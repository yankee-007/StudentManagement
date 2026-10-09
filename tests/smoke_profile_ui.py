"""Manual smoke check with an isolated database; never fetches remote data."""
import tempfile
import os
import json
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from app.backend import Backend
from app.profiles import import_profiles

QQuickStyle.setStyle('Fusion')
app = QApplication([])
with tempfile.TemporaryDirectory() as folder:
    backend = Backend(Path(folder) / 'test.db')
    import_profiles(backend.db, 'C:/Users/AAA/Desktop/学员画像表.xlsx')
    backend.refresh()
    backend.selectRow(0)
    preview_only = bool(os.environ.get('PROFILE_UI_PREVIEW_ONLY'))
    if preview_only:
        backend.workflow.refresh_live()
        assert backend.workflow.visibleCount == 207
        assert backend.workflow.store.batches() == []
    else:
        backend.repo.set_setting('snapshot',json.dumps([{'student_id':r['student_id'],'flags':{'c1':'T','z1':'F'}} for r in backend.repo.list_students()]))
        backend.workflow.createBatch()
        backend.workflow.simulate(True)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(str(item.toString()) for item in items))
    engine.rootContext().setContextProperty('backend',backend)
    engine.rootContext().setContextProperty('studentModel',backend.studentModel)
    engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    window.resize(1280,800)
    window.show()
    assert not window.property('showStudentId')
    from PySide6.QtCore import QObject, QMetaObject, Q_ARG
    table = window.findChild(QObject, 'studentTable')
    steps = [0]
    def exercise():
        steps[0] += 1
        table.setProperty('contentY', (steps[0] * 97) % 3200)
        if steps[0] in (10,20,30):
            backend.workflow.selectRow(steps[0] // 10)
        if steps[0] == 12 and not preview_only:
            backend.workflow.filterRows('pending','')
            backend.workflow.saveDraft(backend.workflow.selected['student_id'],'军训＋考试太忙了')
            assert backend.workflow.submit('军训＋考试太忙了')
        if steps[0] == 25 and not preview_only:
            backend.workflow.markUnreplied()
            backend.workflow.filterRows('all','')
        if steps[0] == 31:
            backend.workflow.sortColumn(4,True)
            backend.workflow.setColumnFilter(1,'notempty','')
        if steps[0] == 34:
            assert QMetaObject.invokeMethod(window,'openColumn',Q_ARG('QVariant',4))
        if steps[0] == 38:
            dialog=window.findChild(QObject,'columnDialog')
            assert dialog.property('visible')
            QMetaObject.invokeMethod(dialog,'close')
            backend.workflow.clearColumnQuery()
        if steps[0] == 39:
            assert QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
            assert backend.profilesModule.total == 207
            assert not window.findChild(QObject,'fetchLearningButton').property('visible')
        if steps[0] == 40:
            backend.profilesModule.selectRow(0)
            assert backend.profilesModule.addField('测试日期','date','',False)
            manager=window.findChild(QObject,'profileFieldManager')
            assert manager is not None
            QMetaObject.invokeMethod(manager,'open')
        if steps[0] == 44:
            manager=window.findChild(QObject,'profileFieldManager')
            assert manager.property('visible')
            QMetaObject.invokeMethod(manager,'close')
            export_dialog=window.findChild(QObject,'profileExportDialog')
            assert export_dialog is not None
            QMetaObject.invokeMethod(export_dialog,'open')
        if steps[0] == 48:
            export_dialog=window.findChild(QObject,'profileExportDialog')
            assert export_dialog.property('visible')
            QMetaObject.invokeMethod(export_dialog,'close')
            QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',0))
            config=window.findChild(QObject,'campaignListDialog')
            assert config is not None
            QMetaObject.invokeMethod(config,'open')
        if steps[0] == 52:
            config=window.findChild(QObject,'campaignListDialog')
            assert config.property('visible')
            QMetaObject.invokeMethod(config,'close')
            QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',4))
            assert backend.groupCenter.createCustom('界面测试','仅界面测试|仅预览，不发送')
            assert backend.groupCenter.prepare('test',{})
            QMetaObject.invokeMethod(window.findChild(QObject,'groupSendPreview'),'open')
        if steps[0] == 56:
            preview=window.findChild(QObject,'groupSendPreview')
            assert preview.property('visible')
            QMetaObject.invokeMethod(preview,'close')
            QMetaObject.invokeMethod(window.findChild(QObject,'customGroupDialog'),'open')
        if steps[0] == 60:
            test_dialog=window.findChild(QObject,'customGroupDialog')
            assert test_dialog.property('visible')
            window.findChild(QObject,'groupCustomTitle').setProperty('text','GUI多字段测试')
        if steps[0] == 64:
            assert QMetaObject.invokeMethod(window.findChild(QObject,'createGroupPlan'),'clicked')
            assert backend.groupCenter.selected['title']=='GUI多字段测试',backend.groupCenter.status
            # 新建群发方案只取名；成员与消息随后手动补。
            assert backend.groupCenter.rows==[]
            assert backend.groupCenter.addNames(backend.groupCenter.selected['id'],['仅界面测试人员'])
            assert backend.groupCenter.addNames(backend.groupCenter.selected['id'],['仅界面测试人员'])['skipped']==['仅界面测试人员']
            timer.stop()
            table.setProperty('contentY', 0)
            if os.environ.get('PROFILE_UI_CAPTURE'):
                QTimer.singleShot(100, lambda: window.grabWindow().save(os.environ['PROFILE_UI_CAPTURE']))
            QTimer.singleShot(200, app.quit)
    timer = QTimer()
    timer.timeout.connect(exercise)
    timer.start(20)
    app.exec()
    assert not warnings, warnings
    print('QML smoke OK: 207-student campaign snapshot, scrolling and selection')
