from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from app.backend import Backend
from app.fonts import configure_font
from app.restart import RestartController


def main() -> int:
    if sys.platform == "win32":
        import ctypes

        # Give the taskbar our own identity instead of the Python host's icon.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "LocalTools.StudentManagement"
        )
    # Fusion supports the customized QML control backgrounds used by the UI.
    QQuickStyle.setStyle("Fusion")
    # QFileDialog is a QWidget, so this must be QApplication rather than
    # QGuiApplication.
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "app.ico")))
    configure_font(app)
    app.setOrganizationName("LocalTools")
    app.setApplicationName("学员催办维护名单")
    engine = QQmlApplicationEngine()
    backend = Backend()
    restart = RestartController(__file__, sys.argv[1:], app)
    engine.rootContext().setContextProperty("restartController", restart)
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("studentModel", backend.studentModel)
    engine.load(Path(__file__).parent.joinpath("qml", "Main.qml"))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    restart.window = window
    primary_screen = app.primaryScreen()
    if primary_screen is not None:
        available = primary_screen.availableGeometry()
        width = round(available.width() * 0.9)
        height = round(available.height() * 0.9)
        window.setScreen(primary_screen)
        window.setMinimumWidth(min(720, width))
        window.setMinimumHeight(min(480, height))
        window.setGeometry(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
            width,
            height,
        )
    window.show()
    result = app.exec()
    if restart.requested and not restart.start_helper():
        QMessageBox.critical(None, '重启失败', '无法启动重启助手，请从原启动入口重新运行程序。')
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
