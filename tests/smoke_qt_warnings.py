"""Global Qt diagnostics and shared term action, using only disposable data."""
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6.QtCore import QObject, QMetaObject, Q_ARG, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.restart import RestartController


def run():
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, text: messages.append((context.category, text)))
    try:
        QQuickStyle.setStyle('Fusion')
        app = QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
        configure_font(app)
        with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
            backend = Backend(Path(folder) / 'test.db')
            service = backend.termsModule
            term = dict(termId=551, termNo='P2026169', termName='界面测试班')
            service._accept('terms', [term]); service._request_term = term
            service._accept('lessons', [dict(resource_id='a', label='01【测试课程】')])
            service._resource = 'a'
            service._accept('students', [dict(student_id='P2026169001D', name='测试学员', status='在读', student_type='新生', nickname='')])
            backend.groupCenter.createStructured('测试群发', '测试甲\n测试乙', [dict(type='text', text='你好 {姓名}')])
            engine = QQmlApplicationEngine()
            qml_warnings = []
            engine.warnings.connect(lambda items: qml_warnings.extend(item.toString() for item in items))
            engine.rootContext().setContextProperty('backend', backend)
            engine.rootContext().setContextProperty('studentModel', backend.studentModel)
            engine.rootContext().setContextProperty('restartController', RestartController(Path('main.py'), parent=backend))
            with patch.object(service, '_start') as start:
                engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
                assert engine.rootObjects(), qml_warnings
                window = engine.rootObjects()[0]
                window.show()
                button = window.findChild(QQuickItem, 'refreshTermRosterButton')
                selector = window.findChild(QQuickItem, 'classSelector')
                output = Path('output/qt-warnings'); output.mkdir(parents=True, exist_ok=True)
                for theme in ('light', 'dark'):
                    backend.settingsModule.setAppearanceMode(theme)
                    for width, height in ((1280, 800), (960, 640), (720, 480)):
                        window.resize(width, height)
                        for module in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                            assert QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', module))
                            QTest.qWait(60)
                            assert button.isVisible() == selector.isVisible(), module
                            assert button.isEnabled() == selector.isEnabled(), module
                            if button.isVisible():
                                assert button.isEnabled()
                                a = selector.mapToScene(QPointF(0, 0)); b = button.mapToScene(QPointF(0, 0))
                                assert abs(b.x() - a.x() - selector.width() - 14) < 1
                                assert abs(a.y() - b.y()) < 1
                                assert b.x() + button.width() <= width - 18
                                start.reset_mock()
                                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint())
                                start.assert_called_once_with('terms')
                                service._force_roster = False
                            if module in (1, 2):
                                assert window.grabWindow().save(str(output / f'{module}-{theme}-{width}.png'))
                for owner, signal in ((service, service.changed), (backend, backend.busyChanged), (backend.liveAbsence, backend.liveAbsence.activityChanged)):
                    owner._busy = True; signal.emit(); app.processEvents()
                    assert not button.isEnabled()
                    start.reset_mock()
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint())
                    start.assert_not_called()
                    owner._busy = False; signal.emit(); app.processEvents()
                assert not window.findChild(QObject, 'groupClipboardBridge')
                assert QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 4))
                panel = window.findChild(QObject, 'recipientMessages')
                original_names = [row['name'] for row in backend.groupCenter.rows]
                with patch('app.clipboard.read_text', side_effect=ValueError('剪贴板正被其他程序占用，请稍后重试。')):
                    assert QMetaObject.invokeMethod(panel, 'pasteFromClipboard')
                assert [row['name'] for row in backend.groupCenter.rows] == original_names
                assert '稍后重试' in panel.property('actionNotice')
                assert not qml_warnings, qml_warnings
                assert not [text for category, text in messages if 'recursive rearrange' in text or 'CreateFontFaceFromHDC() failed' in text], messages
                service.shutdown()
                import shiboken6
                shiboken6.delete(engine); shiboken6.delete(backend)
        print('Qt warning smoke OK: startup, 54 theme/size/module combinations, shared term refresh clicks and busy guards')
    finally:
        qInstallMessageHandler(previous)


if __name__ == '__main__':
    run()
