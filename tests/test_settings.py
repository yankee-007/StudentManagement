from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication
from app.backend import Backend


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_verify_login_uses_entered_credentials_without_saving(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password',return_value='saved-password'):
            b=Backend(Path(folder)/'test.db')
            settings=b.settingsModule
            with patch('app.acquisition.tasks.AcquisitionTask.start'):
                self.assertTrue(settings.verifyLogin('homework','new-account','entered-password'))
                task=settings._task
                self.assertEqual(task.homework,('new-account','entered-password'))
                self.assertTrue(settings.busy)
                self.assertFalse(settings.verifyLogin('completion','other','password'))
                settings._login_verified({'count':2})
                self.assertEqual(settings.verification['homework']['state'],'success')
                self.assertEqual(b.workflow.registry.get_setting('homework_admin_id',''),'')
                self.assertFalse(settings.busy)
                self.assertTrue(settings.verifyLogin('completion','saved-account',''))
                self.assertEqual(settings._task.completion,('saved-account','saved-password'))
                settings._login_failed('验证失败')
                self.assertEqual(settings.verification['completion']['state'],'error')
                self.assertFalse(settings.busy)

    def test_passwords_only_in_vault_and_fetch_config_uses_raw_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            vault={}
            def get(service,username):return vault.get((service,username))
            def set_value(service,username,password):vault[(service,username)]=password
            with patch('keyring.get_password',side_effect=get),patch('keyring.set_password',side_effect=set_value):
                b=Backend(Path(folder)/'test.db')
                settings=b.settingsModule
                self.assertTrue(settings.saveAccount('completion','test-completion','test-completion-password'))
                self.assertTrue(settings.saveAccount('homework','test-homework','test-homework-password'))
                self.assertTrue(settings.saveAccount('homework','test-homework',''))
                self.assertFalse(settings.saveAccount('homework','other-account',''))
                self.assertTrue(settings.accounts['completion']['saved'])
                self.assertTrue(settings.accounts['homework']['saved'])
                with closing(sqlite3.connect(b.workflow.registry.db.path)) as conn:
                    values=[r[0] for r in conn.execute('SELECT value FROM settings')]
                self.assertFalse(any('test-completion-password' in v or 'test-homework-password' in v for v in values))

                self.assertEqual(b.workflow.registry.get_setting('completion_username'),'test-completion')
                self.assertEqual(b.workflow.registry.get_setting('homework_admin_id'),'test-homework')
                self.assertFalse(b.fetchData())  # No term/binding means no network request.

    def test_homework_classes_survive_restart_for_the_same_account(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('app.settings_module.get_password', return_value=None), \
                patch('app.settings_module.set_password'):
            path = Path(folder) / 'test.db'
            b = Backend(path)
            b.workflow.registry.set_setting('homework_admin_id', 'hw-admin')
            b.workflow._classes[0]['term_id'] = '551'
            settings = b.settingsModule
            settings._classes_loaded([{'id': 23, 'name': '正式课py169', 'course_ids': [2]},
                                      {'id': 31, 'name': '正式课py175', 'course_ids': [5]}])
            self.assertTrue(settings.saveBinding('551', 23), settings.notice)
            self.assertEqual(settings.bindingFor('551')['course_id'], 2)
            # 也不应依赖界面传课程：自动取该班级第一个课程。
            self.assertTrue(settings.saveBinding('551', 31))
            self.assertEqual(settings.bindingFor('551')['course_id'], 5)
            self.assertFalse(settings.saveBinding('551', 99))

            # 平台没有返回课程时不允许确认，避免写出无效课程 ID。
            settings._homework_classes = [{'id': 40, 'name': '无课程班级', 'course_ids': []}]
            self.assertFalse(settings.saveBinding('551', 40))
            self.assertIn('课程', settings.notice)

            reopened = Backend(path)
            restored = reopened.settingsModule
            self.assertEqual([c['id'] for c in restored.homeworkClasses], [23, 31])
            self.assertEqual(restored.homeworkClasses[0]['course_ids'], [2])
            self.assertEqual(restored.bindingFor('551')['class_id'], 31)
            # 换账号后不再复用上一个账号的班级目录。
            restored.saveAccount('homework', 'other-admin', 'password')
            self.assertEqual(restored.homeworkClasses, [])


if __name__=='__main__':unittest.main()
