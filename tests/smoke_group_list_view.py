"""Recipient/message list alignment and editing; disposable data, no sending."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QFontDatabase, QWheelEvent, QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app import sending_store as receipts


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder, patch('app.wecom_sender.WeComSender') as driver:
        b = Backend(Path(folder)/'test.db'); g = b.groupCenter
        attachment = Path(folder)/'学习资料.txt'; attachment.write_text('界面测试', encoding='utf-8')
        assert g.createStructured('消息列表验证', '\n'.join('验证学员%02d'%i for i in range(60)), [
            dict(type='text', text='{姓名}，第一条消息'), dict(type='file', path=str(attachment)),
            dict(type='text', text='第二段\n下一行')])
        list_id = g.selected['id']
        personal_id = g.rows[12]['id']
        assert g.saveRecipientContent(list_id, personal_id, [dict(type='text', text='个人消息'+('很长的消息内容'*120))])
        engine = QQmlApplicationEngine(); warnings = []
        engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]; window.resize(1250,800); window.show(); QTest.qWait(100)

        def item(name):
            def visual(parent):
                if parent.objectName()==name: return parent
                for child in parent.childItems():
                    found = visual(child)
                    if found is not None: return found
            result = window.findChild(QObject,name)
            if result is None: result = visual(window.contentItem())
            assert result is not None, name
            return result

        def invoke(obj, method, *args):
            assert QMetaObject.invokeMethod(obj,method,*[Q_ARG('QVariant',arg) for arg in args])
            QTest.qWait(80)

        def click(name): invoke(item(name),'click')
        invoke(window,'switchModule',4)
        panel=item('recipientMessages'); names=item('groupNamesTable'); messages=item('groupRecipientMessageList')
        chat=item('groupMessageChat')

        def top(obj): return obj.mapToScene(QPointF(0,0)).y()
        def geometry():
            result=[]
            for name in ('groupRecipientsPanel','groupTemplatePanel','groupSettingsPanel','groupNamesTable','groupTemplateTitle','groupTemplateHint'):
                obj=item(name); point=obj.mapToScene(QPointF(0,0))
                result.extend((point.x(),point.y(),obj.width(),obj.height()))
            return result
        def aligned():
            assert names.property('count')==messages.property('rows')
            assert abs(top(names)-top(messages))<1, (top(names),top(messages))
            assert abs(names.height()-messages.height())<1, (names.height(),messages.height())
            assert abs((names.property('contentY')-names.property('originY'))-(messages.property('contentY')-messages.property('originY')))<1
            tabs=item('groupMessageTabs'); cell=item('groupMessageHeader')
            assert abs(top(tabs)-top(cell))<1 and abs(tabs.height()-cell.height())<1

        def row_aligned():
            index=min(names.property('count')-1,max(0,int((names.property('contentY')-names.property('originY'))/40)+1))
            if index<0: return
            left=item('groupName'+str(index)); right=item('groupMessageCell'+str(index)+'_0')
            assert abs(top(left)-top(right))<1, (index,top(left),top(right))
            assert left.property('recordKey')==right.property('recordKey')
            text=item('groupMessageText'+str(index)+'_0').property('text')
            row=g.pendingModel.get(index) if item('groupMessageTabs').property('currentIndex')==0 else g.sentModel.get(index)
            if row['id']==personal_id: assert text.startswith('个人消息')
            else: assert row['name'] in text, (row['name'],text)

        def capture(name):
            path=Path('output/group-message-list'); path.mkdir(parents=True,exist_ok=True)
            QTest.mouseMove(window,QPoint(0,0)); QTest.qWait(80)
            assert window.grabWindow().save(str(path/name))

        def configure_template():
            header=item('groupMessageHeader0')
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,header.mapToScene(QPointF(40,18)).toPoint())
            QTest.qWait(80)

        # A mode change respects the existing unsubmitted composer protection.
        item('groupChatComposer').setProperty('text','未加入的模板稿')
        click('groupToggleMessageView')
        assert not panel.property('listMode') and item('groupChatComposer').property('text')=='未加入的模板稿'
        item('groupChatComposer').setProperty('text','')
        click('groupToggleMessageView'); assert panel.property('listMode')
        assert item('groupTemplateTitle').property('text')=='消息模板'
        assert '加入后自动保存' in item('groupTemplateHint').property('text')
        aligned(); row_aligned()
        assert messages.property('columns')==3
        assert [item('groupMessageHeaderLabel'+str(i)).property('text') for i in range(3)]==['消息1','消息2','消息3']
        assert item('groupMessageText0_0').property('text')=='验证学员00，第一条消息'
        assert item('groupMessageText0_1').property('text')=='学习资料.txt'
        assert item('groupMessageText0_2').property('text')=='第二段 下一行'
        assert messages.property('contentWidth')>messages.width()
        messages.setProperty('contentX',120); QTest.qWait(80)
        assert names.property('contentX')==0
        messages.setProperty('contentX',0)
        position=messages.mapToScene(QPointF(40,messages.height()/2))
        app.sendEvent(window,QWheelEvent(position,position,QPoint(0,0),QPoint(0,-120),Qt.NoButton,Qt.ShiftModifier,Qt.NoScrollPhase,False))
        QTest.qWait(80); assert messages.property('contentX')>0 and names.property('contentX')==0
        assert item('groupMessageHeader').property('contentX')==messages.property('contentX')
        aligned(); messages.setProperty('contentX',0)
        for mode in ('light','dark'):
            assert b.settingsModule.setAppearanceMode(mode)
            for width,height in ((1250,800),(720,480)):
                window.resize(width,height); QTest.qWait(100)
                before_geometry=geometry()
                click('groupToggleMessageView'); assert not panel.property('listMode')
                assert all(abs(a-b)<1 for a,b in zip(before_geometry,geometry())), (mode,width,before_geometry,geometry())
                click('groupToggleMessageView'); aligned()
                assert all(abs(a-b)<1 for a,b in zip(before_geometry,geometry()))
                names.setProperty('contentY',names.property('originY')+400); QTest.qWait(80)
                aligned(); row_aligned()
                assert item('groupNamePersonalFlag12').property('visible')
                assert item('groupMessageCell12_0').property('personallyEdited')
                assert not item('groupMessageCell11_0').property('personallyEdited')
                capture('personal-mark-'+mode+'-'+str(width)+'.png')
                position=messages.mapToScene(QPointF(40,messages.height()/2))
                before=messages.property('contentY')
                app.sendEvent(window,QWheelEvent(position,position,QPoint(0,0),QPoint(0,-480),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
                QTest.qWait(100)
                assert messages.property('contentY')>before, (mode,width,before,messages.property('contentY'),messages.property('contentX'),position,messages.height(),messages.width())
                aligned(); row_aligned()
                position=names.mapToScene(QPointF(40,names.height()/2))
                before=names.property('contentY')
                app.sendEvent(window,QWheelEvent(position,position,QPoint(0,0),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
                QTest.qWait(80)
                assert names.property('contentY')>before
                aligned(); row_aligned()
                invoke(names,'positionViewAtEnd'); aligned()
                assert abs(top(item('groupAddNameInput'))+item('groupAddNameInput').height()-(top(names)+names.height()))<10
                capture('list-'+mode+'-'+str(width)+'.png')
                invoke(names,'positionViewAtBeginning'); aligned(); row_aligned()
                if mode=='light' and width==1250: capture('list-overview.png')

        # Real drag events carry the held button on the offscreen platform.
        window.resize(1250,800); QTest.qWait(100)
        for view in (names,messages):
            invoke(view,'positionViewAtBeginning')
            start=view.mapToScene(QPointF(40,view.height()*0.75)).toPoint()
            end=view.mapToScene(QPointF(40,view.height()*0.25)).toPoint()
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start)
            for step in range(1,9):
                position=QPointF(start)+(QPointF(end)-QPointF(start))*step/8
                app.sendEvent(window,QMouseEvent(QEvent.MouseMove,position,position,QPointF(window.mapToGlobal(position.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                QTest.qWait(20)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,end)
            QTest.qWait(80); invoke(view,'cancelFlick')
            assert view.property('contentY')>view.property('originY'), view.objectName()
            aligned(); row_aligned()
        invoke(names,'positionViewAtBeginning')
        # Long text remains within its column and opens a genuinely scrollable hover preview.
        names.setProperty('contentY',names.property('originY')+12*40); QTest.qWait(100)
        target=item('groupMessageCell12_0')
        assert target.width()<=messages.width() or target.width()==220
        position=target.mapToScene(QPointF(40,20)).toPoint()
        QTest.mouseMove(window,position); QTest.qWait(550)
        preview=item('groupMessagePreview'); assert preview.property('visible')
        assert item('groupMessagePreviewText').property('text').startswith('个人消息')
        text=item('groupMessagePreviewText')
        QTest.mouseMove(window,text.mapToScene(QPointF(40,40)).toPoint()); QTest.qWait(100)
        scroll=item('groupMessagePreviewScroll').property('contentItem')
        before=scroll.property('contentY'); position=text.mapToScene(QPointF(40,40))
        app.sendEvent(window,QWheelEvent(position,position,QPoint(0,0),QPoint(0,-480),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
        QTest.qWait(100); assert scroll.property('contentY')>before, (preview.property('visible'),before,scroll.property('contentY'),scroll.property('contentHeight'),scroll.height(),warnings)
        capture('table-hover-preview.png'); invoke(preview,'close')
        invoke(names,'positionViewAtBeginning')
        # Right-hand selection highlights the same person, and double click edits only that person.
        target=item('groupMessageCell1_0'); position=target.mapToScene(QPointF(40,20)).toPoint()
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,position); QTest.qWait(80)
        assert panel.property('selectedRow').toVariant()['id']==g.pendingModel.get(1)['id']
        QTest.mouseDClick(window,Qt.LeftButton,Qt.NoModifier,position); QTest.qWait(80)
        assert item('recipientMessageEditor').property('visible')
        assert item('recipientMessageEditor').property('recipientId')==g.pendingModel.get(1)['id']
        click('cancelRecipientMessages')

        # The original editor is retained and reused for global template configuration.
        configure_template(); assert item('groupUnifiedTemplateDialog').property('visible')
        assert item('groupMessageChat')==chat
        capture('unified-template.png')
        window.resize(720,480); QTest.qWait(100)
        for obj in (item('groupChatComposer'),item('groupCloseUnifiedTemplate')):
            assert top(obj)>=0 and top(obj)+obj.height()<=window.height()
        capture('unified-template-small.png')
        window.resize(1250,800); QTest.qWait(100)
        composer=item('groupChatComposer'); invoke(composer,'forceActiveFocus'); composer.setProperty('text','新模板 {姓名}')
        composer.setProperty('cursorPosition',len('新模板 {姓名}'))
        QTest.keyClick(window,Qt.Key_Return); QTest.qWait(100)
        assert g.pendingMessageModel.columnCount()==4
        assert len(g.defaultFields)==4 and '新模板' in g.defaultFields[-1]['value']
        assert g.recipientForView(personal_id,False)['items'][0]['text'].startswith('个人消息')
        composer.setProperty('text','还未加入'); click('groupCloseUnifiedTemplate')
        assert item('groupUnifiedTemplateDialog').property('visible') and composer.property('text')=='还未加入'
        composer.setProperty('text',''); click('groupCloseUnifiedTemplate')
        assert not item('groupUnifiedTemplateDialog').property('visible')
        aligned(); row_aligned()
        click('groupToggleMessageView'); assert not panel.property('listMode') and item('groupMessageChat')==chat
        assert chat.property('messageCount')==4
        click('groupToggleMessageView'); aligned()

        # Model changes, deletion and the sent tab retain row identity and alignment.
        result=g.addNames(list_id,['追加甲','追加乙']); assert len(result['added'])==2
        QTest.qWait(100); aligned()
        assert g.removeNames(list_id,[g.rows[-1]['id']]); QTest.qWait(100); aligned()
        task=g.store.plan(list_id)[0]; attempt=g.store.claim(list_id,task)
        g.store.finish(list_id,task,attempt,receipts.SENT,'模拟发送记录')
        g._reload_snapshot(); QTest.qWait(100); aligned()
        item('groupMessageTabs').setProperty('currentIndex',1); QTest.qWait(100); aligned(); row_aligned()
        assert names.property('count')==1
        target=item('groupMessageCell0_0'); position=target.mapToScene(QPointF(40,20)).toPoint()
        QTest.mouseDClick(window,Qt.LeftButton,Qt.NoModifier,position); QTest.qWait(80)
        assert not item('recipientMessageEditor').property('canEdit')
        click('cancelRecipientMessages')

        # An empty plan can configure its template first, then add names in list mode.
        assert g.createEmptyList('空名单配置'); QTest.qWait(100); aligned()
        assert names.property('count')==0
        configure_template(); assert chat.property('editable')
        composer=item('groupChatComposer'); invoke(composer,'forceActiveFocus'); composer.setProperty('text','你好 {姓名}')
        composer.setProperty('cursorPosition',len('你好 {姓名}'))
        QTest.keyClick(window,Qt.Key_Return); QTest.qWait(100)
        assert g.pendingMessageModel.columnCount()==1
        composer.setProperty('text','第二条提醒'); composer.setProperty('cursorPosition',len('第二条提醒'))
        QTest.keyClick(window,Qt.Key_Return); QTest.qWait(100)
        assert g.pendingMessageModel.columnCount()==2
        click('groupCloseUnifiedTemplate')
        add=item('groupAddNameInput'); invoke(add,'forceActiveFocus'); add.setProperty('text','空名单甲\n空名单乙')
        QTest.qWait(100); aligned(); row_aligned()
        assert g.pendingModel.rows[0]['items'][0]['text']=='你好 空名单甲' and messages.property('columns')==2
        assert not warnings,warnings
        driver.assert_not_called()
        import shiboken6
        shiboken6.delete(engine); shiboken6.delete(b)
        print('Message table smoke OK: stable mode geometry, fields/headers, scrollable hover, bidirectional scroll, model/tabs, editing/drafts, light/dark/small; no sending')


if __name__=='__main__': run()
