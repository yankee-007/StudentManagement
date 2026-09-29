"""Exercise the restart button with a disposable database; never relaunch main.py."""
from pathlib import Path
import os
import tempfile

from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.restart import RestartController


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / 'test.db')
        restart = RestartController(Path('main.py'))
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', backend)
        engine.rootContext().setContextProperty('studentModel', backend.studentModel)
        engine.rootContext().setContextProperty('restartController', restart)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        window = engine.rootObjects()[0]
        restart.window = window
        window.show()
        button = window.findChild(QQuickItem, 'debugRestartButton')
        for width, height in ((1280, 800), (960, 640)):
            window.resize(width, height)
            app.processEvents()
            assert button.property('visible') and button.property('enabled')
            window.grabWindow().save(str(Path(tempfile.gettempdir()) / f'restart-ui-{width}.png'))
        backend._busy = True
        backend.busyChanged.emit()
        app.processEvents()
        assert not button.property('enabled')
        backend._busy = False
        backend.busyChanged.emit()
        app.processEvents()
        assert button.property('enabled')
        QMetaObject.invokeMethod(button, 'clicked')
        app.processEvents()
        assert restart.requested and not window.isVisible()
        assert not warnings, warnings
        print('Restart UI OK: button, busy guard, normal close; screenshots in temporary directory')


if __name__ == '__main__':
    run()
