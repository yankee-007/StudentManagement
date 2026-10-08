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

    def test_binding_rows_follow_completion_terms_including_empty_refresh(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            b = Backend(Path(folder) / 'test.db')
            b.workflow._classes[0]['term_id'] = 'old'
            b.settingsModule.refresh()
            self.assertEqual([r['termId'] for r in b.settingsModule.termClasses], ['old'])
            terms = [{'termId': 551, 'termName': '测试班一', 'termNo': 'P2026169'},
                     {'termId': 564, 'termName': '测试班二', 'termNo': 'P2026175'}]
            b.termsModule._accept('terms', terms)
            self.assertEqual([r['termId'] for r in b.settingsModule.termClasses], ['551', '564'])
            self.assertTrue(any(r.get('term_id') == 'old' for r in b.workflow._classes))
            self.assertFalse(b.settingsModule.saveBinding('old', 0))
            b.termsModule._accept('terms', [])
            self.assertEqual(b.settingsModule.termClasses, [])
            self.assertEqual(Backend(Path(folder) / 'test.db').settingsModule.termClasses, [])

    def test_bindings_and_blank_rows_survive_restart_and_class_switch(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            path = Path(folder) / 'test.db'
            b = Backend(path)
            b.workflow.registry.set_setting('homework_admin_id', 'hw-admin')
            b.termsModule._accept('terms', [
                {'termId': 551, 'termName': '测试班一', 'termNo': 'P2026169'},
                {'termId': 564, 'termName': '测试班二', 'termNo': 'P2026175'},
                {'termId': 578, 'termName': '测试班三', 'termNo': 'P2026180'}])
            settings = b.settingsModule
            settings._classes_loaded([{'id': 23, 'name': '测试作业一', 'course_ids': [2]},
                                      {'id': 31, 'name': '测试作业二', 'course_ids': [5, 9]}])
            self.assertTrue(settings.saveBinding('551', 23))
            self.assertTrue(settings.saveBinding('564', 31, 9))
            b.workflow.select_term_id('564')
            self.assertNotEqual(b.db.path, path)
            self.assertTrue(settings.saveBinding('551', 0))
            self.assertTrue(settings.saveBinding('578', 0))
            self.assertFalse(settings.saveBinding('unknown', 0))
            restored = Backend(path).settingsModule
            self.assertEqual(len(restored.termClasses), 3)
            self.assertEqual(restored.bindingFor('551'), {})
            self.assertEqual(restored.bindingFor('578'), {})
            self.assertEqual(restored.bindingFor('564'),
                             {'class_id': 31, 'class_name': '测试作业二', 'course_id': 9})
            self.assertEqual(restored.homeworkClasses[1]['course_ids'], [5, 9])
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT term_id FROM homework_bindings').fetchall(), [('564',)])

    def test_empty_homework_directory_replaces_cache_without_clearing_binding(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            path = Path(folder) / 'test.db'
            b = Backend(path)
            b.workflow.registry.set_setting('homework_admin_id', 'hw-admin')
            b.workflow._classes[0]['term_id'] = '551'
            settings = b.settingsModule
            settings._classes_loaded([{'id': 23, 'name': '测试作业一', 'course_ids': [2]}])
            self.assertTrue(settings.saveBinding('551', 23))
            settings._classes_loaded([])
            restored = Backend(path).settingsModule
            self.assertEqual(restored.homeworkClasses, [])
            self.assertEqual(restored.bindingFor('551')['class_name'], '测试作业一')

    def test_save_failures_are_reported_without_losing_existing_binding(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            b = Backend(Path(folder) / 'test.db')
            b.workflow._classes[0]['term_id'] = '551'
            settings = b.settingsModule
            settings._classes_loaded([{'id': 23, 'name': '测试作业一', 'course_ids': [2]}])
            self.assertTrue(settings.saveBinding('551', 23))
            with patch.object(b.workflow.registry.db, 'connect', side_effect=sqlite3.OperationalError('locked')):
                self.assertFalse(settings.saveBinding('551', 0))
            self.assertIn('保存失败', settings.notice)
            self.assertEqual(settings.bindingFor('551')['class_id'], 23)
            with patch.object(b.workflow.registry, 'set_setting', side_effect=sqlite3.OperationalError('locked')):
                settings._classes_loaded([])
            self.assertIn('未能写入本地缓存', settings.notice)


if __name__=='__main__':unittest.main()
