"""Exercise the shared editor and drag sorting in disposable QML windows."""
import tempfile
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from app.backend import Backend
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder)/'test.db')
        with b.db.connect() as conn:
            conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','张三','2026-09-27')")
            insert_profile(conn,'001','张三',1)
        b.refresh()
        engine = QQmlApplicationEngine()
        warnings=[]
        engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]
        window.resize(1100,750); window.show()
        assert not window.findChild(QObject,'learningOverviewPage').property('visible')
        b.workflow.createBatch()
        export_dialog=window.findChild(QObject,'campaignExportDialog')
        QMetaObject.invokeMethod(export_dialog,'open'); QTest.qWait(100)
        assert export_dialog.property('visible')
        keys=export_dialog.property('selectedKeys').toVariant()
        assert 'name' in keys and 'feedback' in keys
        QMetaObject.invokeMethod(export_dialog,'close')
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
        QTest.qWait(100)

        references=[]
        def visual(item, predicate):
            references.append(item)
            if predicate(item):return item
            for child in item.childItems():
                result=visual(child,predicate)
                if result is not None:return result

        def field(win,label):
            return visual(win.contentItem(),lambda i:i.property('caption')==label)

        def input_for(win,label):
            return field(win,label).findChild(QObject,'profileInput')

        region=input_for(window,'所在地区')
        region.forceActiveFocus(); region.setProperty('text','杭州')
        QTest.keyClick(window,Qt.Key_Return)
        app.processEvents()
        assert b.repo.get('001')['profile_fields']['所在地区']=='杭州'
        assert input_for(window,'学习目的').property('activeFocus')

        with patch('app.contact_opener.ContactOpenTask') as task:
            window.findChild(QObject,'profileContactPrefix').setProperty('text','py169')
            assert QMetaObject.invokeMethod(window.findChild(QObject,'openProfileContact'),'clicked')
            assert task.call_args.args[0]=='py169张三'
            assert b.contactOpener.active
            b.contactOpener._finished()

        manager=window.findChild(QObject,'profileFieldManager')
        QMetaObject.invokeMethod(manager,'open'); QTest.qWait(100)
        order=window.findChild(QObject,'profileFieldOrder')
        handle=visual(order,lambda i:i.objectName()=='fieldDragHandle' and i.parentItem().parentItem().parentItem().property('index')==0)
        assert handle is not None
        start=handle.mapToScene(QPointF(handle.width()/2,handle.height()/2)).toPoint()
        finish=start+QPointF(0,84).toPoint()
        original=b.profilesModule.managedFields[0]['field_id']
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(window,finish,100)
        QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,finish)
        app.processEvents()
        assert b.profilesModule.managedFields[2]['field_id']==original
        QMetaObject.invokeMethod(manager,'close')

        c=b.profileCompanion
        c._active_wecom_title=lambda:'张三'
        c.refreshContact()
        floating=window.findChild(QObject,'profileFloatingWindow')
        floating.show(); QTest.qWait(100)
        assert field(floating,'所在地区') is not None
        input_for(floating,'所在地区').forceActiveFocus()
        input_for(floating,'所在地区').setProperty('text','苏州')
        QTest.keyClick(floating,Qt.Key_Return)
        app.processEvents()
        assert b.profilesModule.selected['profile_fields']['所在地区']=='苏州'
        assert input_for(floating,'学习目的').property('activeFocus')
        floating.setProperty('pinned',False); app.processEvents()
        assert floating.isVisible()
        b.profilesModule.setFieldVisible('column:profile:QQ',False)
        app.processEvents()
        assert field(floating,'QQ') is None and field(window,'QQ') is None
        floating.close(); window.close(); app.processEvents()
        assert not warnings,warnings
        print('Shared profile UI OK: Return navigation, contact action, drag sorting, floating edits, visibility, pinning, export fields, collapsed dashboard')


if __name__=='__main__':run()
