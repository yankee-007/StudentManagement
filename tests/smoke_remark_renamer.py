"""Offscreen GUI smoke check for the remark revision module.

No enterprise-WeChat window, no search, no rename: only the QML page, the Sixth
header entry and the persisted scope are exercised.
"""
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from app.backend import Backend
from app import remark_storage as storage
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        b=Backend(Path(folder)/'test.db')
        b.workflow._classes[b.workflow.class_index]['term_no']='P2026175'
        with b.db.connect() as conn:
            for i,(sid,name) in enumerate((('P2026175001A','张三'),('P2026175002A','李四'),('P2026175003A','王五')),1):
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',(sid,name,'2026-09-30'))
                insert_profile(conn,sid,name,i,{'微信':'是' if i<3 else '否','所在地区':'杭州'})
        storage.save_scan(b.db,'P2026175001A',observed='py175张三',desired='py175张三',state='已符合',detail='当前备注已包含目标格式')
        storage.save_scan(b.db,'P2026175002A',observed='李四/新生',desired='py175李四',state='',detail='')
        b.refresh()
        renamer=b.remarkRenamer
        # The backend builds this module before the term binding is aligned: the
        # prefix must appear without restarting the app.
        assert renamer.prefix=='' or renamer.prefix=='py175',renamer.prefix
        renamer.reload()
        assert renamer.prefix=='py175',renamer.prefix
        assert renamer.total==2,f'只应包含微信=是的学员：{renamer.total}'
        assert renamer.compliantCount==1 and renamer.pendingCount==1,(renamer.compliantCount,renamer.pendingCount)
        engine=QQmlApplicationEngine()
        warnings=[]
        engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]
        window.resize(1280,820);window.show()
        QMetaObject.invokeMethod(window,'switchModule',Q_ARG('QVariant',5))
        QTest.qWait(200)
        page=window.findChild(QObject,'remarkRenamerPage')
        assert page is not None,'缺少备注批改页面'
        table=window.findChild(QObject,'remarkTable')
        assert table is not None and table.property('rows')==2,table
        assert window.findChild(QObject,'remarkPrefixInput').property('text')=='py175'
        assert window.findChild(QObject,'remarkStartButton').property('enabled') is True
        assert window.findChild(QObject,'remarkForceButton').property('enabled') is False
        assert window.findChild(QObject,'remarkRetryButton').property('enabled') is False
        # Selecting a row marks it for the strong rewrite without starting anything.
        QMetaObject.invokeMethod(renamer,'selectRow',Q_ARG(int,1))
        revision=page.property('pickedRevision') if page.property('pickedRevision') is not None else renamer.property('pickRevision')
        page.setProperty('pickedKeys',[])
        QMetaObject.invokeMethod(page,'togglePick',Q_ARG('QVariant','P2026175002A'),Q_ARG('QVariant',True))
        QTest.qWait(60)
        assert renamer.property('pickRevision')>=1,'选中标记未触发重绘'
        assert page.property('pickedKeys') is not None
        assert window.findChild(QObject,'remarkForceButton').property('enabled') is True
        window.grabWindow().save(str(Path(tempfile.gettempdir())/'student-remark-renamer-preview.png'))
        dialog=window.findChild(QObject,'remarkStartDialog')
        QMetaObject.invokeMethod(dialog,'open');QTest.qWait(120)
        assert dialog.property('visible')
        assert not renamer.active,'打开确认对话框不得启动桌面自动化'
        QMetaObject.invokeMethod(dialog,'close')
        assert not window.findChild(QObject,'remarkForceDialog').property('visible')
        # Switching class from the header must re-read this module's roster and prefix.
        from app.database import Database
        other=Database(Path(folder)/'class_other.db')
        with other.connect() as conn:
            conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',('P2026169001A','别班学员','2026-09-30'))
            insert_profile(conn,'P2026169001A','别班学员',1,{'微信':'是'})
        b.workflow._classes.append({'name':'编程169期','path':str(other.path),'term_id':'551','term_no':'P2026169'})
        b.workflow.changed.emit();QTest.qWait(60)
        # Same slot the header class selector invokes (the overlay only wraps its timing).
        b.workflow.selectClass(1)
        QTest.qWait(200)
        assert str(b.db.path)==str(other.path),b.db.path
        assert renamer.prefix=='py169',renamer.prefix
        assert table.property('rows')==1,table.property('rows')
        assert window.findChild(QObject,'remarkPrefixInput').property('text')=='py169'
        assert renamer.rows[0]['name']=='别班学员',renamer.rows
        window.grabWindow().save(str(Path(tempfile.gettempdir())/'student-remark-renamer-class-switch.png'))
        window.close();app.processEvents()
        assert not warnings,warnings
        print('Remark revision page, prefix default, scope filter, selection, confirm dialogs and class switch: OK')


if __name__=='__main__':run()
