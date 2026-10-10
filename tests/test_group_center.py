import json
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from app.group_dispatch import GroupStore
from app.send_options import normalize
from app import group_dispatch as adapter
from app.send_controller import F11Hotkey, SendWorker
from app import sending_store as source
from app.wecom_sender import DispatchError, WeComSender
from tests.test_business_logic import seeded
from tests.test_real_sending import prepare


class GroupCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_rename_list_only_changes_the_title(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createCustom('重命名前','甲|第一条\n乙|第二条'))
            list_id=g.selected['id']
            self.assertTrue(g.prepare('前缀-',{}),g.status)
            preview=list(g.preview)
            self.assertEqual(len(preview),2)
            self.assertTrue(g.renameList(list_id,'  重命名后  '),g.status)
            self.assertEqual(g.selected['title'],'重命名后')
            self.assertEqual(g.store.get(list_id)['title'],'重命名后')
            self.assertEqual([row['label'].split(' · ')[0] for row in g.lists],['重命名后'])
            self.assertEqual([r['name'] for r in g.store.rows(list_id)],['甲','乙'])
            self.assertEqual([r['message'] for r in g.store.rows(list_id)],['第一条','第二条'])
            self.assertEqual(g.pendingCount,2)
            # 改名不废弃已确认的预览，人员与消息也不变。
            self.assertEqual(g.preview,preview)
            self.assertEqual(g.selected['prefix'],'前缀-')
            for invalid in ('   ','第一行\n第二行'):
                self.assertFalse(g.renameList(list_id,invalid))
                self.assertIn('重命名失败',g.status)
                self.assertEqual(g.store.get(list_id)['title'],'重命名后')
            self.assertFalse(g.renameList(list_id+999,'别的名单'))
            self.assertIn('重命名失败',g.status)
            self.assertEqual([r['state'] for r in g.rows],['待发送','待发送'])
            # 发送运行中不接受改名，名单名保持原值。
            g._worker=object()
            try:
                self.assertFalse(g.renameList(list_id,'发送中改名'))
                self.assertIn('发送运行中',g.status)
            finally:
                g._worker=None
            self.assertEqual(g.store.get(list_id)['title'],'重命名后')

    def test_manage_unselected_plan_keeps_current_content_and_preview(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createCustom('旧方案','甲|旧消息'))
            old_id=g.selected['id']; task=g.store.plan(old_id)[0]
            attempt=g.store.claim(old_id,task)
            g.store.finish(old_id,task,attempt,source.SENT,'模拟已发送')
            self.assertTrue(g.createCustom('当前方案','乙|当前消息'))
            current_id=g.selected['id']
            self.assertTrue(g.prepare('前缀-',{}),g.status)
            preview=list(g.preview); confirmation=g._confirmation
            self.assertTrue(g.renameList(old_id,'旧方案新名称'),g.status)
            self.assertEqual(g.store.get(old_id)['title'],'旧方案新名称')
            self.assertEqual(g.selected['id'],current_id)
            self.assertTrue(g.deleteList(old_id),g.status)
            self.assertIsNone(g.store.get(old_id));self.assertEqual(g.store.rows(old_id),[])
            with g.store.connect() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM attempts WHERE id=?',(attempt,)).fetchone()[0],0)
                self.assertEqual(list(conn.execute('PRAGMA foreign_key_check')),[])
            self.assertEqual(g.selected['id'],current_id)
            self.assertEqual(g.preview,preview);self.assertEqual(g._confirmation,confirmation)
            self.assertEqual([row['message'] for row in g.rows],['当前消息'])
            self.assertFalse(g.deleteList(old_id));self.assertIn('已不存在',g.status)
            self.assertEqual(g.preview,preview)

    def test_delete_selected_plan_chooses_next_then_clears_the_last(self):
        with seeded(1) as b:
            g=b.groupCenter; ids=[]
            for title in ('最早','中间','最新'):
                self.assertTrue(g.createCustom(title,'甲|消息'));ids.append(g.selected['id'])
            g.selectList(1)
            self.assertTrue(g.prepare('',{}),g.status)
            self.assertTrue(g.deleteList(ids[1]),g.status)
            self.assertEqual(g.selected['id'],ids[0]);self.assertEqual(g.selectedIndex,1)
            self.assertEqual(g.preview,[]);self.assertIsNone(g._confirmation)
            self.assertTrue(g.deleteList(ids[0]),g.status)
            self.assertEqual(g.selected['id'],ids[2]);self.assertEqual(g.selectedIndex,0)
            self.assertTrue(g.deleteList(ids[2]),g.status)
            self.assertEqual(g.lists,[]);self.assertEqual(g.selected['id'],0)
            self.assertEqual(g.selectedIndex,-1);self.assertEqual(g.pendingCount+g.sentCount,0)
            self.assertEqual(g.defaultFields,[])

    def test_delete_plan_protects_unsettled_results_and_rolls_back(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createCustom('事务保护','甲|消息'))
            list_id=g.selected['id'];task=g.store.plan(list_id)[0]
            attempt=g.store.claim(list_id,task)
            g.store.finish(list_id,task,attempt,source.FAILED,'模拟失败')
            for state,pending,reason in ((source.RUNNING,0,'正在发送'),(source.UNKNOWN,0,'待核实'),
                                         ('仅粘贴未发送',0,'待核实'),(source.FAILED,1,'来源回写')):
                with self.subTest(state=state,pending=pending):
                    with g.store.connect() as conn:
                        conn.execute('UPDATE recipients SET state=?,sync_pending=? WHERE list_id=?',(state,pending,list_id))
                    self.assertFalse(g.deleteList(list_id));self.assertIn(reason,g.status)
                    self.assertIsNotNone(g.store.get(list_id));self.assertEqual(len(g.store.rows(list_id)),1)
            with g.store.connect() as conn:
                conn.execute('UPDATE recipients SET state=?,sync_pending=0 WHERE list_id=?',(source.FAILED,list_id))
                conn.execute("CREATE TRIGGER prevent_recipient_delete BEFORE DELETE ON recipients BEGIN SELECT RAISE(ABORT,'模拟删除失败'); END")
            g._worker=object()
            try:
                self.assertFalse(g.deleteList(list_id));self.assertIn('发送运行中',g.status)
            finally:g._worker=None
            self.assertFalse(g.deleteList(list_id));self.assertIn('模拟删除失败',g.status)
            with g.store.connect() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM attempts WHERE id=?',(attempt,)).fetchone()[0],1)
            self.assertIsNotNone(g.store.get(list_id));self.assertEqual(len(g.store.rows(list_id)),1)

    def test_delete_plan_keeps_legacy_source_receipts(self):
        with seeded(1) as b:
            g=b.groupCenter;w,tasks=prepare(b,1)
            list_id=g.store.create('旧来源',[dict(name='学员1',student_id=tasks[0]['student_id'],message='消息')],w.store,w._batch)
            task=g.store.plan(list_id)[0];attempt=g.store.claim(list_id,task)
            g.store.finish(list_id,task,attempt,source.SENT,'模拟已发送')
            g.refresh();g.selectList(0)
            with w.store.db.connect() as conn:
                before=[tuple(row) for row in conn.execute('SELECT * FROM send_attempts')]
            self.assertTrue(g.deleteList(list_id),g.status)
            with w.store.db.connect() as conn:
                self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM send_attempts')],before)

    def test_new_plan_starts_empty_and_takes_typed_or_pasted_names(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createEmptyList('  空方案  '),g.status)
            list_id=g.selected['id']
            self.assertEqual(g.selected['title'],'空方案')
            self.assertEqual(g.rows,[]);self.assertEqual(g.pendingCount,0)
            self.assertEqual([row['label'].split(' · ')[0] for row in g.lists],['空方案'])
            # 空方案允许先存模板：保存 0 人成功，添加姓名时按模板生成消息。
            draft=[dict(sourceIndex=-1,type='text',value='{姓名}同学，请查收')]
            self.assertTrue(g.saveDefaultRow(list_id,g.contentRevision,draft,False),g.status)
            self.assertIn('模板已保存',g.status)
            result=g.addNames(list_id,['甲','甲','','乙'])
            self.assertEqual(result['added'],['甲','乙'])
            self.assertEqual(result['skipped'],['甲'])
            self.assertEqual(result['no_message'],[])
            self.assertEqual([row['name'] for row in g.rows],['甲','乙'])
            self.assertEqual([json.loads(row['content'])[0]['text'] for row in g.rows],['甲同学，请查收','乙同学，请查收'])
            self.assertEqual(g.pendingCount,2)
            self.assertTrue(g.prepare('',{}),g.status)
            self.assertEqual([row['name'] for row in g.preview],['甲','乙'])
            self.assertFalse(g.createEmptyList('   '))
            self.assertIn('创建失败',g.status)

    def test_typed_names_that_cannot_use_the_template_stay_empty(self):
        with seeded(1) as b:
            g=b.groupCenter
            # 画像名单的模板含画像变量：手动添加的姓名无法解析，留空而不是写占位提示。
            list_id=g.store.create('变量名单',[dict(name='甲',content=[dict(type='text',text='甲欠第3节')],
                learning_data=dict(profile_fields={'欠课':'第3节'}),message='欠课{欠课}')],
                content_template=[dict(type='text',text='欠课{欠课}')])
            g.refresh()
            g.selectList(next(i for i,row in enumerate(g.lists) if row['id']==list_id))
            result=g.addNames(list_id,['乙'])
            self.assertEqual(result['added'],['乙'])
            self.assertEqual(result['no_message'],['乙'])
            self.assertEqual(json.loads(g.rows[1]['content']),[])
            self.assertIn('还没有套用上模板消息',g.status)
            # 没有消息的人不能进入预览，避免空消息误发。
            self.assertFalse(g.prepare('',{}),g.status)
            self.assertIn('尚未配置消息字段',g.status)

    def test_remove_names_keeps_send_records(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createCustom('删除测试','甲|话术\n乙|话术'))
            list_id=g.selected['id']
            ids={row['name']:row['id'] for row in g.rows}
            self.assertTrue(g.removeNames(list_id,[ids['乙']]),g.status)
            self.assertEqual([row['name'] for row in g.rows],['甲'])
            self.assertFalse(g.removeNames(list_id,[ids['乙']]))
            self.assertIn('不在当前名单',g.status)
            # 有发送记录（含失败后重试）和受保护状态都不能删除。
            task=g.store.plan(list_id)[0]
            attempt=g.store.claim(list_id,task)
            g.store.finish(list_id,task,attempt,source.FAILED,'未发送失败')
            self.assertFalse(g.removeNames(list_id,[g.rows[0]['id']]))
            self.assertIn('有发送记录的姓名不能删除',g.status)
            self.assertEqual(len(g.rows),1)
            g._worker=object()
            try:
                self.assertFalse(g.removeNames(list_id,[g.rows[0]['id']]))
                self.assertIn('发送运行中',g.status)
            finally:
                g._worker=None

    def test_v2_options_apply_and_paste_only_never_sends_enter(self):
        driver=WeComSender.__new__(WeComSender)
        driver.options=normalize(dict(wait=.7,focus_delay=.8,paste_delay=.9,timeout=5,substring_mode=True,confirm_send=False))
        driver.keys=Mock();driver.gui=Mock();driver.process=Mock()
        driver._copy=Mock();driver._require_empty_draft=Mock();driver.pause_requested=lambda:False
        driver.keys.getWindowsWithTitle.return_value=[Mock(title='企业微信',isMinimized=False)]
        state={'hwnd':1}
        driver.gui.GetForegroundWindow.side_effect=lambda:state['hwnd']
        driver.gui.GetWindowText.side_effect=lambda hwnd:'企业微信' if hwnd==1 else 'py测试号（备注）'
        driver.gui.IsWindow.return_value=True
        driver.process.GetWindowThreadProcessId.return_value=(1,777)
        def hotkey(*keys):
            if keys==('ctrl','o'):state['hwnd']=2
            if keys==('ctrl','w'):state['hwnd']=1
        driver.keys.hotkey.side_effect=hotkey
        with patch('app.wecom_sender.time.sleep') as sleep:
            self.assertEqual(driver.send('py测试号','指定消息'),'仅粘贴未发送')
        self.assertEqual(driver.keys.press.call_count,1)  # Search Enter only, no message Enter.
        self.assertIn(('ctrl','w'),[c.args for c in driver.keys.hotkey.call_args_list])
        self.assertIn((.7,),[c.args for c in sleep.call_args_list])
        self.assertIn((.8,),[c.args for c in sleep.call_args_list])
        self.assertIn((.9,),[c.args for c in sleep.call_args_list])
        self.assertEqual(driver._copy.call_args.args,('指定消息',))

    def test_send_failure_continues_and_failed_recipient_stays_pending(self):
        with seeded(3) as b, patch('app.wecom_sender.WeComSender') as factory, patch.object(F11Hotkey,'start'):
            g=b.groupCenter
            self.assertTrue(g.createCustom('失败继续','甲|第一条\n乙|第二条\n丙|第三条'))
            list_id=g.selected['id']
            self.assertTrue(g.prepare('',{}),g.status)
            driver=factory.return_value
            def send(contact,content):
                if contact=='甲':raise DispatchError('联系人浮窗标题不匹配，未发送')
                return source.SENT
            driver.send.side_effect=send
            self.assertTrue(g.start(),g.status)
            worker=g._worker
            self.assertTrue(worker and worker.wait(10000),'发送线程未结束')
            for _ in range(200):
                QTest.qWait(10)
                if not g.active:break
            self.assertFalse(g.active,'发送线程状态未回收')
            self.assertEqual(driver.send.call_count,3)  # The failure does not end the round.
            self.assertEqual({r['name']:r['state'] for r in g.store.rows(list_id)},
                             {'甲':source.FAILED,'乙':source.SENT,'丙':source.SENT})
            self.assertEqual([r['name'] for r in g.pendingModel.rows],['甲'])
            self.assertEqual([r['name'] for r in g.store.plan(list_id)],['甲'])
            self.assertIn('1 人发送失败仍在待处理',g.status)

    def test_custom_names_messages_persist_without_creating_campaign(self):
        with seeded(1) as b:
            g=b.groupCenter
            self.assertTrue(g.createCustom('测试名单','我的测试号|第一行\\n第二行'))
            self.assertEqual(b.workflow.store.batches(),[])
            self.assertTrue(g.prepare('test',{'wait':1,'confirm_send':False}))
            self.assertEqual(g.preview[0]['message'],'第一行\n第二行')
            self.assertEqual(g.preview[0]['contact'],'test我的测试号')
            self.assertTrue(g.selected['options']['verify_contact'])
            reopened=GroupStore(g.store.path)
            self.assertEqual(reopened.get(g.selected['id'])['prefix'],'test')
            driver=Mock();driver.send.return_value='仅粘贴未发送'
            worker=SendWorker(g.store,g.selected['id'],g.preview,lambda:driver,adapter=adapter)
            worker.run()
            self.assertEqual(g.rows[0]['state'],'仅粘贴未发送')
            self.assertEqual(g.store.plan(g.selected['id']),[])
            self.assertEqual(b.workflow.store.batches(),[])
            self.assertTrue(g.resolve(g.selected['id'],g.rows[0]['id'],False))
            self.assertEqual(len(g.store.plan(g.selected['id'])),1)

    def test_campaign_list_generation_later_sending_and_writeback(self):
        with seeded(2) as b:
            w,tasks=prepare(b,2)
            g=b.groupCenter
            self.assertTrue(g.generateCampaign('{姓名}：作业{欠作业}'),g.status)
            first=g.selected['id']
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],'待发送')
            self.assertEqual(g.selected['kind'],'催办名单')
            self.assertTrue(g.prepare('py169',{}))
            source_sid=tasks[1]['student_id']
            b.repo.update_profile_field(source_sid,'微信','否')
            self.assertFalse(g.start())  # No driver is constructed when preview changed.
            self.assertTrue(g.prepare('py169',{}))
            self.assertEqual(len(g.preview),1)
            driver=Mock();driver.send.return_value=source.SENT
            SendWorker(g.store,first,g.preview,lambda:driver,adapter=adapter).run()
            self.assertEqual(w.store.rows(w._batch,tasks[0]['student_id'])[0]['send_state'],source.SENT)
            w.store.submit(w._batch,tasks[0]['student_id'],'明天补')
            self.assertEqual(w.store.rows(w._batch,tasks[0]['student_id'])[0]['reply_state'],'已回复')
            self.assertEqual(g.store.plan(first),[])

    def test_two_generated_lists_do_not_send_same_source_twice(self):
        with seeded(1) as b:
            w,_=prepare(b,1);g=b.groupCenter
            self.assertTrue(g.generateCampaign(w.template))
            first=g.selected['id']
            self.assertTrue(g.generateCampaign(w.template))
            second=g.selected['id']
            task=g.store.plan(first)[0]
            attempt=g.store.claim(first,task)
            self.assertIsNotNone(attempt)
            self.assertEqual(g.store.plan(second),[])
            g.store.finish(first,task,attempt,source.SENT,'已执行')
            self.assertEqual(g.store.plan(second),[])

    def test_recovery_and_pending_writeback_are_durable(self):
        with seeded(1) as b:
            w,tasks=prepare(b,1);g=b.groupCenter
            self.assertTrue(g.generateCampaign(w.template))
            job=g.selected['id'];task=g.store.plan(job)[0]
            attempt=g.store.claim(job,task)
            with patch.object(g.store,'sync_results',side_effect=RuntimeError('数据库暂不可用')):
                with self.assertRaises(RuntimeError):g.store.finish(job,task,attempt,source.SENT,'已执行')
            self.assertEqual(g.rows[0]['state'],source.SENT)
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],source.RUNNING)
            GroupStore(g.store.path).recover()
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],source.SENT)
            self.assertEqual(g.store.plan(job),[])

    def test_parameters_validation_and_history_guard(self):
        for invalid in ({'wait':-1},{'timeout':'nan'},{'interval':61},{'confirm_send':'true'},{'ocr':True}):
            with self.assertRaises(ValueError):normalize(invalid)
        with seeded(1) as b:
            w,_=prepare(b,1);g=b.groupCenter
            self.assertFalse(g.createCustom('同名','甲|话术\n甲|另一条'))
            self.assertTrue(g.generateCampaign(w.template))
            w.store.create('新批次',w.template)
            self.assertFalse(g.prepare('',{}))
            self.assertIn('历史批次',g.status)


if __name__=='__main__':unittest.main()
