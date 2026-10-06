"""Match the native Windows frame to the QML theme without replacing it."""
import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QEvent, QObject, QTimer, Slot
from PySide6.QtGui import QColor, QGuiApplication


def apply_native_title_bar_theme(window):
    """Return per-attribute support; older Windows keeps its native light frame."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return {}
    try:
        setter = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
    except (OSError, AttributeError):
        return {}
    # HWND must remain pointer-sized on 64-bit Windows.
    setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    setter.restype = ctypes.c_long
    attributes = [("light", 20, 0)]  # DWMWA_USE_IMMERSIVE_DARK_MODE = FALSE
    for name, attribute, property_name in (
        ("background", 35, "nativeTitleBarBackground"),
        ("text", 36, "nativeTitleBarText"),
        ("border", 34, "nativeTitleBarBorder"),
    ):
        color = QColor(window.property(property_name))
        if color.isValid():
            # Win32 COLORREF is 0x00BBGGRR, rather than Qt's ARGB.
            value = color.red() | (color.green() << 8) | (color.blue() << 16)
            attributes.append((name, attribute, value))
    handle = int(window.winId())
    results = {}
    for name, attribute, value in attributes:
        data = wintypes.DWORD(value)
        result = setter(handle, attribute, ctypes.byref(data), ctypes.sizeof(data))
        # Windows 10 rejects the explicit colors with E_INVALIDARG. This is
        # optional decoration: an unsupported attribute must not block startup.
        results[name] = result >= 0
    return results


class NativeTitleBarTheme(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.results = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply)
        window.installEventFilter(self)
        window.activeChanged.connect(self.apply)
        window.visibleChanged.connect(self.apply)
        self.apply()

    @Slot()
    def apply(self):
        if self.window.isVisible():
            self.results = apply_native_title_bar_theme(self.window)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.ThemeChange, QEvent.Type.WinIdChange):
            self.timer.start(0)
        return False
