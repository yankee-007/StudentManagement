"""Attachment presentation in real QML, with fictional people and disposable files."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output=Path('output/group-attachments'); output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder, patch('app.wecom_sender.WeComSender') as driver:
        root=Path(folder)
        word=root/'数媒在线课堂刷题系统使用教程与课程说明.docx'; word.write_bytes(b'0'*(245*1024*1024//100))
        notes=root/'笔记详情.docx'; notes.write_bytes(b'0'*(11*1024))
        missing=root/'已移走的文件.pdf'
        corrupt=root/'损坏图片.png'; corrupt.write_bytes(b'not an image')

        def picture(name,width,height):
            path=root/name
            image=QImage(width,height,QImage.Format_RGB32); image.fill(QColor('#edf3ff'))
            painter=QPainter(image)
            painter.fillRect(0,0,width,height//4,QColor('#285db4'))
            painter.setPen(QColor('#ffffff')); painter.setFont(QFont('Microsoft YaHei',max(8,width//28)))
            painter.drawText(image.rect().adjusted(width//12,0,0,-height*3//4),Qt.AlignVCenter,'本周学习安排')
            painter.setPen(QColor('#203047')); painter.setFont(QFont('Microsoft YaHei',max(8,width//32)))
            painter.drawText(image.rect().adjusted(width//12,height//4,0,0),Qt.AlignVCenter,'课程复习  ·  作业提交')
            painter.end(); assert image.save(str(path))
            return path

        landscape=picture('安排 图%#甲.PNG',1600,900)
        portrait=picture('竖版安排.png',900,1800)
        small=picture('小图片.png',48,32)
        rotated=picture('带方向信息的图片.jpg',600,300)
        jpeg=rotated.read_bytes()
        # Minimal EXIF orientation=6 (90 degrees), using only the standard library.
        exif=bytes.fromhex('45786966000049492a0008000000010012010300010000000600000000000000')
        rotated.write_bytes(jpeg[:2]+b'\xff\xe1'+(len(exif)+2).to_bytes(2,'big')+exif+jpeg[2:])
        truncated=root/'截断图片.png'; truncated.write_bytes(landscape.read_bytes()[:100])
        b=Backend(root/'test.db'); g=b.groupCenter
        content=[dict(type='file',path=str(path)) for path in (word,notes,landscape)]
        assert g.createStructured('附件展示验证','验证甲\n验证乙',content)
        original=[row['content'] for row in g.rows]
        assert g.messageFileInfo(str(notes))['sizeLabel']=='11.00 KB'
        assert g.messageFileInfo(str(word))['sizeLabel']=='2.45 MB'
        info=g.messageFileInfo(str(landscape))
        assert info['image'] and (info['width'],info['height'])==(1600,900)
        assert Path(QUrl(info['url']).toLocalFile()).resolve()==landscape.resolve()
        assert not g.messageFileInfo(str(corrupt))['image']
        rotated_info=g.messageFileInfo(str(rotated))
        assert (rotated_info['width'],rotated_info['height'])==(300,600)
        assert g.messageFileInfo(str(truncated))['image']
        for value in ('',str(missing),str(root)):
            assert not g.messageFileInfo(value)['available']

        engine=QQmlApplicationEngine(); warnings=[]
        engine.warnings.connect(lambda values:warnings.extend(v.toString() for v in values))
        engine.rootContext().setContextProperty('backend',b)
        engine.rootContext().setContextProperty('studentModel',b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0]; window.resize(1280,960); window.show(); QTest.qWait(120)

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
            QTest.qWait(120)
            assert window.grabWindow().save(str(output/name))
            if name=='template-light.png':
                panel=item('groupTemplatePanel'); point=panel.mapToScene(QPointF(0,0)).toPoint()
                assert window.grabWindow().copy(point.x(),point.y(),int(panel.width()),int(panel.height())).save(str(output/'template-detail.png'))

        def check_image(name,expected):
            obj=item(name); image=item(name+'Image')
            for _ in range(30):
                if obj.property('imageReady'):break
                QTest.qWait(50)
            assert obj.property('showsImage') and obj.property('imageReady'),name
            assert abs(obj.width()-expected[0])<=1 and abs(obj.height()-expected[1])<=1,(name,obj.width(),obj.height())
            assert abs(image.property('paintedWidth')/image.property('paintedHeight')-expected[0]/expected[1])<0.02
            assert image.property('sourceSize').width()<=480 and image.property('sourceSize').height()<=360
            return obj

        invoke(window,'switchModule',4)
        chat=item('groupMessageChat'); panel=item('recipientMessages')
        invoke(item('groupChatThread'),'positionViewAtBeginning')
        card=item('groupChatAttachment0')
        assert card.property('visible') and card.height()==88
        assert item('groupChatAttachment0Name').property('text')==word.name
        assert item('groupChatAttachment0Size').property('text')=='2.45 MB'
        check_image('groupChatAttachment2',(240,135))
        capture('template-light.png')
        b.settingsModule.setAppearanceMode('dark'); QTest.qWait(100)
        capture('template-dark.png')
        b.settingsModule.setAppearanceMode('light'); QTest.qWait(80)

        # Double-click still uses the file replacement flow and keeps saved drafts intact.
        replacement=root/'替换资料.xlsx'; replacement.write_bytes(b'0'*2048)
        with patch('app.group_center.QFileDialog.getOpenFileName',return_value=(str(replacement),'')) as chooser:
            QTest.mouseDClick(window,Qt.LeftButton,Qt.NoModifier,card.mapToScene(QPointF(30,30)).toPoint())
            QTest.qWait(120); chooser.assert_called_once()
        assert g.defaultFields[0]['value']==str(replacement.resolve())
        assert item('groupChatAttachment0Size').property('text')=='2.00 KB'

        # Reloading an edited file at the same path refreshes metadata and the image cache.
        previous_url=g.messageFileInfo(str(landscape))['url']
        picture(landscape.name,48,32); invoke(panel,'loadDefaults',True)
        check_image('groupChatAttachment2',(48,32))
        assert g.messageFileInfo(str(landscape))['url']!=previous_url
        picture(landscape.name,1600,900); invoke(panel,'loadDefaults',True)
        check_image('groupChatAttachment2',(240,135))

        # Personal messages and send preview reuse the actual attachment renderer.
        panel.setProperty('selectedRow',g.pendingModel.get(0)); invoke(panel,'openEditor')
        check_image('personChatAttachment2',(240,135))
        capture('personal.png'); click('cancelRecipientMessages')
        invoke(item('groupCenterPage'),'openPreview')
        assert item('groupSendPreview').property('visible')
        check_image('groupPreviewAttachment2',(240,135))
        capture('send-preview.png'); click('groupPreviewBack')

        # Table rows remain 40px and keep the name/message viewports aligned.
        click('groupToggleMessageView')
        assert item('groupMessageCell0_0').height()==40
        assert item('groupTableAttachment0_0').height()==32
        assert item('groupTableAttachment0_0Name').property('text')==replacement.name
        assert abs(item('groupNamesTable').height()-item('groupRecipientMessageList').height())<1
        cell=item('groupMessageCell0_2')
        invoke(panel,'showMessagePreview',cell)
        check_image('groupHoverAttachment',(240,135))
        capture('table-preview.png'); invoke(item('groupMessagePreview'),'close')
        click('groupToggleMessageView')

        # Isolated display drafts cover aspect ratios, small files, invalid attachments,
        # and narrow columns without committing any invalid content to the store.
        def display(paths):
            invoke(chat,'load',[dict(sourceIndex=i,type='file',value=str(path),mixed=False) for i,path in enumerate(paths)],False)
            invoke(item('groupChatThread'),'positionViewAtBeginning')

        display([portrait,small,corrupt,missing])
        check_image('groupChatAttachment0',(90,180))
        check_image('groupChatAttachment1',(48,32))
        assert not item('groupChatAttachment2').property('showsImage')
        assert item('groupChatAttachment3Size').property('text')=='文件已失效'
        capture('edge-cases.png')
        display([rotated]); check_image('groupChatAttachment0',(90,180))
        display([truncated]); QTest.qWait(250)
        assert not item('groupChatAttachment0').property('showsImage')
        assert item('groupChatAttachment0Size').property('text').startswith('图片无法预览')
        window.resize(720,480); QTest.qWait(120)
        display([landscape])
        narrow=item('groupChatAttachment0')
        assert narrow.width()<=min(240,item('groupChatThread').width()) and narrow.height()<=180
        thread=item('groupChatThread')
        assert narrow.height()<=thread.height()
        invoke(thread,'positionViewAtEnd')
        top=narrow.mapToItem(thread,QPointF(0,0)).y()
        assert top>=-1 and top+narrow.height()<=thread.height()+1
        image=item('groupChatAttachment0Image'); QTest.qWait(120)
        assert abs(image.property('paintedWidth')/image.property('paintedHeight')-1600/900)<0.02
        capture('narrow.png')

        # Changes remain confined to the intentional replacement, with no send activity.
        assert len(g.rows)==2 and len(g.defaultFields)==3
        assert g.defaultFields[1]['value']==str(notes.resolve())
        assert [row['content'] for row in g.rows]!=original
        assert not driver.called and not g.active
        assert not [w for w in warnings if any(term in w for term in ('ReferenceError','TypeError','binding loop','Cannot assign'))],warnings
        invoke(panel,'loadDefaults',True)
        window.close(); engine.deleteLater(); app.processEvents()
    print('Attachment smoke OK: cards, scaled images, replacement, personal/send/table previews, light/dark, narrow and invalid files; no sending')


if __name__=='__main__':run()
