"""Verify native frame styling with a disposable database and fictitious roster."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from PySide6.QtCore import QEvent, QUrl, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.roster_sync import sync_roster
from app.window_theme import NativeTitleBarTheme, apply_native_title_bar_theme
from tests.smoke_ui_refresh import RestartProbe


def capture_native_window(window, path):
    """Print this HWND directly, so foreground windows cannot enter evidence."""
    import win32gui
    import win32ui
    handle = int(window.winId())
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    width, height = right - left, bottom - top
    dc_handle = win32gui.GetWindowDC(handle)
    source = win32ui.CreateDCFromHandle(dc_handle)
    target = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        target.SelectObject(bitmap)
        printer = ctypes.WinDLL("user32").PrintWindow
        printer.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        printer.restype = wintypes.BOOL
        assert printer(handle, target.GetSafeHdc(), 2)
        pixels = bitmap.GetBitmapBits(True)
        image = QImage(pixels, width, height, width * 4, QImage.Format_RGB32).copy()
        assert image.save(str(path))
    finally:
        target.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(handle, dc_handle)
        win32gui.DeleteObject(bitmap.GetHandle())


def run():
    QQuickStyle.setStyle("Fusion")
    app = QApplication([])
    configure_font(app)
    app.setWindowIcon(QIcon(str(Path("assets/app.ico").resolve())))
    output = Path("output/native-title-bar")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / "test.db")
        sync_roster(backend.db, dict(termId=551, termNo="P2026169", termName="界面测试班"), [
            dict(student_id="P2026169001A", name="示例学员", status="在读",
                 student_type="新生", nickname="", source="接口学员")])
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        restart = RestartProbe()
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("restartController", restart)
        engine.load(QUrl.fromLocalFile(str(Path("qml/Main.qml").resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        original_flags = window.flags()
        assert not original_flags & Qt.FramelessWindowHint
        window.show()
        theme = NativeTitleBarTheme(window)
        native = sys.platform == "win32" and app.platformName() == "windows"
        if native:
            assert theme.results["light"], theme.results
            getter = ctypes.WinDLL("dwmapi").DwmGetWindowAttribute
            getter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            getter.restype = ctypes.c_long
            value = wintypes.DWORD()
            assert getter(int(window.winId()), 20, ctypes.byref(value), 4) >= 0
            assert value.value == 0
            if sys.getwindowsversion().build >= 22000:
                assert all(theme.results.values()), theme.results
                for attribute, expected in ((35, 0xffffff), (36, 0x473020), (34, 0xebe3dc)):
                    assert getter(int(window.winId()), attribute, ctypes.byref(value), 4) >= 0
                    assert value.value == expected

            # Windows 11 color calls are also checked against a fake ABI on
            # Windows 10, including failure of one optional attribute.
            seen = {}
            def setter(handle, attribute, data, size):
                assert handle == int(window.winId()) and size == 4
                seen[attribute] = ctypes.cast(data, ctypes.POINTER(wintypes.DWORD)).contents.value
                return -2147024809 if attribute == 35 else 0
            class DwmProbe:
                DwmSetWindowAttribute = staticmethod(setter)
            with patch("app.window_theme.ctypes.WinDLL", return_value=DwmProbe()):
                results = apply_native_title_bar_theme(window)
            assert seen == {20: 0, 35: 0xffffff, 36: 0x473020, 34: 0xebe3dc}, seen
            assert not results["background"] and results["text"] and results["border"]
            with patch("app.window_theme.ctypes.WinDLL", side_effect=OSError("unavailable")):
                assert apply_native_title_bar_theme(window) == {}

        toolbar = window.findChild(QQuickItem, "mainToolbar")
        assert toolbar.property("background").property("color") == QColor("#ffffff")
        title = toolbar.findChild(QQuickItem, "appToolbarTitle")
        assert title is not None and title.property("text") == "学员管理"
        for width, height in ((1280, 800), (1000, 700), (720, 480)):
            window.resize(width, height)
            window.setPosition(60, 60)
            window.raise_()
            window.requestActivate()
            QTest.qWait(250)
            selector = window.findChild(QQuickItem, "classSelector")
            title_point = title.mapToScene(title.boundingRect().topLeft())
            selector_point = selector.mapToScene(selector.boundingRect().topLeft())
            assert title_point.x() + title.width() < selector_point.x()
            for name in ("appToolbarTitle", "classSelector", "debugRestartButton"):
                item = window.findChild(QQuickItem, name)
                point = item.mapToScene(item.boundingRect().topLeft())
                assert item.isVisible() and point.x() >= 0
                assert point.x() + item.width() <= width
            assert window.grabWindow().save(str(output / f"content-{width}.png"))
            if native and os.environ.get("NATIVE_FRAME_SCREENSHOTS") == "1":
                capture_native_window(window, output / f"frame-{width}.png")

        if native:
            user32 = ctypes.WinDLL("user32")
            get_style = user32.GetWindowLongW
            get_style.argtypes = [wintypes.HWND, ctypes.c_int]
            get_style.restype = ctypes.c_long
            style = get_style(int(window.winId()), -16)
            # Caption, system menu, resizing, minimize/maximize buttons.
            for flag in (0x00c00000, 0x00080000, 0x00040000, 0x00020000, 0x00010000):
                assert style & flag == flag, hex(style)
            send = user32.SendMessageW
            send.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            send.restype = ctypes.c_ssize_t
            # Restoring a minimized maximized window first returns to maximized.
            for command, state in ((0xf030, Qt.WindowMaximized), (0xf020, Qt.WindowMinimized),
                                   (0xf120, Qt.WindowMaximized), (0xf120, Qt.WindowNoState)):
                send(int(window.winId()), 0x0112, command, 0)
                QTest.qWait(200)
                assert window.windowState() == state, (hex(command), window.windowState(), state)
            other = QWindow()
            other.show()
            other.requestActivate()
            QTest.qWait(100)
            window.requestActivate()
            QTest.qWait(100)
            other.close()
            app.sendEvent(window, QEvent(QEvent.ThemeChange))
            QTest.qWait(50)
            assert theme.results["light"] and window.flags() == original_flags

        # Simulate a busy contact without creating a worker or driving WeCom.
        backend.contactOpener._worker = object()
        backend.contactOpener.changed.emit()
        assert not window.close() and window.isVisible()
        backend.contactOpener._worker = None
        backend.contactOpener.changed.emit()
        assert window.close()
        assert not warnings, warnings
        print("Native title bar OK:", theme.results, "; three sizes, original frame flags, close guard; fictitious data only")


if __name__ == "__main__":
    run()
