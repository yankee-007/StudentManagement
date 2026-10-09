"""Real QML chat/settings/preview integration; disposable data and mocked sending."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG, Qt, QPointF, QPoint
from PySide6.QtGui import QFontDatabase, QInputMethodEvent, QWheelEvent
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

        def double_name(row):
            obj = item('groupName'+str(row))
            pos = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, pos)
            QTest.qWait(90)

        def pointer_click(name, double=False):
            obj = item(name)
            pos = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            action = QTest.mouseDClick if double else QTest.mouseClick
            action(window, Qt.LeftButton, Qt.NoModifier, pos)
            QTest.qWait(90)

        invoke(window, 'switchModule', 4)
        panel = item('recipientMessages')
        chat = item('groupMessageChat')
        assert item('groupTemplatePanel').property('visible')
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
        assert chat.property('editingIndex') == 0 and g.defaultFields[0]['value'] == 'Tab 保存'
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(70)
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
        assert item('groupSettingsPanel').mapToScene(QPointF(0,0)).x() < item('groupTemplatePanel').mapToScene(QPointF(0,0)).x() < item('groupRecipientsPanel').mapToScene(QPointF(0,0)).x()
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

        # Protected rows are viewed through the same name entry, and expose result resolution.
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

        # Close flushes prefix debounce, but committed bubbles have already persisted.
        item('groupContactPrefix').setProperty('text', '关闭前前缀-')
        compose('关闭前追加')
        window.close(); app.processEvents()
        assert not window.isVisible()
        assert g.store.get(list_id)['prefix'] == '关闭前前缀-'
        assert len(json.loads(g.store.rows(list_id)[0]['content'])) == 4
        assert len(json.loads(g.store.rows(list_id)[2]['content'])) == 3
        assert not warnings, warnings
        driver.assert_not_called()
        import shiboken6
        shiboken6.delete(engine)
        shiboken6.delete(b)
        print('Group chat smoke OK: keys/IME, append/edit/cancel/delete/order, files, personal/protected records, draft/revision guards, settings and explicit preview, light/dark/small; no sending')


if __name__ == '__main__': run()
