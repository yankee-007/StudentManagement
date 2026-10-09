"""File clipboard/drop and bubble interactions with disposable, fictional data."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF, QMimeData
from PySide6.QtGui import QFontDatabase, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font


def run():
    QQuickStyle.setStyle('Fusion'); app=QApplication([])
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    clipboard=app.clipboard(); previous=QMimeData()
    original=clipboard.mimeData()
    if original:
        for fmt in original.formats(): previous.setData(fmt,original.data(fmt))
    try:
        with tempfile.TemporaryDirectory() as folder, patch('app.wecom_sender.WeComSender') as driver:
            b=Backend(Path(folder)/'test.db'); g=b.groupCenter
            first=Path(folder)/'资料 甲.txt'; first.write_text('附件甲',encoding='utf-8')
            second=Path(folder)/'资料%乙.txt'; second.write_text('附件乙',encoding='utf-8')
            urls=[QUrl.fromLocalFile(str(path)) for path in (first,second)]
            assert g.messageFiles(urls)['files']==[str(first.resolve()),str(second.resolve())]
            for bad in (QUrl.fromLocalFile(folder),QUrl.fromLocalFile(str(Path(folder)/'缺失.txt')),QUrl('https://example.com/file.txt')):
                result=g.messageFiles([urls[0],bad])
                assert result['error'] and not result['files']
            assert g.createStructured('输入交互验证','验证甲\n验证乙',[dict(type='text',text='你好 {姓名}')])
            engine=QQmlApplicationEngine(); warnings=[]
            engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
            engine.rootContext().setContextProperty('backend',b)
            engine.rootContext().setContextProperty('studentModel',b.studentModel)
            engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
            assert engine.rootObjects(),warnings
            window=engine.rootObjects()[0]; window.resize(1250,800); window.show(); QTest.qWait(100)

            def item(name):
                def visual(parent):
                    if parent.objectName()==name:return parent
                    for child in parent.childItems():
                        result=visual(child)
                        if result is not None:return result
                result=window.findChild(QObject,name)
                if result is None:result=visual(window.contentItem())
                assert result is not None,name
                return result

            def invoke(obj,method,*args):
                assert QMetaObject.invokeMethod(obj,method,*[Q_ARG('QVariant',arg) for arg in args])
                QTest.qWait(80)

            invoke(window,'switchModule',4)
            chat=item('groupMessageChat'); composer=item('groupChatComposer')
            invoke(composer,'forceActiveFocus'); composer.setProperty('text','保留这段待加入文字')
            mime=QMimeData(); mime.setUrls(urls); clipboard.setMimeData(mime)
            QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(100)
            assert len(g.defaultFields)==3 and chat.property('messageCount')==3
            assert composer.property('text')=='保留这段待加入文字'
            assert [field['type'] for field in g.defaultFields]==['text','file','file']
            assert [field['value'] for field in g.defaultFields[1:]]==[str(first.resolve()),str(second.resolve())]
            assert all(len(row['items'])==3 for row in g.pendingModel.rows)

            # Plain text and web URLs retain the normal paste path.
            clipboard.setText('普通文字'); composer.setProperty('text','')
            QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(80)
            assert composer.property('text')=='普通文字' and chat.property('messageCount')==3
            remote=QMimeData(); remote.setUrls([QUrl('https://example.com/notes')]); remote.setText('https://example.com/notes')
            clipboard.setMimeData(remote); composer.setProperty('text','')
            QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(80)
            assert composer.property('text')=='https://example.com/notes' and chat.property('messageCount')==3
            composer.setProperty('text','')

            invalid=QMimeData(); invalid.setUrls([urls[0],QUrl.fromLocalFile(folder)]); clipboard.setMimeData(invalid)
            QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(80)
            assert chat.property('messageCount')==3 and chat.property('feedback')
            assert composer.property('text')==''

            # Real Qt drag/drop events hit the input DropArea and always copy the file.
            dropped=QMimeData(); dropped.setUrls([urls[0]])
            position=composer.mapToScene(QPointF(40,15))
            enter=QDragEnterEvent(position.toPoint(),Qt.CopyAction,dropped,Qt.LeftButton,Qt.NoModifier)
            app.sendEvent(window,enter); assert enter.isAccepted()
            move=QDragMoveEvent(position.toPoint(),Qt.CopyAction,dropped,Qt.LeftButton,Qt.NoModifier)
            app.sendEvent(window,move)
            drop=QDropEvent(position,Qt.CopyAction,dropped,Qt.LeftButton,Qt.NoModifier)
            app.sendEvent(window,drop); QTest.qWait(100)
            assert drop.isAccepted() and drop.dropAction()==Qt.CopyAction
            assert len(g.defaultFields)==4 and g.defaultFields[-1]['value']==str(first.resolve())
            assert first.read_text(encoding='utf-8')=='附件甲'
            assert not item('groupChatFileDrop').property('containsDrag')

            # A save failure keeps the attachment draft available for retry.
            mime=QMimeData(); mime.setUrls([urls[1]]); clipboard.setMimeData(mime)
            invoke(composer,'forceActiveFocus')
            with patch.object(g,'saveDefaultRow',return_value=False):
                QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(80)
            assert len(g.defaultFields)==4 and chat.property('messageCount')==5 and chat.property('dirty')
            invoke(item('recipientMessages'),'saveDefaults')
            assert len(g.defaultFields)==5 and not chat.property('dirty')

            chat.setProperty('editable',False); QTest.qWait(50)
            assert not item('groupChatFileDrop').property('enabled')
            invoke(chat,'dropFiles',[url.toString() for url in urls])
            assert chat.property('messageCount')==5
            chat.setProperty('editable',True); QTest.qWait(50)

            # Hover reveals the reserved action row without moving bubbles.
            invoke(item('groupChatThread'),'positionViewAtBeginning')
            QTest.mouseMove(window,window.contentItem().mapToScene(QPointF(1,1)).toPoint()); QTest.qWait(80)
            actions=item('groupChatActions0'); card=item('groupChatBubbleCard0')
            assert actions.property('opacity')==0
            before=card.mapToScene(QPointF(0,0)).y()
            QTest.mouseMove(window,card.mapToScene(QPointF(card.width()/2,card.height()/2)).toPoint()); QTest.qWait(80)
            assert actions.property('opacity')==1 and card.mapToScene(QPointF(0,0)).y()==before
            output=Path('output/group-message-table'); output.mkdir(parents=True,exist_ok=True)
            assert window.grabWindow().save(str(output/'bubble-hover.png'))
            QTest.mouseMove(window,window.contentItem().mapToScene(QPointF(1,1)).toPoint()); QTest.qWait(80)
            assert actions.property('opacity')==0 and card.mapToScene(QPointF(0,0)).y()==before
            assert window.grabWindow().save(str(output/'bubble-idle.png'))

            # Empty editing cancels on an outside click and preserves the committed value.
            before=g.defaultFields[0]['value']
            invoke(chat,'beginEdit',0); item('groupChatInline0').setProperty('text','  ')
            title=item('groupTemplateTitle')
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,title.mapToScene(QPointF(20,10)).toPoint()); QTest.qWait(100)
            assert chat.property('editingIndex')==-1 and not chat.property('feedback')
            assert g.defaultFields[0]['value']==before

            # The shared personal input saves its pasted file only for that person.
            panel=item('recipientMessages'); person=g.pendingModel.get(0)
            panel.setProperty('selectedRow',person); invoke(panel,'openEditor')
            personal=item('recipientMessageChat'); personal_input=item('personChatComposer')
            invoke(personal_input,'forceActiveFocus'); mime=QMimeData(); mime.setUrls([urls[0]]); clipboard.setMimeData(mime)
            QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier); QTest.qWait(80)
            assert personal.property('messageCount')==6 and len(g.defaultFields)==5
            invoke(item('saveRecipientMessages'),'click')
            assert not item('recipientMessageEditor').property('visible')
            assert len(g.pendingModel.rows[0]['items'])==6 and len(g.pendingModel.rows[1]['items'])==5
            assert not warnings,warnings
            driver.assert_not_called()
            import shiboken6
            shiboken6.delete(engine); shiboken6.delete(b)
            print('Message input smoke OK: file batches, actual clipboard/text fallback/drop, read-only, hover stability, empty outside cancel; no sending')
    finally:
        if previous.formats(): clipboard.setMimeData(previous)
        else: clipboard.clear()
        app.processEvents()
        # Finish the offscreen clipboard's ownership before Python releases MIME wrappers.
        import shiboken6
        shiboken6.delete(app)


if __name__=='__main__':run()
