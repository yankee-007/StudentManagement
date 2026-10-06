import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.contact_opener import ContactOpenTask
from tests.profile_fixtures import insert_profile
from tests.test_message_content import fake_driver


class ContactOpenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_open_leaves_verified_chat_without_message_actions(self):
        driver,state=fake_driver({'substring_mode':True,'verify_contact':False})
        driver.copy_chat_item=Mock()
        with patch('app.wecom_sender.time.sleep'):
            self.assertEqual(driver.open_contact('试甲'),(2,777))
        self.assertEqual(state['hwnd'],2)
        self.assertNotIn((('ctrl','w'),2),state['events'])
        self.assertEqual(driver.keys.press.call_count,1)  # Only selecting the search result.
        self.assertFalse(any(hwnd==2 and keys in [('enter',),('ctrl','v')] for keys,hwnd in state['events']))
        driver.copy_chat_item.assert_not_called()
        self.assertEqual(driver._clipboard.call_count,1)

    def test_mismatch_closes_wrong_float(self):
        driver,state=fake_driver({})
        with patch('app.wecom_sender.time.sleep'),self.assertRaises(RuntimeError):driver.open_contact('不存在')
        self.assertEqual(state['hwnd'],1)
        self.assertEqual(driver.keys.press.call_count,1)

    def test_worker_uses_open_only(self):
        with patch('app.wecom_sender.WeComSender') as factory:
            task=ContactOpenTask('张三')
            task.run()
            factory.return_value.open_contact.assert_called_once_with('张三',keep_float=True,verify_contact=True)
            factory.return_value.send.assert_not_called()

    def test_close_float_returns_to_main_without_sending(self):
        driver,state=fake_driver({'verify_contact':False})
        driver.copy_chat_item=Mock()
        with patch('app.wecom_sender.time.sleep'):
            self.assertEqual(driver.open_contact('测试甲',keep_float=False),(1,777))
        self.assertIn((('ctrl','o'),1),state['events'])
        self.assertIn((('ctrl','w'),2),state['events'])
        self.assertEqual(driver.keys.press.call_count,1)
        driver.copy_chat_item.assert_not_called()

    def test_search_only_never_opens_float(self):
        for keep in (True,False):
            driver,state=fake_driver({})
            driver.copy_chat_item=Mock()
            with patch('app.wecom_sender.time.sleep'):
                self.assertEqual(driver.open_contact('测试甲',keep_float=keep,verify_contact=False),(1,777))
            self.assertNotIn((('ctrl','o'),1),state['events'])
            self.assertEqual(driver.keys.press.call_count,1)
            driver.copy_chat_item.assert_not_called()

    def test_identity_prefix_and_sending_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(Path(folder)/'test.db')
            with b.db.connect() as conn:
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','张三','2026-09-27')")
                insert_profile(conn,'001','张三',1)
            b.profilesModule.refresh()
            opener=b.contactOpener; key=b.profilesModule.selected['_record_key']
            with patch('app.contact_opener.ContactOpenTask') as factory:
                self.assertFalse(opener.openContact('stale',''))
                factory.assert_not_called()
                b.groupCenter._worker=Mock()
                self.assertFalse(opener.openContact(key,''))
                factory.assert_not_called()
                b.groupCenter._worker=None
                opener.setKeepFloat(False)
                opener.setVerifyContact(False)
                self.assertTrue(opener.openContact(key,'py169'))
                self.assertEqual(factory.call_args.args[0],'py169张三')
                self.assertFalse(factory.call_args.kwargs['keep_float'])
                self.assertFalse(factory.call_args.kwargs['verify_contact'])
                self.assertEqual(b.workflow.registry.get_setting('profile_contact_verify'),'0')
                self.assertEqual(b.workflow.registry.get_setting('profile_contact_keep_float'),'0')
                self.assertEqual(opener.prefix(key),'py169')
                self.assertTrue(b.workflow.send_busy)
                self.assertFalse(opener.openContact(key,''))
                self.assertEqual(factory.call_count,1)
                opener._finished()
                self.assertFalse(b.workflow.send_busy)
                self.assertEqual(b.workflow.store.batches(),[])

    def test_default_prefix_persists_and_preserves_class_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            b = Backend(Path(folder) / 'test.db')
            with b.db.connect() as conn:
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','示例甲','2026-10-06')")
                insert_profile(conn, '001', '示例甲', 1)
            b.refresh()
            b.workflow.createBatch()
            opener = b.contactOpener
            profile_key = b.profilesModule.selected['_record_key']
            campaign_key = b.workflow.editorKey
            self.assertTrue(opener.setDefaultPrefix('  py169  '))
            self.assertEqual(opener.prefix(profile_key), 'py169')
            self.assertEqual(opener.campaignPrefix(campaign_key), 'py169')
            self.assertEqual(opener.prefix('stale'), '')
            self.assertEqual(opener.campaignPrefix('stale'), '')
            b.repo.set_setting('profile_contact_prefix', '')
            b.repo.set_setting('campaign_contact_prefix', '旧班')
            self.assertTrue(opener.setDefaultPrefix('新默认'))
            self.assertEqual(opener.prefix(profile_key), '')
            self.assertEqual(opener.campaignPrefix(campaign_key), '旧班')
            # The fallback is global and survives construction of the next session.
            reopened = Backend(Path(folder) / 'test.db')
            self.assertEqual(reopened.contactOpener.defaultPrefix, '新默认')

    def test_invalid_or_busy_default_prefix_does_not_change_saved_value(self):
        with tempfile.TemporaryDirectory() as folder:
            b = Backend(Path(folder) / 'test.db')
            opener = b.contactOpener
            self.assertTrue(opener.setDefaultPrefix('py169'))
            for invalid in ('a\nb', 'a\rb', 'a\0b'):
                self.assertFalse(opener.setDefaultPrefix(invalid))
                self.assertEqual(opener.defaultPrefix, 'py169')
            with patch.object(b.workflow.registry, 'set_setting', side_effect=RuntimeError('临时写入失败')):
                self.assertFalse(opener.setDefaultPrefix('失败写入'))
                self.assertEqual(opener.defaultPrefix, 'py169')
            opener._worker = Mock()
            self.assertFalse(opener.setDefaultPrefix('忙碌时修改'))
            self.assertEqual(opener.defaultPrefix, 'py169')
            opener._finished()


if __name__=='__main__':unittest.main()
