"""Disposable GUI integration: no network access or real message sending."""
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from app.backend import Backend
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        b=Backend(Path(folder)/'test.db')
        with b.db.connect() as conn:
            for i,name in enumerate(('张三','李四','王五'),1):
                sid=str(i)
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',(sid,name,'2026-09-28'))
                insert_profile(conn,sid,name,i,{'微信':'是' if i<3 else '', '所在地区':'杭州' if i<3 else '上海'})
        b.refresh()
        engine=QQmlApplicationEngine()
        warnings=[]
        engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]
        window.resize(1250,800);window.show()
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',1))
        QTest.qWait(100)
        module=window.findChild(QObject,'profileModule')
        table=window.findChild(QObject,'profileTable')
        before=table.width()
        module.setProperty('cardExpanded',False)
        QTest.qWait(100)
        assert table.width()>before+200
        module.setProperty('cardExpanded',True)
        filter_dialog=window.findChild(QObject,'profileColumnFilter')
        index=next(i for i,c in enumerate(b.profilesModule.tableModel.columns) if c[0]=='profile:微信')
        QMetaObject.invokeMethod(filter_dialog,'openFor',Q_ARG('QVariant',index))
        QTest.qWait(100)
        assert filter_dialog.property('visible')
        window.grabWindow().save(str(Path(tempfile.gettempdir())/'student-profile-filter-preview.png'))
        QMetaObject.invokeMethod(filter_dialog,'close')
        b.profilesModule.setColumnFilter('profile:微信','values',['是'],'')
        assert b.profilesModule.visibleCount==2
        group_dialog=window.findChild(QObject,'profileGroupDialog')
        QMetaObject.invokeMethod(group_dialog,'open');QTest.qWait(100)
        assert group_dialog.property('visible')
        assert len(group_dialog.property('recordKeys').toVariant())==2
        fields=[dict(type='text',text='{姓名}同学，请查收资料'),dict(type='file',path=str(Path(__file__).resolve())),dict(type='text',text='有问题可以随时联系我')]
        assert b.groupCenter.createFromProfiles('画像筛选测试名单',fields,b.profilesModule.recipientKeys)
        QMetaObject.invokeMethod(group_dialog,'close')
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',4))
        QTest.qWait(150)
        group_table=window.findChild(QObject,'groupRecipientList')
        assert group_table.property('rows')==2
        panel=window.findChild(QObject,'recipientMessages')
        panel.setProperty('selectedRow',b.groupCenter.pendingModel.get(0))
        selected_id=b.groupCenter.pendingModel.get(0)['id']
        assert window.findChild(QObject,'groupColumnMessageDialog') is None
        def visual_item(parent,name):
            if parent.objectName()==name:return parent
            for child in parent.childItems():
                found=visual_item(child,name)
                if found:return found
            return None
        template_input=visual_item(window.contentItem(),'groupDefaultText0')
        template_input.setProperty('text','统一消息-{姓名}')
        save_defaults=window.findChild(QObject,'groupApplyDefaults')
        QMetaObject.invokeMethod(save_defaults,'click');QTest.qWait(100)
        assert not panel.property('defaultsDirty')
        assert all(r['message'].startswith('统一消息-'+r['name']) for r in b.groupCenter.rows)
        selected=panel.property('selectedRow')
        selected=selected.toVariant() if hasattr(selected,'toVariant') else selected
        assert selected['id']==selected_id
        tabs=window.findChild(QObject,'groupMessageTabs')
        tabs.setProperty('currentIndex',1)
        copy_dialog=window.findChild(QObject,'groupCopyBatchDialog')
        QMetaObject.invokeMethod(copy_dialog,'open');QTest.qWait(100)
        title_input=window.findChild(QObject,'groupCopyTitleInput')
        title_input.setProperty('text','UI复制批次')
        copy_button=window.findChild(QObject,'confirmCopyBatch')
        QMetaObject.invokeMethod(copy_button,'click');QTest.qWait(120)
        assert len(b.groupCenter.lists)==2
        assert all(r['state']=='待发送' for r in b.groupCenter.rows)
        assert tabs.property('currentIndex')==0
        first=b.groupCenter.pendingModel.get(0)
        panel.setProperty('selectedRow',first)
        QMetaObject.invokeMethod(panel,'openCellEditor',Q_ARG('QVariant',first),Q_ARG('QVariant',0));QTest.qWait(100)
        single_dialog=window.findChild(QObject,'groupSingleCellDialog')
        assert single_dialog.property('visible')
        single_text=window.findChild(QObject,'groupSingleCellText')
        single_text.setProperty('text','只改这一格')
        QMetaObject.invokeMethod(window.findChild(QObject,'saveGroupSingleCell'),'click');QTest.qWait(100)
        assert not single_dialog.property('visible')
        assert b.groupCenter.rows[0]['message'].startswith('只改这一格')
        assert b.groupCenter.rows[1]['message'].startswith('统一消息-')
        panel.setProperty('selectedRow',b.groupCenter.pendingModel.get(0))
        QMetaObject.invokeMethod(panel,'openEditor');QTest.qWait(100)
        editor=window.findChild(QObject,'recipientMessageEditor')
        assert editor.property('visible') and editor.property('canEdit')
        QMetaObject.invokeMethod(editor,'close')
        window.grabWindow().save(str(Path(tempfile.gettempdir())/'student-group-table-preview.png'))
        row=b.groupCenter.rows[0]
        with b.groupCenter.store.connect() as conn:
            conn.execute("UPDATE recipients SET state='已发送' WHERE id=?",(row['id'],))
        b.groupCenter.refresh()
        tabs.setProperty('currentIndex',1);QTest.qWait(100)
        assert group_table.property('rows')==1
        panel.setProperty('selectedRow',b.groupCenter.sentModel.get(0))
        QMetaObject.invokeMethod(panel,'openEditor');QTest.qWait(100)
        assert not editor.property('canEdit')
        QMetaObject.invokeMethod(editor,'close')
        window.close();app.processEvents()
        assert not warnings,warnings
        print('Group center selection, tabs, unified default row and cell editors, batch copy and read-only sent tab: OK')


if __name__=='__main__':run()
