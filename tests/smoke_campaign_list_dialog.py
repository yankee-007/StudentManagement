"""Verify the real list dialog, field selection and message edits using fake data."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from app.fonts import configure_font
from app.importer import import_rows
from tests.test_business_logic import seeded, merged_row


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output=Path('output/workbench-optimization'); output.mkdir(parents=True,exist_ok=True)
    with seeded(8) as b:
        import_rows(b.db,[merged_row(i) for i in range(1,9)])
        w=b.workflow; w.createBatch(); first=w._batch
        w.store.save_feedback(first,'P2026169001A','约定下周补齐作业')
        w.createBatch()
        engine=QQmlApplicationEngine(); warnings=[]
        engine.warnings.connect(lambda entries:warnings.extend(i.toString() for i in entries))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]; window.resize(1280,800); window.show(); QTest.qWait(100)
        def item(name):
            result=window.findChild(QObject,name); assert result is not None,name
            return result
        def click(name):
            control=item(name)
            pos=control.mapToScene(QPointF(control.property('width')/2,control.property('height')/2)).toPoint()
            assert 0<=pos.x()<window.width() and 0<=pos.y()<window.height(),(name,pos)
            QTest.mouseClick(window,Qt.LeftButton,pos=pos); QTest.qWait(35)
        dialog=item('campaignListDialog')
        click('createCampaignList')
        assert dialog.property('visible') and len(dialog.property('recordKeys').toVariant())==8
        fields=item('campaignMessageFields')
        fields.insertVariable('欠作业'); app.processEvents()
        assert '{欠作业}' in fields.values().toVariant()[0]['text']
        fields.load([{'type':'text','text':'{姓名}同学，你好！请补齐第 1 节课作业，有困难可以回复我。'},
                     {'type':'text','text':'本次欠交作业：{欠作业}。'}])
        QTest.qWait(50)
        assert window.grabWindow().save(str(output/'list-messages-light.png'))
        item('campaignListTitle').setProperty('text','')
        assert not item('createCampaignSelection').property('enabled')
        item('campaignListTitle').setProperty('text','虚构消息名单')
        click('createCampaignSelection')
        assert window.property('moduleIndex')==4 and len(b.groupCenter.rows)==8
        assert len(json.loads(b.groupCenter.rows[0]['content']))==2 and not b.groupCenter.active
        window.switchModule(0); dialog.open(); QTest.qWait(60)
        click('campaignNamesOnly'); assert window.grabWindow().save(str(output/'list-names-light.png'))
        window.resize(720,480); b.settingsModule.setAppearanceMode('dark'); QTest.qWait(80)
        assert window.grabWindow().save(str(output/'list-names-dark-720.png'))
        click('campaignMessagesMode'); QTest.qWait(35)
        fields.load([{'type':'text','text':'长内容\n'*30},{'type':'text','text':'第二条消息'}])
        QTest.qWait(50)
        assert item('campaignMessageScroll').property('height') >= 100
        button=item('createCampaignSelection')
        assert button.mapToScene(QPointF(0,button.property('height'))).y()<=window.height()
        assert window.grabWindow().save(str(output/'list-messages-dark-720.png'))
        click('campaignNamesOnly'); click('createCampaignSelection')
        assert all(not json.loads(row['content']) for row in b.groupCenter.rows) and not b.groupCenter.active
        window.resize(1280,800); b.settingsModule.setAppearanceMode('light'); window.switchModule(0)
        manager=item('campaignFieldDialog'); manager.open(); QTest.qWait(50)
        key=f'previous_feedback_{first}'
        assert w.moveField(key,8)
        click('campaignLocateHistory')
        def visual(node,predicate):
            if predicate(node):return node
            for child in node.childItems():
                found=visual(child,predicate)
                if found is not None:return found
        history=visual(manager.property('contentItem'),lambda obj:obj.objectName()=='profileFieldRow' and obj.property('index')==8)
        assert history is not None
        check=visual(history,lambda obj:obj.objectName()=='fieldVisibility')
        assert check is not None and check.property('enabled') and not check.property('checked')
        pos=check.mapToScene(QPointF(check.width()/2,check.height()/2)).toPoint()
        QTest.mouseClick(window,Qt.LeftButton,pos=pos); QTest.qWait(50)
        assert check.property('checked')
        QTest.qWait(60)
        assert window.grabWindow().save(str(output/'history-fields-light.png'))
        assert w.selected[key]=='约定下周补齐作业'
        manager.close(); dialog.open(); QTest.qWait(50)
        w.filterRows('all','学员2')
        click('createCampaignSelection')
        assert dialog.property('visible') and dialog.property('generationError')
        assert not b.groupCenter.active
        dialog.close()
        assert not warnings,warnings
        window.hide(); engine.deleteLater(); app.processEvents()
    print('Campaign list dialog QML OK: message/names modes, variables, ordered messages, history field controls, light/dark, 720x480, no sending.')


if __name__=='__main__': run()
