"""No desktop driver or global hotkey is invoked by these tests."""
import threading
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from app import sending_store as s
from app.send_controller import SendWorker
from app.wecom_sender import DispatchError
from app.wecom_sender import WeComSender
from app.importer import import_rows
from tests.test_business_logic import seeded, merged_row


def prepare(b,n=3):
    import_rows(b.db,[merged_row(i,f'学员{i}') for i in range(1,n+1)])
    w=b.workflow
    w._batch=w.store.create('测试班',w.template)
    s.save_config(w.store,w._batch,'py169','{姓名}：课{欠课}，作业{欠作业}')
    w.reload_batches(w._batch)
    return w,s.plan(w.store,w._batch)


class RealSendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_user_test_campaign_same_pipeline_and_real_data_isolation(self):
        with seeded(2) as b:
            w,real_tasks=prepare(b,2)
            before=w.store.rows(w._batch)
            people=[dict(name='我自己的测试号',courses='2,1',homework='3',completed_courses='1',completed_homework='2')]
            sender=w.sender
            self.assertTrue(sender.prepareTest(people,'测试','{姓名}|{欠课}|{欠作业}|{欠交合计}|{完成合计}'),sender.status)
            self.assertTrue(sender.testMode)
            task=sender.preview[0]
            self.assertEqual(task['contact'],'测试我自己的测试号')
            self.assertEqual(task['message'],'我自己的测试号|1,2|3|2/1|1/2')
            test_store=sender._dispatch_store
            self.assertNotEqual(test_store.db.path,b.db.path)
            test_row=sender.testResults[0]
            self.assertEqual(task['learning_data'],{key:test_row[key] for key in ('courses','homework','missing_total','completed_courses','completed_homework')})
            for key in ('courses','homework','missing_total','completed_courses','completed_homework','wechat','roster_status','exemption_date'):
                self.assertIn(key,test_row)
            self.assertEqual(test_row['wechat'],'是')
            driver=Mock()
            worker=SendWorker(test_store,sender._dispatch_batch,sender.preview,lambda:driver)
            worker.run()
            driver.send.assert_called_once_with(task['contact'],task['message'])
            self.assertEqual(sender.testResults[0]['send_state'],s.SENT)
            self.assertEqual(w.store.rows(w._batch),before)
            self.assertTrue(sender.prepare('py169',w.template))
            self.assertFalse(sender.testMode)
            self.assertEqual(sender._dispatch_store.db.path,b.db.path)

    def test_test_data_validation_does_not_touch_real_campaign(self):
        with seeded(1) as b:
            w,_=prepare(b,1)
            sender=w.sender
            good=dict(name='测试人员',courses='1',homework='',completed_courses='0',completed_homework='0')
            for people in ([],[dict(good,name='')],[good,good],[dict(good,courses='33')],[dict(good,courses='1,1')],[dict(good,completed_courses='32')],[dict(good,courses='')]):
                self.assertFalse(sender.prepareTest(people,'','{姓名}'))
                self.assertEqual(sender.preview,[])
            self.assertEqual(len(w.store.batches()),1)

    def test_adapter_rejects_wrong_recipient_before_message_paste(self):
        driver=WeComSender.__new__(WeComSender)
        driver.keys=Mock();driver.gui=Mock();driver.process=Mock()
        driver._copy=Mock();driver._require_empty_draft=Mock()
        driver.pause_requested=lambda:False
        window=Mock(title='企业微信',isMinimized=False)
        driver.keys.getWindowsWithTitle.return_value=[window]
        state={'hwnd':1}
        driver.gui.GetForegroundWindow.side_effect=lambda:state['hwnd']
        driver.gui.IsWindow.return_value=True
        driver.gui.GetWindowText.side_effect=lambda h:'企业微信' if h==1 else '错误的联系人'
        driver.process.GetWindowThreadProcessId.return_value=(1,777)
        def hotkey(*keys):
            if keys==('ctrl','o'):state['hwnd']=2
        driver.keys.hotkey.side_effect=hotkey
        with patch('app.wecom_sender.time.sleep'),self.assertRaises(DispatchError) as caught:
            driver.send('py169正确联系人','绝不能发送')
        self.assertFalse(caught.exception.uncertain)
        self.assertEqual([c.args for c in driver._copy.call_args_list],[('py169正确联系人',)])

    def test_stop_during_pause_never_processes_remaining_students(self):
        with seeded(2) as b:
            w,tasks=prepare(b,2)
            driver=Mock()
            worker=SendWorker(w.store,w._batch,tasks,lambda:driver)
            worker.pause();worker.start();worker.stop()
            self.assertTrue(worker.wait(5000))
            driver.send.assert_not_called()

    def test_plan_live_rules_prefix_receipts_feedback_and_no_resend(self):
        with seeded(3) as b:
            w,tasks=prepare(b)
            self.assertEqual(tasks[0]['contact'],'py169学员1')
            self.assertEqual(tasks[0]['message'],'学员1：课无，作业1')
            b.repo.update_profile_field(tasks[1]['student_id'],'微信','否')
            self.assertIsNone(s.claim(w.store,w._batch,tasks[1]))
            attempt=s.claim(w.store,w._batch,tasks[0])
            self.assertIsNone(s.claim(w.store,w._batch,tasks[0]))
            s.finish(w.store,w._batch,tasks[0],attempt,s.SENT,'已执行，未核验送达')
            self.assertEqual([r['student_id'] for r in s.plan(w.store,w._batch)],[tasks[2]['student_id']])
            w.store.submit(w._batch,tasks[0]['student_id'],'今晚补')
            self.assertEqual(w.store.rows(w._batch,tasks[0]['student_id'])[0]['reply_state'],'已回复')
            s.save_config(w.store,w._batch,'new','新消息{姓名}')
            self.assertEqual(w.store.rows(w._batch,tasks[0]['student_id'])[0]['message'],tasks[0]['message'])
            self.assertEqual(s.plan(w.store,w._batch)[0]['contact'],'new学员3')

    def test_crash_recovery_unknown_never_automatically_retries(self):
        with seeded(1) as b:
            w,tasks=prepare(b,1)
            s.claim(w.store,w._batch,tasks[0])
            s.recover(b.db)
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],s.UNKNOWN)
            self.assertEqual(s.plan(w.store,w._batch),[])
            # Feedback tracking is independent of uncertain delivery state.
            self.assertEqual(w.store.mark_unreplied(w._batch),1)
            s.resolve(w.store,w._batch,tasks[0]['student_id'],False)
            self.assertEqual(len(s.plan(w.store,w._batch)),1)

    def test_worker_errors_stop_queue_and_classify_outcomes(self):
        for uncertain in (False,True):
            with self.subTest(uncertain=uncertain),seeded(2) as b:
                w,tasks=prepare(b,2)
                class Driver:
                    def send(self,contact,message):raise DispatchError('测试异常',uncertain)
                worker=SendWorker(w.store,w._batch,tasks,Driver)
                worker.run()
                rows=w.store.rows(w._batch)
                self.assertEqual(rows[0]['send_state'],s.UNKNOWN if uncertain else s.FAILED)
                self.assertEqual(rows[1]['send_state'],'待发送')
                self.assertEqual(len(s.plan(w.store,w._batch)),1 if uncertain else 2)

    def test_pause_finishes_current_then_waits_resume_rechecks_rules(self):
        with seeded(3) as b:
            w,tasks=prepare(b)
            entered=threading.Event();release=threading.Event();second=threading.Event()
            sent=[]
            class Driver:
                def send(self,contact,message):
                    sent.append(contact)
                    if len(sent)==1:
                        entered.set()
                        if not release.wait(5):raise AssertionError('测试释放超时')
                    else:second.set()
            worker=SendWorker(w.store,w._batch,tasks,Driver)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                worker.pause()
                release.set()
                self.assertFalse(second.wait(.2))
                b.repo.update_profile_field(tasks[1]['student_id'],'微信','否')
                worker.resume()
                self.assertTrue(worker.wait(5000))
                self.assertEqual(sent,['py169学员1','py169学员3'])
                self.assertEqual(w.store.rows(w._batch,tasks[0]['student_id'])[0]['send_state'],s.SENT)
            finally:
                release.set();worker.stop();worker.wait(5000)

    def test_duplicate_names_invalid_templates_history_and_preview_guard(self):
        with seeded(2) as b:
            w,tasks=prepare(b,2)
            with self.assertRaises(ValueError):s.save_config(w.store,w._batch,'py','{未知变量}')
            self.assertTrue(w.sender.prepare('py',w.template))
            b.repo.update_profile_field(tasks[0]['student_id'],'微信','否')
            # Changed preview fails before importing/constructing the desktop driver.
            self.assertFalse(w.sender.start())
            self.assertIn('重新预览',w.sender.status)
            with b.db.connect() as conn:
                conn.execute('UPDATE class_roster SET name=?',('同名',))
            with self.assertRaises(ValueError):s.plan(w.store,w._batch)
            old=w._batch
            w.store.create('测试',w.template)
            with self.assertRaises(ValueError):s.plan(w.store,old)


if __name__=='__main__':unittest.main()
