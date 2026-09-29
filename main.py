from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font


def main() -> int:
    # Fusion supports the customized QML control backgrounds used by the UI.
    QQuickStyle.setStyle("Fusion")
    # QFileDialog is a QWidget, so this must be QApplication rather than
    # QGuiApplication.
    app = QApplication(sys.argv)
    configure_font(app)
    app.setOrganizationName("LocalTools")
    app.setApplicationName("学员催办维护名单")
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("studentModel", backend.studentModel)
    engine.load(Path(__file__).parent.joinpath("qml", "Main.qml"))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    primary_screen = app.primaryScreen()
    if primary_screen is not None:
        available = primary_screen.availableGeometry()
        width = round(available.width() * 0.8)
        height = round(available.height() * 0.8)
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
