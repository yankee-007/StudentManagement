"""Isolated UI smoke. TERM_ROSTER_LIVE=1 explicitly enables read-only API QA."""
import os
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QMetaObject, Q_ARG, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from app.backend import Backend
from app.fonts import configure_font

QQuickStyle.setStyle('Fusion')
app = QApplication([])
configure_font(app)
with tempfile.TemporaryDirectory() as folder:
    backend = Backend(Path(folder)/'test.db')
    service = backend.termsModule
    live = bool(os.environ.get('TERM_ROSTER_LIVE'))
    if live:
        service._accept('terms',[dict(termId=551,termNo='P2026169',termName='编程169期')])
    if not live:
        term = dict(termId=551,termNo='P2026169',termName='编程169期')
        service._accept('terms',[term])
        service._request_term=term
        service._accept('lessons',[dict(resource_id='a',label='01【Python核心语法】')])
        service._resource='a'
        service._accept('students',[dict(student_id=f'P2026169{i:03d}D',name=f'测试学员{i}',status='在读',student_type='新生',nickname=f'昵称{i}')
                                    for i in range(1,208) if i not in (3,25,55)])
    engine=QQmlApplicationEngine()
    warnings=[]
    engine.warnings.connect(lambda messages:warnings.extend(m.toString() for m in messages))
    engine.rootContext().setContextProperty('backend',backend)
    engine.rootContext().setContextProperty('studentModel',backend.studentModel)
    engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
    assert engine.rootObjects(), warnings
    window=engine.rootObjects()[0]
    window.resize(1280,800)
    window.show()
    assert QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',2))
    stage=[0]
    failed=[]
    def advance():
        if service.busy: return
        try:
            assert service.visibleCount>0,service.notice
            assert not window.findChild(QObject,'fetchLearningButton').property('visible')
            from PySide6.QtTest import QTest
            from PySide6.QtCore import QPointF, Qt
            combo=window.findChild(QObject,'termLessonBox')
            assert combo.property('visible') and combo.property('enabled')
            point=combo.mapToScene(QPointF(combo.width()/2,combo.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point)
            app.processEvents()
            popup=combo.findChild(QObject,'termLessonPopup')
            assert popup.property('visible'),'Course dropdown did not open'
            QMetaObject.invokeMethod(popup,'close')
            from unittest.mock import patch
            with patch.object(service,'_start') as start:
                service.activate()
                service.selectTerm(0)
                start.assert_not_called()
            print(service.summary)
            table=window.findChild(QObject,'termRosterTable')
            table.setProperty('contentY',2000)
            service.filterRows('缺号补位')
            assert service.visibleCount==3
            service.filterRows('')
            table.setProperty('contentY',0)
            assert QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
            assert backend.profilesModule.total == len(service._rows)
            assert not window.findChild(QObject,'fetchLearningButton').property('visible')
            assert QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',0))
            assert window.findChild(QObject,'fetchLearningButton').property('visible')
            assert backend.workflow.visibleCount == len(service._rows)
            assert not window.property('showStudentId')
            toggle=window.findChild(QObject,'showStudentIdToggle')
            point=toggle.mapToScene(QPointF(toggle.width()/2,toggle.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point)
            app.processEvents()
            assert window.property('showStudentId')
            assert QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',2))
            if os.environ.get('TERM_UI_CAPTURE'):
                QTimer.singleShot(200,lambda:window.grabWindow().save(os.environ['TERM_UI_CAPTURE']))
            timer.stop()
            QTimer.singleShot(400,app.quit)
        except Exception as exc:
            failed.append(str(exc))
            timer.stop()
            app.quit()
    timer=QTimer()
    timer.timeout.connect(advance)
    timer.start(100)
    QTimer.singleShot(60000,app.quit)
    app.exec()
    service.shutdown()
    assert not failed,failed
    assert not timer.isActive(),'Smoke timed out'
    assert not warnings,warnings
    print('Term module QML/process smoke OK' if live else 'Term module QML smoke OK')
    engine.deleteLater()
    app.processEvents()
