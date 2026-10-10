"""Real QML clipboard mode, with temporary databases and no desktop sending."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, QMimeData, QPointF, Qt
from PySide6.QtGui import QFontDatabase, QImage, QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.group_dispatch import GroupStore


def run():
    QQuickStyle.setStyle('Fusion');app=QApplication([])
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output=Path('output/group-clipboard');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder,patch('app.wecom_sender.WeComSender') as driver:
        b=Backend(Path(folder)/'test.db');g=b.groupCenter
        assert g.createEmptyList('剪贴板验证名单')
        assert g.addNames(g.selected['id'],['验证甲','验证乙'])
        engine=QQmlApplicationEngine();warnings=[]
        engine.warnings.connect(lambda values:warnings.extend(v.toString() for v in values))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0];window.resize(1280,960);window.show();QTest.qWait(120)

        def item(name):
            def visual(parent):
                if parent.objectName()==name:return parent
                for child in parent.childItems():
                    found=visual(child)
                    if found is not None:return found
            result=window.findChild(QObject,name)
            if result is None:result=visual(window.contentItem())
            assert result is not None,name
            return result

        def invoke(obj,method,*args):
            assert QMetaObject.invokeMethod(obj,method,*[Q_ARG('QVariant',arg) for arg in args])
            QTest.qWait(100)

        def click(name):invoke(item(name),'click')
        def capture(name):
            QTest.qWait(120);assert window.grabWindow().save(str(output/name))

        invoke(window,'switchModule',4)
        page=item('groupCenterPage');mode=item('groupSendMode');panel=item('recipientMessages')
        panel.setProperty('contactPrefix','测试');QTest.qWait(700)
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,mode.mapToScene(QPointF(mode.width()/2,mode.height()/2)).toPoint())
        QTest.keyClick(window,Qt.Key_Down);QTest.keyClick(window,Qt.Key_Return);QTest.qWait(150)
        assert mode.property('currentIndex')==1 and panel.property('clipboardMode')
        assert g.selected['options']['clipboard_mode']
        assert GroupStore(g.store.path).get(g.selected['id'])['options']['clipboard_mode']
        assert item('groupClipboardInstructions').property('visible')
        assert not item('groupMessageChat').property('visible')
        assert not item('groupSingleSend').property('enabled')
        assert all(row['content']=='[]' for row in g.rows)
        capture('clipboard-light.png')
        b.settingsModule.setAppearanceMode('dark');QTest.qWait(100);capture('clipboard-dark.png')
        b.settingsModule.setAppearanceMode('light')

        app.clipboard().setText('本周学习安排\n请在周日之前完成作业。\n原样保留 {姓名}')
        click('groupPreviewButton')
        assert item('groupSendPreview').property('visible') and len(g.preview)==2
        assert item('groupClipboardPreviewText').property('text')==app.clipboard().text()
        assert not item('groupPreviewEditPerson').property('visible')
        assert '剪贴板模式' in item('groupPreviewSummary').property('text')
        frozen=g.clipboardPreview['text'];app.clipboard().setText('后复制的内容不替换本轮')
        assert g.clipboardPreview['text']==frozen
        capture('clipboard-preview.png');click('groupPreviewBack')

        # Empty clipboard cannot reuse the preceding round's confirmation.
        app.clipboard().clear();click('groupPreviewButton')
        assert not item('groupSendPreview').property('visible')
        assert not g.preview and g.clipboardPreview=={}
        assert '先复制' in g.status

        # Qt offscreen image/file copies exercise the same preview and validation.
        image=QImage(160,90,QImage.Format_RGB32);image.fill(QColor('#285db4'))
        app.clipboard().setImage(image);click('groupPreviewButton')
        assert item('groupSendPreview').property('visible')
        assert '图片' in g.clipboardPreview['kindLabel'];click('groupPreviewBack')
        file=Path(folder)/'验证附件.txt';file.write_text('fixture',encoding='utf-8')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(file))]);app.clipboard().setMimeData(mime)
        click('groupPreviewButton');assert g.clipboardPreview['files']==[str(file)]
        capture('clipboard-file.png');click('groupPreviewBack')

        # Switch back with no prepared messages: template mode still requires them.
        invoke(page,'changeSendMode',0)
        assert item('groupMessageChat').property('visible') and not g.preview
        assert not item('groupClipboardInstructions').property('visible')
        click('groupPreviewButton');assert not g.preview and '尚未配置消息' in g.status

        # Pending template input is protected when selecting clipboard mode.
        composer=item('groupChatComposer');composer.setProperty('text','未加入的模板草稿')
        invoke(page,'changeSendMode',1)
        assert mode.property('currentIndex')==0
        assert composer.property('text')=='未加入的模板草稿'
        composer.setProperty('text','')
        revision=g.contentRevision
        assert g.saveDefaultRow(g.selected['id'],revision,[dict(sourceIndex=-1,type='text',value='你好 {姓名}',mixed=False)],False)
        original=[row['content'] for row in g.rows]
        invoke(page,'changeSendMode',1)
        assert [row['content'] for row in g.rows]==original
        invoke(page,'changeSendMode',0)
        assert [row['content'] for row in g.rows]==original

        # Selecting another list restores its own mode; narrow layouts remain usable.
        invoke(page,'changeSendMode',1);first=g.selected['id']
        assert g.createEmptyList('另一个虚构名单');QTest.qWait(120)
        assert mode.property('currentIndex')==0
        g.selectList(next(i for i,row in enumerate(g.lists) if row['id']==first));QTest.qWait(120)
        assert mode.property('currentIndex')==1
        window.resize(720,480);QTest.qWait(150);capture('clipboard-narrow.png')
        app.clipboard().setText('窄窗口的统一消息');click('groupPreviewButton')
        preview=item('groupSendPreview')
        assert preview.property('visible') and preview.property('width')<=window.width() and preview.property('height')<=window.height()
        capture('clipboard-preview-narrow.png');click('groupPreviewBack')
        driver.assert_not_called()
        relevant=[w for w in warnings if any(value in w for value in ('GroupCenter.qml','RecipientMessages.qml'))]
        assert not relevant,relevant
        window.close();QTest.qWait(50);engine.deleteLater();QTest.qWait(50)
    print('Clipboard QML smoke OK: mode persistence, frozen text/image/files, empty guards, drafts, template recovery, themes and narrow layout; no sending')


if __name__=='__main__':run()
