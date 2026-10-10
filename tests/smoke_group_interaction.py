"""Real QML chat/settings/preview integration; disposable data and mocked sending."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF, QPoint
from PySide6.QtGui import QFontDatabase, QInputMethodEvent, QWheelEvent, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder, patch('app.wecom_sender.WeComSender') as driver:
        b = Backend(Path(folder) / 'test.db')
        g = b.groupCenter
        attachment = Path(folder) / '学习资料.txt'
        attachment.write_text('仅用于界面验证', encoding='utf-8')
        assert g.createStructured('消息编辑验证', '张三\n李四\n王五', [
            dict(type='text', text='{姓名}同学，请查收本周学习资料。'),
            dict(type='file', path=str(attachment)),
            dict(type='text', text='完成后请回复，感谢配合。')])
        list_id = g.selected['id']
        first_id = g.pendingModel.get(0)['id']
        assert g.saveRecipientField(list_id, first_id, 0, dict(type='text', text='张三的个人消息'))
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1250, 800)
        window.show()

        def item(name):
            result = window.findChild(QObject, name)
            def visual_item(parent):
                if parent.objectName() == name: return parent
                for child in parent.childItems():
                    found = visual_item(child)
                    if found: return found
                return None
            if result is None: result = visual_item(window.contentItem())
            assert result is not None, name
            return result

        def invoke(obj, method, *args):
            assert QMetaObject.invokeMethod(obj, method, *[Q_ARG('QVariant', arg) for arg in args])
            QTest.qWait(70)

        def click(name):
            obj = item(name)
            assert obj.property('enabled'), name
            invoke(obj, 'click')

        def edit(index, text, control='groupChat', save=True):
            invoke(item('groupMessageChat' if control == 'groupChat' else 'recipientMessageChat'), 'beginEdit', index)
            obj = item(control+'Inline'+str(index))
            invoke(obj, 'forceActiveFocus')
            obj.setProperty('text', text)
            obj.setProperty('cursorPosition', len(text))
            assert item('groupMessageChat' if control == 'groupChat' else 'recipientMessageChat').property('editingIndex') == index, (index, text, obj.property('activeFocus'))
            if save:
                QTest.keyClick(window, Qt.Key_Return)
                QTest.qWait(80)

        def compose(text, control='groupChat', send=True):
            obj = item(control+'Composer')
            invoke(obj, 'forceActiveFocus')
            obj.setProperty('text', text)
            obj.setProperty('cursorPosition', len(text))
            if send:
                QTest.keyClick(window, Qt.Key_Return)
                QTest.qWait(80)
            return obj

        def content(): return [json.loads(row['content']) for row in g.rows]

        def capture(name):
            directory = os.environ.get('GROUP_UI_CAPTURE_DIR')
            if directory:
                path = Path(directory)
                path.mkdir(parents=True, exist_ok=True)
                QTest.mouseMove(window, QPoint(0, 0)); QTest.qWait(80)
                assert window.grabWindow().save(str(path / name))
                if name == 'group-list-copied.png' or name.startswith('group-input-'):
                    grabbed = item('groupRecipientsPanel').grabToImage()
                    for _ in range(5):
                        if not grabbed.image().isNull(): break
                        QTest.qWait(50)
                    assert grabbed.image().save(str(path / ('roster-'+name)))

        def double_name(row):
            obj = item('groupName'+str(row))
            pos = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, pos)
            QTest.qWait(90)

        def pointer_click(name, double=False, button=Qt.LeftButton):
            obj = item(name)
            pos = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            action = QTest.mouseDClick if double else QTest.mouseClick
            action(window, button, Qt.NoModifier, pos)
            QTest.qWait(90)

        def modifier_click(name, modifier=Qt.NoModifier):
            obj = item(name)
            pos = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, modifier, pos)
            QTest.qWait(90)

        invoke(window, 'switchModule', 4)
        panel = item('recipientMessages')
        chat = item('groupMessageChat')
        assert item('groupTemplatePanel').property('visible')
        assert item('groupNamePersonalFlag0').property('visible')
        assert not item('groupNamePersonalFlag1').property('visible')
        for removed in ('groupStatistics', 'groupRecipientList', 'groupInformationTable', 'groupSingleCellDialog'):
            assert window.findChild(QObject, removed) is None, removed
        capture('group-center.png')

        # Inline editing can cancel; committing only updates unoverridden recipients.
        before = content()
        edit(0, '取消的修改', save=False)
        capture('group-default-edit.png')
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
        assert content() == before
        edit(0, '{姓名}，本周资料已经更新。')
        assert content()[0][0]['text'] == '张三的个人消息'
        assert content()[1][0]['text'] == '李四，本周资料已经更新。', (content(), chat.property('editingIndex'), chat.property('editText'), chat.property('feedback'))
        assert not panel.property('defaultsDirty')

        # Double click enters editing; a click on a non-focusable title commits it.
        template_text = g.defaultFields[0]['value']
        pointer_click('groupChatBubbleCard0')
        assert chat.property('editingIndex') == -1
        pointer_click('groupChatBubbleCard0', double=True)
        assert chat.property('editingIndex') == 0
        assert window.findChild(QObject, 'groupChatSaveEdit') is None
        assert window.findChild(QObject, 'groupChatCancelEdit') is None
        item('groupChatInline0').setProperty('text', '外部点击保存')
        pointer_click('groupTemplateTitle')
        assert chat.property('editingIndex') == -1 and g.defaultFields[0]['value'] == '外部点击保存'
        edit(0, 'Tab 保存', save=False)
        QTest.keyClick(window, Qt.Key_Tab); QTest.qWait(90)
        assert chat.property('editingIndex') == -1 and g.defaultFields[0]['value'] == 'Tab 保存'
        edit(0, '', save=False)
        pointer_click('groupTemplateTitle')
        assert chat.property('editingIndex') == -1 and g.defaultFields[0]['value'] == 'Tab 保存'
        # Composition confirmation is separate from Enter-save, including an outside click.
        edit(0, '', save=False)
        app.sendEvent(window, QInputMethodEvent('组合输入', []))
        assert item('groupChatInline0').property('inputMethodComposing')
        QTest.keyClick(window, Qt.Key_Return)
        assert chat.property('editingIndex') == 0
        pointer_click('groupTemplateTitle')
        assert chat.property('editingIndex') == 0
        event = QInputMethodEvent(); event.setCommitString('组合输入')
        app.sendEvent(window, event); QTest.qWait(90)
        assert chat.property('editingIndex') == -1 and g.defaultFields[0]['value'] == '组合输入'
        edit(0, template_text)

        # A failed inline save retains its editor, but Esc cancels the new value.
        before = content()
        with patch.object(g, 'saveDefaultRow', return_value=False):
            edit(0, '保存失败后取消的编辑')
        assert chat.property('editingIndex') == 0 and not panel.property('defaultsDirty')
        assert item('groupChatInline0').property('text') == '保存失败后取消的编辑'
        assert item('groupResetDefaults').property('visible')
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
        assert chat.property('editingIndex') == -1 and content() == before
        click('groupPreviewButton')
        if item('groupEmptyPrefixReminder').property('visible'):
            click('groupEmptyPrefixContinue')
        assert item('groupSendPreview').property('visible') and content() == before
        click('groupPreviewBack')

        # Bubble width follows rendered content; long text wraps at a stable cap.
        template_text = g.defaultFields[0]['value']
        edit(0, '好')
        short_card = item('groupChatBubbleCard0')
        short_width = short_card.width()
        short_height = short_card.height()
        right_edge = short_card.mapToScene(QPointF(short_width, 0)).x()
        assert short_width < 100
        edit(0, '这是一条稍长的消息 Hello 123')
        medium_width = item('groupChatBubbleCard0').width()
        assert medium_width > short_width+80
        edit(0, '第二行比较长一些')
        one_line_width = item('groupChatBubbleCard0').width()
        edit(0, '短\n第二行比较长一些')
        card = item('groupChatBubbleCard0')
        assert abs(card.width()-one_line_width) < 1 and card.height() > short_height+10
        # A message that fits the column is never wrapped, not even when its widest line is the
        # last one: a card rounded below the exact text width used to push 「业}」 onto its own line.
        edit(0, '未完作业节次：{姓名}')
        widest_width = item('groupChatBubbleCard0').width()
        edit(0, '未完课程节次：{姓名}\n未完作业节次：{姓名}')
        card = item('groupChatBubbleCard0')
        label = item('groupChatBubble0')
        assert label.property('lineCount') == 2, (card.width(), card.height())
        assert abs(card.width()-widest_width) < 1, (card.width(), widest_width)
        # The text keeps at least a pixel of slack, so device pixel rounding cannot wrap it.
        assert label.property('width') >= label.property('implicitWidth')+1, \
            (label.property('width'), label.property('implicitWidth'))
        # A {变量} placeholder stays whole when a message does wrap, and joins add no width.
        edit(0, '第一节{姓名}')
        token_text = label.property('text')
        assert token_text == '第一节{\u2060姓\u2060名\u2060}', repr(token_text)
        assert g.defaultFields[0]['value'] == '第一节{姓名}', g.defaultFields[0]['value']
        token_width = item('groupChatBubbleCard0').width()
        edit(0, '第一节{姓名')
        unclosed_width = item('groupChatBubbleCard0').width()
        edit(0, '第一节}}')
        braces_width = item('groupChatBubbleCard0').width()
        edit(0, '第一节}')
        assert abs((token_width-unclosed_width)-(braces_width-item('groupChatBubbleCard0').width())) <= 2, \
            (token_width, unclosed_width, braces_width, item('groupChatBubbleCard0').width())
        long_text = '这是一条用于验证自动换行和最大宽度的消息。'*18
        edit(0, long_text)
        card = item('groupChatBubbleCard0')
        capped_width = card.width()
        assert capped_width > medium_width and capped_width < item('groupChatThread').width()
        assert card.height() > short_height*2
        assert abs(card.mapToScene(QPointF(card.width(), 0)).x()-right_edge) < 2
        edit(0, long_text*2)
        assert abs(item('groupChatBubbleCard0').width()-capped_width) < 1
        # Editing expands even a one-character bubble so its controls fit.
        edit(0, '好')
        edit(0, '正在编辑', save=False)
        assert item('groupChatBubbleCard0').width() > short_width+100
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
        assert abs(item('groupChatBubbleCard0').width()-short_width) < 1
        edit(0, template_text)
        # Several different content lengths provide a real screenshot of the geometry.
        compose('收到')
        compose('请查收附件，完成后回复即可。')
        compose('第一行\n这条消息有两行')
        capture('group-bubbles-auto.png')
        for index in (5, 4, 3): invoke(chat, 'removeMessage', index)

        # Real keys: Shift+Enter inserts a newline, Enter commits one raw message.
        obj = compose('第一行', send=False)
        QTest.keyClick(window, Qt.Key_Return, Qt.ShiftModifier)
        assert obj.property('text') == '第一行\n'
        obj.setProperty('text', '第一行\n\n第二行\n')
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(80)
        assert all(len(row) == 4 and row[3]['text'] == '第一行\n\n第二行\n' for row in content())
        # A second Enter uses the freshly loaded contentRevision, rather than a stale draft.
        compose('连续第二条-{姓名}')
        assert all(len(row) == 5 for row in content())
        assert content()[2][4]['text'] == '连续第二条-王五'
        invoke(chat, 'moveMessage', 4, -1)
        assert content()[1][3]['text'] == '连续第二条-李四'
        invoke(chat, 'removeMessage', 3)
        invoke(chat, 'removeMessage', 3)
        assert all(len(row) == 3 for row in content())

        # IME confirmation cannot accidentally append a message.
        obj = compose('', send=False)
        app.sendEvent(window, QInputMethodEvent('军训', []))
        assert obj.property('inputMethodComposing')
        QTest.keyClick(window, Qt.Key_Return)
        assert chat.property('messageCount') == 3
        event = QInputMethodEvent()
        event.setCommitString('军训')
        app.sendEvent(window, event)
        assert not obj.property('inputMethodComposing') and obj.property('text') == '军训'
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(80)
        assert content()[0][-1]['text'] == '军训'
        invoke(chat, 'removeMessage', 3)

        # Cancelled attachment is inert. Invalid paths retain the draft for retry/reset.
        with patch.object(g, 'chooseMessageFile', return_value=''):
            click('groupChatAttach')
        assert chat.property('messageCount') == 3
        with patch.object(g, 'chooseMessageFile', return_value=str(attachment)):
            click('groupChatAttach')
        assert content()[1][3]['type'] == 'file'
        invoke(chat, 'removeMessage', 3)
        with patch.object(g, 'chooseMessageFile', return_value=str(Path(folder)/'missing.txt')):
            click('groupChatAttach')
        assert panel.property('defaultsDirty') and chat.property('messageCount') == 4
        click('groupPreviewButton')
        assert not item('groupSendPreview').property('visible')
        click('groupResetDefaults')
        assert chat.property('messageCount') == 3 and not panel.property('defaultsDirty')
        # Retry first commits the inline draft, keeping the newest revision of the message.
        with patch.object(g, 'saveDefaultRow', return_value=False):
            compose('临时保存失败的消息')
        assert panel.property('defaultsDirty') and all(len(row) == 3 for row in content())
        edit(3, '正在修订失败稿', save=False)
        click('groupRetryDefaults')
        assert chat.property('editingIndex') == -1
        assert all(row[3]['text'] == '正在修订失败稿' for row in content())
        assert all(len(row) == 4 for row in content()) and not panel.property('defaultsDirty')
        invoke(chat, 'removeMessage', 3)

        # Names use the actual prefix, with no index. A real double click opens personal chat.
        item('groupContactPrefix').setProperty('text', '测试班-')
        QTest.qWait(750)
        assert item('groupNameLabel1').property('text') == '测试班-李四'
        # Esc discards added bubbles, pending input and active inline edits in the whole dialog.
        before=content()
        double_name(1)
        compose('未保存的个人气泡','personChat')
        compose('未加入的个人草稿','personChat',send=False)
        QTest.keyClick(window,Qt.Key_Escape);QTest.qWait(80)
        assert not item('recipientMessageEditor').property('visible') and content()==before
        assert not item('recipientMessageChat').property('hasPending') and not item('recipientMessageChat').property('dirty')
        assert not item('groupNamePersonalFlag1').property('visible')
        double_name(1)
        edit(0,'Esc 不保存内联修改','personChat',save=False)
        QTest.keyClick(window,Qt.Key_Escape);QTest.qWait(80)
        assert not item('recipientMessageEditor').property('visible') and content()==before
        double_name(1)
        editor = item('recipientMessageEditor')
        assert editor.property('visible') and editor.property('canEdit')
        assert editor.property('recipientId') == g.rows[1]['id']
        edit(0, '', 'personChat', save=False)
        pointer_click('cancelRecipientMessages')
        assert not editor.property('visible')
        assert item('recipientMessageChat').property('editingIndex') == -1
        pointer_click('groupTemplateTitle')
        assert chat.property('editingIndex') == -1
        double_name(1)
        edit(2, '李四的补充说明', 'personChat')
        assert content()[1][2]['text'] == '完成后请回复，感谢配合。'
        window.close(); app.processEvents()
        assert window.isVisible() and editor.property('visible')
        compose('未加入个人稿', 'personChat', send=False)
        click('saveRecipientMessages')
        assert editor.property('visible')
        item('personChatComposer').setProperty('text', '')
        capture('group-personal.png')
        click('saveRecipientMessages')
        assert not editor.property('visible') and content()[1][2]['text'] == '李四的补充说明'
        assert item('groupNamePersonalFlag1').property('visible'), (g.pendingModel.get(1),item('groupName1').property('rowData').toVariant(),panel.property('rowsRevision'))
        assert content()[0][2]['text'] == '完成后请回复，感谢配合。'
        edit(2, '公共补充-{姓名}')
        assert content()[1][2]['text'] == '李四的补充说明'
        assert content()[0][2]['text'] == '公共补充-张三'

        # A pending composer blocks navigation; preview commits a completed inline edit.
        compose('未提交草稿', send=False)
        click('groupPreviewButton')
        assert not item('groupSendPreview').property('visible')
        invoke(window, 'switchModule', 1)
        assert window.property('moduleIndex') == 4
        window.close(); app.processEvents()
        assert window.isVisible() and item('groupChatComposer').property('text') == '未提交草稿'
        item('groupChatComposer').setProperty('text', '')
        template_text = g.defaultFields[0]['value']
        edit(0, '尚未保存编辑', save=False)
        click('groupPreviewButton')
        assert item('groupSendPreview').property('visible') and chat.property('editingIndex') == -1
        click('groupPreviewBack')
        edit(0, template_text)

        # Settings and the explicit, ordered preview/send boundary stay intact.
        assert item('groupSettingsPanel').property('visible')
        assert item('groupRecipientsPanel').mapToScene(QPointF(0,0)).x() < item('groupTemplatePanel').mapToScene(QPointF(0,0)).x() < item('groupSettingsPanel').mapToScene(QPointF(0,0)).x()
        assert item('groupPasteDelay').property('text') == '0.5'
        item('groupPasteDelay').setProperty('text', '0.7')
        click('groupResetWaits')
        assert item('groupPasteDelay').property('text') == '0.5'
        confirm_send = item('groupConfirmSend')
        single_send = item('groupSingleSend')
        assert single_send.property('enabled') and single_send.property('y') > confirm_send.property('y')
        confirm_send.setProperty('checked', False)
        invoke(item('groupCenterPage'), 'saveOptions')
        assert not single_send.property('enabled') and not g.preview
        assert single_send.property('opacity') < 0.5

        # 方案操作在下拉框右键菜单，复制为新名单／新建群发仍在最右。
        page = item('groupCenterPage')
        selector = item('groupListSelector')
        assert window.findChild(QObject,'groupRenameList') is None
        copy_button = item('groupCopyList')
        create_button = item('groupCreateList')
        row_y = selector.mapToScene(QPointF(0, 0)).y()
        for control in (copy_button, create_button):
            assert abs(control.mapToScene(QPointF(0, 0)).y()-row_y) < 2, (control.objectName(), control.mapToScene(QPointF(0, 0)).y(), row_y)
        assert selector.mapToScene(QPointF(selector.width(), 0)).x() <= copy_button.mapToScene(QPointF(0, 0)).x()+1
        assert copy_button.mapToScene(QPointF(copy_button.width(), 0)).x() <= create_button.mapToScene(QPointF(0, 0)).x()+1
        assert create_button.mapToScene(QPointF(create_button.width(), 0)).x() >= page.mapToScene(QPointF(page.width(), 0)).x()-1
        pointer_click('groupListSelector',button=Qt.RightButton)
        assert item('groupPlanMenu').property('visible')
        capture('group-plan-menu.png')
        pointer_click('groupRenamePlanAction')
        assert item('groupRenameDialog').property('visible')
        assert item('groupRenameInput').property('text') == '消息编辑验证'
        capture('group-rename-dialog.png')
        item('groupRenameInput').setProperty('text', '聊天模板改名验证')
        click('confirmRenameList')
        assert not item('groupRenameDialog').property('visible')
        assert g.selected['title'] == '聊天模板改名验证' and g.store.get(list_id)['title'] == '聊天模板改名验证'
        assert selector.property('currentText').startswith('聊天模板改名验证')
        assert [row['name'] for row in g.rows] == ['张三', '李四', '王五'] and content()[0][0]['text'] == '张三的个人消息'
        # Right clicking an unselected popup item must not switch or manage the current plan.
        extra_id=g.store.create('右键目标',[],allow_empty=True);g.refresh();QTest.qWait(80)
        pointer_click('groupListSelector');pointer_click('groupPlanOption0')
        assert g.selected['id']==extra_id and selector.property('currentIndex')==0
        pointer_click('groupListSelector');pointer_click('groupPlanOption1')
        assert g.selected['id']==list_id and selector.property('currentIndex')==1
        pointer_click('groupListSelector')
        assert item('groupPlanOption0').property('visible')
        pointer_click('groupPlanOption0',button=Qt.RightButton)
        assert item('groupPlanMenu').property('listId')==extra_id and g.selected['id']==list_id
        pointer_click('groupRenamePlanAction')
        assert item('groupRenameInput').property('text')=='右键目标'
        item('groupRenameInput').setProperty('text','右键目标已改名');click('confirmRenameList')
        assert g.store.get(extra_id)['title']=='右键目标已改名' and g.selected['id']==list_id
        pointer_click('groupListSelector');pointer_click('groupPlanOption0',button=Qt.RightButton)
        pointer_click('groupDeletePlanAction');capture('group-delete-dialog.png')
        assert item('groupDeletePlanDialog').property('listId')==extra_id
        click('cancelDeletePlan');assert g.store.get(extra_id)
        pointer_click('groupListSelector');pointer_click('groupPlanOption0',button=Qt.RightButton)
        pointer_click('groupDeletePlanAction');click('confirmDeletePlan')
        assert g.store.get(extra_id) is None and g.selected['id']==list_id
        click('groupCopyList')
        assert item('groupCopyBatchDialog').property('visible')
        assert item('groupCopyTitleInput').property('text') == '聊天模板改名验证 - 副本'
        invoke(item('groupCopyBatchDialog'), 'close')
        click('groupCreateList')
        assert item('customGroupDialog').property('visible')
        invoke(item('customGroupDialog'), 'close')
        item('groupContactPrefix').setProperty('text', '')
        click('groupPreviewButton')
        assert item('groupEmptyPrefixReminder').property('visible')
        click('groupEmptyPrefixBack')
        click('groupPreviewButton')
        click('groupEmptyPrefixContinue')
        assert item('groupSendPreview').property('visible')
        click('groupPreviewBack')
        item('groupContactPrefix').setProperty('text', '测试班-')
        QTest.qWait(750)
        click('groupPreviewButton')
        preview = item('groupSendPreview')
        assert preview.property('visible') and len(g.preview) == 3
        assert item('groupPreviewSummary').property('text').startswith('仅粘贴，不发送 · ')
        assert item('groupPreviewContact').property('text') == '联系人：测试班-张三'
        assert item('groupStartButton').property('text') == '开始粘贴 · 3 人'
        click('groupPreviewNext')
        current = preview.property('currentRecipient').toVariant()
        assert [row['type'] for row in current['content']] == ['text', 'file', 'text']
        assert current['content'][2]['text'] == '李四的补充说明'
        capture('group-preview.png')
        click('groupPreviewEditPerson')
        assert editor.property('visible') and editor.property('recipientId') == g.rows[1]['id']
        click('cancelRecipientMessages')
        edit(0, '更新预览-{姓名}')
        assert not g.preview and not g.start()
        driver.assert_not_called()

        # Actual control geometry in light/dark, wide/narrow; names and messages scroll independently.
        for mode in ('light', 'dark'):
            assert b.settingsModule.setAppearanceMode(mode)
            for width, height in ((1250, 800), (720, 480)):
                window.resize(width, height); QTest.qWait(100)
                capture('group-'+mode+'-'+str(width)+'.png')
                for name in ('groupChatComposer', 'groupChatSend', 'groupPreviewButton'):
                    control = item(name)
                    top = control.mapToScene(QPointF(0, 0))
                    assert top.y() >= 0 and top.y()+control.height() <= window.height()+1, (name, top.y(), control.height())
                assert item('groupChatThread').height() > 35
                # The inline editor must remain reachable in the smaller viewport too.
                edit(2, '小窗正在编辑', save=False)
                save = item('groupChatInlineScroll2')
                thread = item('groupChatThread')
                assert save.property('visible') and save.mapToScene(QPointF(0, 0)).y() >= thread.mapToScene(QPointF(0, 0)).y()-1
                assert save.mapToScene(QPointF(0, save.height())).y() <= thread.mapToScene(QPointF(0, thread.height())).y()+1
                QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
                if width == 720:
                    panel.setProperty('selectedRow', g.pendingModel.get(1))
                    invoke(panel, 'openEditor')
                    for name in ('personChatComposer', 'saveRecipientMessages', 'cancelRecipientMessages'):
                        control = item(name)
                        top = control.mapToScene(QPointF(0, 0))
                        assert top.y() >= 0 and top.y()+control.height() <= window.height()+1, (name, top.y(), control.height())
                    assert item('personChatThread').height() > 70
                    capture('group-personal-'+mode+'-small.png')
                    edit(2, '\n'.join('个人长消息'+str(i) for i in range(40)), 'personChat', save=False)
                    QTest.qWait(80)
                    save = item('personChatInlineScroll2')
                    thread = item('personChatThread')
                    assert save.property('visible')
                    assert save.mapToScene(QPointF(0, 0)).y() >= thread.mapToScene(QPointF(0, 0)).y()-1
                    assert save.mapToScene(QPointF(0, save.height())).y() <= thread.mapToScene(QPointF(0, thread.height())).y()+1
                    capture('group-personal-edit-'+mode+'-small.png')
                    QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
                    click('cancelRecipientMessages')
        assert b.settingsModule.setAppearanceMode('light')
        click('groupPreviewButton')
        assert preview.property('width') <= window.width() and preview.property('height') <= window.height()
        capture('group-preview-small.png')
        click('groupPreviewBack')
        assert g.saveOptions(list_id, '测试班-', dict(confirm_send=True, verify_contact=False))
        invoke(item('groupCenterPage'), 'loadOptions')
        click('groupPreviewButton')
        assert item('groupAcceptRisk').property('visible') and not item('groupStartButton').property('enabled')
        item('groupAcceptRisk').setProperty('checked', True)
        assert item('groupStartButton').property('enabled')
        click('groupPreviewBack')
        click('groupPreviewButton')
        assert not item('groupStartButton').property('enabled')
        click('groupPreviewBack')
        g._worker = object(); g._notify_activity(); app.processEvents()
        assert not chat.property('editable')
        assert not item('groupConfirmSend').property('enabled')
        assert not item('groupContactPrefix').property('enabled')
        assert not item('groupPreviewButton').property('enabled')
        g._worker = None; g._notify_activity()

        # A concurrent update keeps the inline draft but rejects its stale revision.
        window.resize(1250, 800); QTest.qWait(100)
        edit(0, '仍保留的草稿', save=False)
        assert g.saveRecipientField(list_id, g.rows[1]['id'], 0, dict(type='text', text='外部编辑'))
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(80)
        assert not panel.property('defaultsDirty') and chat.property('editingIndex') == 0
        assert item('groupChatInline0').property('text') == '仍保留的草稿'
        click('groupPreviewButton')
        assert not preview.property('visible')
        click('groupResetDefaults')

        # Long chat edits stay scrollable and at the same part of the conversation.
        many = [dict(type='text', text='第'+str(i+1)+'条消息') for i in range(80)]
        assert g.createStructured('长消息验证', '甲\n乙\n丙', many)
        QTest.qWait(90)
        invoke(chat, 'beginEdit', 79)
        long_text = '\n'.join('长消息第'+str(i+1)+'行' for i in range(40))
        inline = item('groupChatInline79')
        assert inline.property('activeFocus') and chat.property('activeEditor') == inline
        inline.setProperty('text', long_text)
        QTest.qWait(80)
        assert item('groupChatInlineScroll79').property('clip')
        assert item('groupChatInlineScroll79').height() <= 160
        thread = item('groupChatThread')
        thread.setProperty('contentY', thread.property('originY')); QTest.qWait(80)
        assert chat.property('editingIndex') == 79 and inline.property('text') == long_text
        old_y = thread.property('contentY')
        p = thread.mapToScene(QPointF(5, thread.height()/2))
        for _ in range(8):
            event = QWheelEvent(p, QPointF(window.mapToGlobal(p.toPoint())), QPoint(), QPoint(0,-120),
                                Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            app.sendEvent(window, event); QTest.qWait(25)
        QTest.qWait(100)
        assert thread.property('contentY') > old_y and inline.property('text') == long_text
        # Return to the same live editor after scrolling far away.
        invoke(chat, 'revealEditing')
        save = item('groupChatInlineScroll79')
        capture('group-long-edit.png')
        assert save.property('visible') and save.mapToScene(QPointF(0, 0)).y() >= thread.mapToScene(QPointF(0, 0)).y()-1
        assert save.mapToScene(QPointF(0, save.height())).y() <= thread.mapToScene(QPointF(0, thread.height())).y()+1, (save.mapToScene(QPointF(0,save.height())).y(), thread.mapToScene(QPointF(0,thread.height())).y(), thread.property('contentY'), thread.property('moving'))
        g._worker = object(); g._notify_activity(); app.processEvents()
        assert inline.property('readOnly')
        g._worker = None; g._notify_activity()
        capture('group-long-edit.png')
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(80)
        assert content()[0][79]['text'] == long_text, (content()[0][79]['text'], chat.property('editingIndex'), inline.property('activeFocus'), chat.property('editText'), chat.property('feedback'))
        assert thread.property('contentY')-thread.property('originY') > 2000
        edit(50, '中间消息更新')
        assert content()[1][50]['text'] == '中间消息更新'
        assert thread.property('contentY')-thread.property('originY') > 2000

        # Mixed legacy messages remain distinct when another bubble is added/deleted.
        assert g.createCustom('旧混合名单', '甲|甲的话术\n乙|乙的话术')
        QTest.qWait(90)
        assert item('groupChatBubble0').property('text') == '各人内容不同 · 编辑后统一'
        compose('共同的第二条')
        assert [row[0]['text'] for row in content()] == ['甲的话术', '乙的话术']
        assert all(row[1]['text'] == '共同的第二条' for row in content())
        invoke(chat, 'removeMessage', 1)
        edit(0, '已统一-{姓名}')
        assert [row[0]['text'] for row in content()] == ['已统一-甲', '已统一-乙']

        # The name list and message thread have independent vertical positions.
        assert g.createStructured('长名单验证', '\n'.join('验证学员'+str(i) for i in range(90)), [dict(type='text', text='统一消息')])
        QTest.qWait(90)
        names = item('groupNamesTable')
        old_y = thread.property('contentY')
        names.setProperty('contentY', 1000); QTest.qWait(80)
        assert names.property('contentY') > 900 and thread.property('contentY') == old_y
        invoke(item('groupCenterPage'), 'selectList', next(i for i, row in enumerate(g.lists) if row['id'] == list_id))

        # Covering personal overrides remains explicit and invalidates prior preview.
        click('groupOverridePersonal')
        assert item('groupOverrideDialog').property('visible')
        click('groupConfirmOverride')
        assert content()[0][0]['text'] == '更新预览-张三'
        assert content()[1][2]['text'] == '公共补充-李四'
        assert not item('groupNamePersonalFlag0').property('visible') and not item('groupNamePersonalFlag1').property('visible')

        # Names-only lists accept the first bubble. Switching cannot discard pending text.
        assert g.copyList('仅人员名单', False)
        QTest.qWait(90)
        assert g.pendingCount == 3 and chat.property('messageCount') == 0
        capture('group-names-only.png')
        compose('新增给-{姓名}')
        assert content()[2][0]['text'] == '新增给-王五'
        names_only_id = g.selected['id']
        target_index = next(i for i, row in enumerate(g.lists) if row['id'] == list_id)
        compose('不能丢弃', send=False)
        invoke(item('groupCenterPage'), 'selectList', target_index)
        assert g.selected['id'] == names_only_id
        assert item('groupListSelector').property('currentIndex') == g.selectedIndex
        item('groupChatComposer').setProperty('text', '')
        invoke(item('groupCenterPage'), 'selectList', target_index)
        assert g.selected['id'] == list_id
        assert chat.property('messageCount') == 3

        # 非首个方案的改名同样只换标题，刷新名单列表后当前选择与索引不变。
        assert target_index > 0
        assert g.renameList(list_id, '长名单验证-改名'), g.status
        QTest.qWait(80)
        assert g.selected['id'] == list_id and g.store.get(list_id)['title'] == '长名单验证-改名'
        assert item('groupListSelector').property('currentIndex') == target_index == g.selectedIndex
        assert [row['label'].split(' · ')[0] for row in g.lists][target_index] == '长名单验证-改名'

        # Protected rows are viewed through the same name entry, and expose result resolution.
        protected_list_id=g.selected['id']
        row_id = g.rows[2]['id']
        with g.store.connect() as conn:
            conn.execute("UPDATE recipients SET state='结果待确认' WHERE id=?", (row_id,))
        g.refresh(); QTest.qWait(80)
        panel.setProperty('selectedRow', g.recipientForView(row_id, False))
        invoke(panel, 'openEditor')
        assert editor.property('visible') and not editor.property('canEdit')
        assert item('groupResolveSent').property('visible')
        assert not item('recipientMessageChat').property('editable')
        click('cancelRecipientMessages')
        pointer_click('groupListSelector',button=Qt.RightButton)
        pointer_click('groupDeletePlanAction');click('confirmDeletePlan')
        assert item('groupDeletePlanDialog').property('visible') and '待核实' in g.status
        assert g.store.get(protected_list_id)
        click('cancelDeletePlan')

        # 新建群发方案只填名称；名单用手填空单元格和 Ctrl+V 粘贴补，像文件列表一样多选复制。
        saved_clipboard = QGuiApplication.clipboard().text()
        click('groupCreateList')
        assert item('customGroupDialog').property('visible')
        assert window.findChild(QObject, 'groupCustomNames') is None, '新建群发方案不应再要求先填名单和消息'
        assert window.findChild(QObject, 'newMessageFields') is None
        item('groupCustomTitle').setProperty('text', '手填名单验证')
        click('createGroupPlan')
        assert not item('customGroupDialog').property('visible')
        assert g.selected['title'] == '手填名单验证' and g.rows == [], g.status
        assert item('groupListSelector').property('currentText').startswith('手填名单验证')
        assert window.findChild(QObject, 'groupEditPersonButton') is None, '查看个人消息按钮应已移除'
        names_view = item('groupNamesTable')
        assert names_view.metaObject().className() == 'QQuickListView', names_view.metaObject().className()
        add_cell = item('groupAddNameInput')
        assert add_cell.property('visible') and add_cell.property('enabled')
        assert window.findChild(QObject, 'groupListHint') is None
        title_bottom = item('groupListTitle').mapToScene(QPointF(0, item('groupListTitle').height())).y()
        assert 0 <= item('groupContactPrefix').mapToScene(QPointF(0, 0)).y()-title_bottom <= 7
        assert not item('groupListNotice').property('visible')
        capture('group-empty-plan.png')
        for name in ('手填甲', '手填乙', '手填丙'):
            invoke(add_cell, 'forceActiveFocus')
            add_cell.setProperty('text', name)
            if name == '手填丙': click('groupAddNamesButton')
            else: QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(110)
        assert [row['name'] for row in g.rows] == ['手填甲', '手填乙', '手填丙'], g.status
        assert add_cell.property('text') == '' and '已添加' in item('groupListNotice').property('text'), (add_cell.property('text'), item('groupListNotice').property('text'), g.status)
        # 名单内同名会被跳过，不产生第二行。
        add_cell.setProperty('text', '手填甲')
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(110)
        assert [row['name'] for row in g.rows] == ['手填甲', '手填乙', '手填丙']
        assert '跳过名单内同名' in item('groupListNotice').property('text'), item('groupListNotice').property('text')
        assert add_cell.property('text') == '手填甲'
        # 每行底边一条分隔线，行距为 0，看起来像表格。
        row_item = item('groupName0')
        separators = [child for child in row_item.childItems()
                      if child.metaObject().className() == 'QQuickRectangle' and child.height() == 1]
        assert separators and separators[0].width() == row_item.width()-24, [(c.metaObject().className(), c.height()) for c in row_item.childItems()]
        assert names_view.property('spacing') == 0
        # Ctrl+C 复制选中的姓名；Shift 连选、Ctrl 增删选择。
        modifier_click('groupName0')
        modifier_click('groupName2', Qt.ShiftModifier)
        QTest.keyClick(window, Qt.Key_C, Qt.ControlModifier); QTest.qWait(110)
        assert QGuiApplication.clipboard().text().split('\n') == ['手填甲', '手填乙', '手填丙'], QGuiApplication.clipboard().text()
        assert '已复制 3 个姓名' in item('groupListNotice').property('text'), item('groupListNotice').property('text')
        capture('group-list-copied.png')
        modifier_click('groupName1', Qt.ControlModifier)
        QTest.keyClick(window, Qt.Key_C, Qt.ControlModifier); QTest.qWait(110)
        assert QGuiApplication.clipboard().text().split('\n') == ['手填甲', '手填丙']
        # Ctrl+V 把剪贴板里的多行姓名加入名单，同名自动跳过。
        QGuiApplication.clipboard().setText('粘贴甲\n粘贴乙\n手填甲')
        QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier); QTest.qWait(120)
        assert [row['name'] for row in g.rows] == ['手填甲', '手填乙', '手填丙', '粘贴甲', '粘贴乙'], g.status
        assert '已添加 2 人' in item('groupListNotice').property('text') and '跳过名单内同名 1 人' in item('groupListNotice').property('text')
        capture('group-list-selection.png')
        # Delete 删除选中的待处理姓名，确认后生效；发送记录仍然保留。
        modifier_click('groupName3')
        QTest.keyClick(window, Qt.Key_Delete); QTest.qWait(90)
        assert item('groupRemoveNamesDialog').property('visible')
        click('confirmRemoveNames')
        assert [row['name'] for row in g.rows] == ['手填甲', '手填乙', '手填丙', '粘贴乙'], g.status

        # 填写框保留换行，直接粘贴多行就逐行加入，空行和同名自动跳过。
        invoke(add_cell, 'forceActiveFocus')
        add_cell.setProperty('text', '')
        QGuiApplication.clipboard().setText('填写甲\r\n \r\n填写乙\n手填甲\r\n填写甲')
        QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier); QTest.qWait(120)
        expected_names = ['手填甲', '手填乙', '手填丙', '粘贴乙', '填写甲', '填写乙']
        assert [row['name'] for row in g.rows] == expected_names, g.status
        assert add_cell.property('text') == '' and add_cell.property('activeFocus')
        assert '已添加 2 人' in item('groupListNotice').property('text')

        # 原生粘贴方法同样按行加入；单行粘贴仍等回车，输入法组合回车不添加。
        QGuiApplication.clipboard().setText('原生甲\n原生乙')
        invoke(add_cell, 'paste')
        expected_names += ['原生甲', '原生乙']
        assert [row['name'] for row in g.rows] == expected_names
        QGuiApplication.clipboard().setText('单行姓名')
        invoke(add_cell, 'paste')
        assert add_cell.property('text') == '单行姓名' and [row['name'] for row in g.rows] == expected_names
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(100)
        expected_names += ['单行姓名']
        assert [row['name'] for row in g.rows] == expected_names
        app.sendEvent(window, QInputMethodEvent('组合姓名', []))
        assert add_cell.property('inputMethodComposing')
        QTest.keyClick(window, Qt.Key_Return)
        assert [row['name'] for row in g.rows] == expected_names
        commit_name = QInputMethodEvent(); commit_name.setCommitString('组合姓名')
        app.sendEvent(window, commit_name)
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(100)
        expected_names += ['组合姓名']
        assert [row['name'] for row in g.rows] == expected_names

        # 批量保存失败保留整段输入，回车可重试；全为重复姓名时也保留原文。
        with patch.object(g.store, 'add_recipients', side_effect=RuntimeError('模拟批量添加失败')):
            add_cell.setProperty('text', '重试甲\n重试乙'); QTest.qWait(100)
            assert [row['name'] for row in g.rows] == expected_names
            assert add_cell.property('text') == '重试甲\n重试乙'
            assert '模拟批量添加失败' in item('groupListNotice').property('text')
        QTest.keyClick(window, Qt.Key_Return); QTest.qWait(100)
        expected_names += ['重试甲', '重试乙']
        assert [row['name'] for row in g.rows] == expected_names and add_cell.property('text') == ''
        add_cell.setProperty('text', '填写甲\n填写乙'); QTest.qWait(100)
        assert [row['name'] for row in g.rows] == expected_names and add_cell.property('text') == '填写甲\n填写乙'

        # 长名单批量加入后，添加单元格仍在视口内，亮暗和小窗均可继续填写。
        bulk_names = ['批量学员'+str(i) for i in range(40)]
        add_cell.setProperty('text', '\n'.join(bulk_names)); QTest.qWait(120)
        expected_names += bulk_names
        assert [row['name'] for row in g.rows] == expected_names and add_cell.property('text') == ''
        for mode in ('light', 'dark'):
            assert b.settingsModule.setAppearanceMode(mode)
            for width, height in ((1250, 800), (720, 480)):
                window.resize(width, height); QTest.qWait(100)
                invoke(names_view, 'positionViewAtEnd')
                top = add_cell.mapToScene(QPointF(0, 0)).y()
                assert top >= names_view.mapToScene(QPointF(0, 0)).y()-1
                assert top+add_cell.height() <= names_view.mapToScene(QPointF(0, names_view.height())).y()+1
                for name in ('groupPendingTab', 'groupSentTab'):
                    assert not item(name).property('contentItem').property('truncated'), name
                capture('group-input-'+mode+'-'+str(width)+'.png')

        # 延后处理的多行输入不能跟着切换写入另一个方案。
        draft_list_id = g.selected['id']
        add_cell.setProperty('text', '不应加入甲\n不应加入乙')
        g.selectList(next(i for i, row in enumerate(g.lists) if row['id'] == list_id))
        QTest.qWait(100)
        assert [row['name'] for row in g.store.rows(draft_list_id)] == expected_names
        assert not any(row['name'] in ('不应加入甲', '不应加入乙') for row in g.rows)
        assert add_cell.property('text') == ''
        assert b.settingsModule.setAppearanceMode('light')
        QGuiApplication.clipboard().setText(saved_clipboard)
        invoke(item('groupCenterPage'), 'selectList', next(i for i, row in enumerate(g.lists) if row['id'] == list_id))
        assert g.selected['id'] == list_id

        # Close flushes prefix debounce, but committed bubbles have already persisted.
        item('groupContactPrefix').setProperty('text', '关闭前前缀-')
        compose('关闭前追加')
        window.close(); app.processEvents()
        assert not window.isVisible()
        assert g.store.get(list_id)['prefix'] == '关闭前前缀-'
        assert len(json.loads(g.store.rows(list_id)[0]['content'])) == 4
        assert len(json.loads(g.store.rows(list_id)[2]['content'])) == 3
        # Deleting the current and final temporary plans refreshes selection and empty controls.
        g.store.resolve(protected_list_id,row_id,False);g.refresh();QTest.qWait(80)
        window.show();QTest.qWait(100)
        for _ in range(len(g.lists)):
            target_id=g.selected['id']
            pointer_click('groupListSelector',button=Qt.RightButton)
            pointer_click('groupDeletePlanAction');click('confirmDeletePlan')
            assert g.store.get(target_id) is None,g.status
        assert selector.property('currentIndex')==-1 and g.selected['id']==0
        assert item('groupNamesTable').property('count')==0 and chat.property('messageCount')==0
        assert not item('groupPreviewButton').property('enabled') and not item('groupCopyList').property('enabled')
        capture('group-empty-after-delete.png')
        assert not warnings, warnings
        driver.assert_not_called()
        import shiboken6
        shiboken6.delete(engine)
        shiboken6.delete(b)
        print('Group chat smoke OK: keys/IME, append/edit/cancel/delete/order, files, personal/protected records, draft/revision guards, settings and explicit preview, light/dark/small; no sending')


if __name__ == '__main__': run()
