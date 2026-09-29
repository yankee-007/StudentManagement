import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from app.group_dispatch import GroupStore
from app.send_options import normalize
from app import group_dispatch as adapter
from app.send_controller import SendWorker
from app import sending_store as source
from app.wecom_sender import WeComSender
from tests.test_business_logic import seeded
from tests.test_real_sending import prepare


class GroupCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

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
