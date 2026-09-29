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


if __name__=='__main__':unittest.main()
