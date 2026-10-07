"""Global appearance persistence, isolated notifications and failed writes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from app.backend import Backend


class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_default_toggle_and_restart(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            path = Path(folder) / 'appearance.db'
            backend = Backend(path)
            settings = backend.settingsModule
            self.assertEqual(settings.appearanceMode, 'light')
            changed, appearance = [], []
            settings.changed.connect(lambda: changed.append(True))
            settings.appearanceChanged.connect(lambda: appearance.append(True))
            self.assertTrue(settings.setAppearanceMode('dark'))
            self.assertTrue(settings.setAppearanceMode('dark'))
            self.assertEqual(appearance, [True])
            self.assertEqual(changed, [])
            self.assertEqual(Backend(path).settingsModule.appearanceMode, 'dark')
            self.assertTrue(settings.setAppearanceMode('light'))
            self.assertEqual(Backend(path).settingsModule.appearanceMode, 'light')
            self.assertFalse(settings.setAppearanceMode('unexpected'))
            backend.workflow.registry.set_setting('appearance_mode', 'unexpected')
            self.assertEqual(Backend(path).settingsModule.appearanceMode, 'light')

    def test_failed_save_retains_current_theme(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            backend = Backend(Path(folder) / 'appearance.db')
            settings = backend.settingsModule
            appearance = []
            settings.appearanceChanged.connect(lambda: appearance.append(True))
            with patch.object(backend.workflow.registry, 'set_setting', side_effect=OSError('test failure')):
                self.assertFalse(settings.setAppearanceMode('dark'))
            self.assertEqual(settings.appearanceMode, 'light')
            self.assertEqual(appearance, [])
            self.assertIn('保存失败', settings.notice)
            self.assertEqual(backend.workflow.registry.get_setting('appearance_mode', 'light'), 'light')


if __name__ == '__main__':
    unittest.main()
