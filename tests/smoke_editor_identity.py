"""Exercise real QML editor reuse against disposable class databases."""
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickItem
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from app.backend import Backend
from app.database import Database
from app.roster_sync import sync_roster


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        b=Backend(Path(directory)/'first.db')
        term=dict(termId=551,termNo='P2026169',termName='测试班')
        students=[dict(student_id=f'P2026169{i:03d}A',name=f'学员{i}',status='在读',student_type='新生',nickname='',source='接口学员') for i in (1,2)]
        sync_roster(b.db,term,students)
        ids=[s['student_id'] for s in students]
        for sid,value in zip(ids,('甲地','乙地')):
            b.repo.update_profile_field(sid,'所在地区',value)
        b.refresh()
        engine=QQmlApplicationEngine()
        warnings=[]
        engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        window=engine.rootObjects()[0]
        window.show()
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
        app.processEvents()

        references=[]
        def field(label):
            def walk(item):
                references.append(item)
                if item.property('caption')==label:return item
                for child in item.childItems():
                    found=walk(child)
                    if found is not None:return found
            return walk(window.contentItem())

        def value(sid,label):return b.repo.get(sid)['profile_fields'][label]
        def choose(label,index):
            control=field(label).findChild(QObject,'profileChoice')
            control.setProperty('currentIndex',index)
            assert QMetaObject.invokeMethod(control,'activated',Q_ARG(int,index))
            app.processEvents()

        choose('微信',1)
        assert value(ids[0],'微信')=='是'
        old_key=b.profilesModule.selected['_record_key']
        area=field('所在地区').findChild(QQuickItem,'profileInput')
        area.forceActiveFocus()
        area.setProperty('text','修改甲地')
        assert value(ids[0],'所在地区')=='修改甲地'
        b.profilesModule.selectRow(1)
        app.processEvents()
        assert field('微信').property('ownerId')==ids[1]
        assert field('微信').findChild(QObject,'profileChoice').property('currentIndex')==0
        assert field('所在地区').findChild(QObject,'profileInput').property('text')=='乙地'
        assert value(ids[0],'所在地区')=='修改甲地'
        choose('微信',2)
        assert value(ids[1],'微信')=='否' and value(ids[0],'微信')=='是'
        area=field('所在地区').findChild(QQuickItem,'profileInput')
        area.forceActiveFocus(); area.setProperty('text','修改乙地')
        assert value(ids[1],'所在地区')=='修改乙地'
        assert not b.profilesModule.saveEditorField(old_key,'微信','否')
        b.profilesModule.selectRow(0); app.processEvents()
        assert field('微信').findChild(QObject,'profileChoice').property('currentIndex')==1
        b.profilesModule.refresh(); app.processEvents()
        assert value(ids[0],'所在地区')=='修改甲地'
        b.profilesModule.setAllClasses(True)
        assert not b.profilesModule.saveEditorField(old_key,'微信','否')
        b.profilesModule.setAllClasses(False)

        w=b.workflow
        for sid in ids:b.repo.update_profile_field(sid,'微信','是')
        b.repo.set_setting('snapshot',json.dumps([dict(student_id=sid,flags={'c1':'T','z1':'F'}) for sid in ids]))
        w.createBatch(); w.simulate(False); w.selectRow(0)
        assert w.dashboard['total']==2
        assert w.dashboard['courses'][0]['completedRate']=='100.00%'
        before_dashboard=w.dashboard
        w.filterRows('all','不存在的学员')
        assert w.dashboard==before_dashboard
        w.filterRows('all','')
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',0))
        app.processEvents()
        # Reorderable detail fields are visual Repeater children, not QObject children.
        def named_item(item,name):
            references.append(item)
            if item.objectName()==name:return item
            for child in item.childItems():
                found=named_item(child,name)
                if found is not None:return found
        draft=named_item(window.contentItem(),'feedbackDraft')
        assert draft is not None
        draft.forceActiveFocus(); draft.setProperty('text','界面甲草稿')
        assert w.store.rows(w._batch,ids[0])[0]['draft']=='界面甲草稿'
        w.selectRow(1); app.processEvents()
        assert draft.property('text')==''
        assert w.store.rows(w._batch,ids[0])[0]['draft']=='界面甲草稿'
        draft.forceActiveFocus(); draft.setProperty('text','界面乙草稿')
        assert w.store.rows(w._batch,ids[1])[0]['draft']=='界面乙草稿'
        w.selectRow(0)
        token=w.editorKey
        assert w.saveEditorValue(token,'draft','甲的反馈')
        assert w.saveEditorValue(token,'remark','新备注')
        w.selectRow(1)
        assert not w.saveEditorValue(token,'draft','错人草稿')
        assert not w.saveEditorValue(token,'submit','错人反馈')
        assert not w.saveEditorValue(token,'remark','错人备注')
        w.selectRow(0)
        assert w.contactRemark=='新备注'
        assert w.selected['draft']=='甲的反馈'
        b.chooseDate=lambda current:(w.selectRow(1) or '2099-01-01')
        w.setLeave()
        assert all(b.repo.get(sid)['status']=='正常' for sid in ids)
        w.selectRow(0); token=w.editorKey
        w.createBatch()
        assert not w.saveEditorValue(token,'draft','错批次草稿')
        w.selectBatch(1)
        app.processEvents()
        assert not window.findChild(QQuickItem,'fetchLearningButton').property('visible')
        b.repo.set_setting('snapshot',json.dumps([dict(student_id=sid,flags={'c1':'F','z1':'T'}) for sid in ids]))
        w.refresh_live()
        assert w.dashboard['courses'][0]['pendingRate']=='0.00%'
        assert w.dashboard['homework'][0]['completedRate']=='0.00%'
        assert w.selected['courses']==''  # Historical learning snapshot stays frozen.
        w.createBatch()
        assert w.dashboard['courses'][0]['pendingRate']=='100.00%'
        assert w.dashboard['homework'][0]['completedRate']=='100.00%'
        assert w.dashboard['courses'][0]['difference']=='-100.00%'
        from app.campaigns import CampaignStore
        reopened=CampaignStore(Database(b.db.path),b.repo)
        assert reopened.dashboard(w._batch)==w.dashboard
        with b.db.connect() as conn:
            conn.execute('DELETE FROM campaign_dashboards WHERE batch_id=?',(w._batch,))
        w.refresh_live()
        assert not w.dashboard['available'] and '无法准确还原' in w.dashboard['notice']

        # Same ID in another class must not accept an old editor token.
        second=Database(Path(directory)/'second.db')
        sync_roster(second,term,students)
        w._classes.append(dict(name='另一个班',path=str(second.path)))
        old_key=b.profilesModule.selected['_record_key']
        w.selectClass(len(w._classes)-1); app.processEvents()
        assert w.dashboard['matched']==0 and w.dashboard['courses']==[]
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
        app.processEvents()
        assert not b.profilesModule.saveEditorField(old_key,'微信','是')
        assert value(ids[0],'微信')==''
        choose('微信',2)
        assert value(ids[0],'微信')=='否'
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',3))
        app.processEvents()
        assert window.findChild(QQuickItem,'completionUsername').property('visible')
        assert window.findChild(QQuickItem,'completionPassword').property('visible')
        assert window.findChild(QQuickItem,'homeworkPassword').property('visible')
        assert not warnings,warnings
        window.close()
        b._date_timer.stop()
        print('Editor identity OK: selection, focus, reload, dropdown, class, batch, draft, leave')


if __name__=='__main__':run()
