"""Verify a loading frame is presented before synchronous class loading."""
import os
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QObject, QMetaObject, Q_ARG, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.database import Database
from app.fonts import configure_font


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'first.db')
        other = Database(Path(folder) / 'second.db')
        b.workflow._classes = [dict(name='测试甲班', path=str(b.db.path), term_id=1),
                               dict(name='测试乙班', path=str(other.path), term_id=2)]
        terms = [dict(termId=i, termNo=f'P2026{i:03d}', termName=name) for i, name in ((1,'测试甲班'),(2,'测试乙班'))]
        b.termsModule._terms = terms
        for term in terms:
            b.termsModule.store.save_lessons(term['termId'], [dict(resource_id='a', label='第1节')], 'a')
            b.termsModule.store.save(term, [], 'a')
        b.termsModule.alignTerm(1)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 800)
        window.show()
        QTest.qWait(100)
        frames = []
        window.frameSwapped.connect(lambda: frames.append(time.monotonic()))
        original_refresh = b.refresh
        checks = []
        expected = {}

        def refresh():
            popup = expected['popup']
            overlays = window.findChildren(QObject, 'classSwitchOverlay')
            active = [item for item in overlays if item.property('visible')]
            assert not popup.property('visible')
            assert len(active) == 1
            assert len(frames) > expected['frames']
            assert expected['name'] in active[0].property('targetName')
            window.grabWindow().save(str(Path(tempfile.gettempdir()) / f'class-switch-{window.width()}.png'))
            time.sleep(.15)  # Stand in for a slow disk without touching real data.
            original_refresh()
            checks.append(True)

        b.refresh = refresh
        for module, selector, index, name, width in ((0, 'classSelector', 1, '测试乙班', 1280),
                                                    (2, 'termClassSelector', 0, '测试甲班', 960)):
            window.resize(width, 720)
            QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', module))
            QTest.qWait(50)
            combo = window.findChild(QQuickItem, selector)
            popup = window.findChild(QObject, selector + 'Popup')
            QMetaObject.invokeMethod(popup, 'open')
            QTest.qWait(80)
            expected.update(popup=popup, frames=len(frames), name=name)
            old_index = b.workflow.classIndex
            QMetaObject.invokeMethod(combo, 'activated', Q_ARG(int, index))
            assert b.workflow.classIndex == old_index
            deadline = time.monotonic() + 3
            while any(item.property('visible') for item in window.findChildren(QObject, 'classSwitchOverlay')) and time.monotonic() < deadline:
                QTest.qWait(20)
            assert b.workflow.classIndex == index
            assert not any(item.property('visible') for item in window.findChildren(QObject, 'classSwitchOverlay'))
        assert len(checks) == 2
        # Closing before the loading frame cancels the deferred operation.
        combo = window.findChild(QQuickItem, 'termClassSelector')
        QMetaObject.invokeMethod(combo, 'activated', Q_ARG(int, 1))
        window.close()
        QTest.qWait(80)
        assert b.workflow.classIndex == 0
        assert not warnings, warnings
        print('Class switch UI OK: popup dismissed, loading frame first, both selectors, close cancellation')


if __name__ == '__main__':
    run()
