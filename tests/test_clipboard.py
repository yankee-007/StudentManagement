import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QUrl

from app import clipboard


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.native = Mock(CF_UNICODETEXT=13, CF_HDROP=15)
        self.native.IsClipboardFormatAvailable.return_value = True
        self.patch = patch('app.clipboard._native_clipboard', return_value=self.native)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_text_is_read_without_rendering_or_requesting_other_formats(self):
        self.native.GetClipboardData.return_value = '甲\r\n乙\nമലയാളം'
        self.assertEqual(clipboard.read_text(), '甲\r\n乙\nമലയാളം')
        self.native.GetClipboardData.assert_called_once_with(13)
        self.native.CloseClipboard.assert_called_once_with()

    def test_copied_files_keep_unicode_and_literal_percent_paths(self):
        paths = ['C:/资料/甲.txt', 'C:/资料/乙%20.txt']
        self.native.GetClipboardData.return_value = tuple(paths)
        self.assertEqual([url.toLocalFile() for url in clipboard.read_file_urls()], paths)
        self.native.GetClipboardData.assert_called_once_with(15)
        self.native.CloseClipboard.assert_called_once_with()

    def test_unavailable_format_does_not_read_clipboard_data(self):
        self.native.IsClipboardFormatAvailable.return_value = False
        self.assertEqual(clipboard.read_text(), '')
        self.assertEqual(clipboard.read_file_urls(), [])
        self.native.GetClipboardData.assert_not_called()

    def test_busy_clipboard_fails_without_changing_or_closing_an_unopened_handle(self):
        self.native.OpenClipboard.side_effect = OSError('busy')
        for operation in (clipboard.read_text, clipboard.read_file_urls, lambda: clipboard.write_text('甲')):
            with self.assertRaisesRegex(ValueError, '稍后重试'):
                operation()
        self.native.EmptyClipboard.assert_not_called()
        self.native.CloseClipboard.assert_not_called()

    def test_read_failure_still_releases_the_clipboard(self):
        self.native.GetClipboardData.side_effect = OSError('read failed')
        with self.assertRaises(OSError):
            clipboard.read_text()
        self.native.CloseClipboard.assert_called_once_with()

    def test_write_uses_unicode_text_and_releases_the_clipboard(self):
        clipboard.write_text('甲\n乙')
        self.native.SetClipboardText.assert_called_once_with('甲\n乙', 13)
        self.native.CloseClipboard.assert_called_once_with()

    def test_qt_file_fallback_preserves_remote_urls_for_existing_validation(self):
        mime = Mock()
        mime.urls.return_value = [QUrl('https://example.com/file')]
        with patch('app.clipboard._native_clipboard', return_value=None), patch('app.clipboard.QGuiApplication.clipboard') as get:
            get.return_value.mimeData.return_value = mime
            self.assertEqual(clipboard.read_file_urls(), mime.urls.return_value)


if __name__ == '__main__':
    unittest.main()
