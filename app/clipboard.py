"""Read only the requested Windows clipboard format; do not render clipboard text."""
from contextlib import contextmanager
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication


def _native_clipboard():
    app = QGuiApplication.instance()
    if sys.platform == 'win32' and isinstance(app, QGuiApplication) and app.platformName() == 'windows':
        import win32clipboard
        return win32clipboard
    return None


@contextmanager
def _opened(clipboard):
    try:
        clipboard.OpenClipboard()
    except Exception as exc:
        raise ValueError('剪贴板正被其他程序占用，请稍后重试。') from exc
    try:
        yield
    finally:
        clipboard.CloseClipboard()


def read_text():
    clipboard = _native_clipboard()
    if clipboard is None:
        return QGuiApplication.clipboard().text()
    with _opened(clipboard):
        if not clipboard.IsClipboardFormatAvailable(clipboard.CF_UNICODETEXT):
            return ''
        return clipboard.GetClipboardData(clipboard.CF_UNICODETEXT)


def write_text(text):
    clipboard = _native_clipboard()
    if clipboard is None:
        QGuiApplication.clipboard().setText(text)
        return
    with _opened(clipboard):
        clipboard.EmptyClipboard()
        clipboard.SetClipboardText(text, clipboard.CF_UNICODETEXT)


def read_file_urls():
    clipboard = _native_clipboard()
    if clipboard is None:
        mime = QGuiApplication.clipboard().mimeData()
        return mime.urls() if mime and mime.hasUrls() else []
    with _opened(clipboard):
        if not clipboard.IsClipboardFormatAvailable(clipboard.CF_HDROP):
            return []
        return [QUrl.fromLocalFile(path) for path in clipboard.GetClipboardData(clipboard.CF_HDROP)]
