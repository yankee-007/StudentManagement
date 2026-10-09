"""Group editing/settings/preview integration using a disposable database only."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    # The offscreen platform may not enumerate Windows' installed CJK fonts.
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
        first = g.pendingModel.get(0)
        assert g.saveRecipientField(list_id, first['id'], 0, dict(type='text', text='张三的个人消息'))
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
                if parent.objectName()==name:return parent
                for child in parent.childItems():
                    found=visual_item(child)
                    if found:return found
                return None
            if result is None:result=visual_item(window.contentItem())
            assert result is not None, name
            return result

        def invoke(obj, method, *args):
            assert QMetaObject.invokeMethod(obj, method, *[Q_ARG('QVariant', arg) for arg in args])
            QTest.qWait(60)

        def click(name):
            obj = item(name)
            assert obj.property('enabled'), name
            invoke(obj, 'click')

        def edit_default(index, text):
            obj=item('groupDefaultText'+str(index))
            invoke(obj, 'forceActiveFocus')
            obj.setProperty('text', text)

        def capture(name):
            directory = os.environ.get('GROUP_UI_CAPTURE_DIR')
            if directory:
                path = Path(directory)
                path.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(path / name))

        invoke(window, 'switchModule', 4)
        panel = item('recipientMessages')
        capture('group-center.png')

        # The unified row is always visible; reloading a draft writes nothing.
        assert item('groupDefaultRow').property('visible')
        assert window.findChild(QObject, 'groupBulkEditButton') is None
        assert window.findChild(QObject, 'groupColumnSelector') is None
        assert window.findChild(QObject, 'groupColumnMessageDialog') is None
        before = [r['content'] for r in g.rows]
        edit_default(0, '取消的修改')
        assert panel.property('defaultsDirty')
        click('groupResetDefaults')
        assert [r['content'] for r in g.rows] == before
        edit_default(0, '{姓名}，本周资料已经更新。')
        capture('group-default-edit.png')
        click('groupApplyDefaults')
        content = [json.loads(r['content']) for r in g.rows]
        assert content[0][0]['text'] == '张三的个人消息'
        assert content[1][0]['text'] == '李四，本周资料已经更新。'
        assert all(r[1]['type'] == 'file' and r[2]['text'] == '完成后请回复，感谢配合。' for r in content)

        # Add/remove operate on the draft; an empty addition blocks preview and list switching.
        click('groupAddDefault')
        edit_default(3, '新增-{姓名}')
        click('groupApplyDefaults')
        assert all(len(json.loads(r['content'])) == 4 for r in g.rows)
        click('groupRemoveDefault')
        click('groupApplyDefaults')
        assert all(len(json.loads(r['content'])) == 3 for r in g.rows)
        click('groupAddDefault')
        click('groupPreviewButton')
        assert not item('groupSendPreview').property('visible')
        assert panel.property('defaultsDirty') and g.pendingFieldCount == 3
        invoke(window, 'switchModule', 1)
        assert window.property('moduleIndex') == 4
        click('groupResetDefaults')

        # File selection happens directly in the same row and is validated before apply.
        with patch.object(g, 'chooseMessageFile', return_value=str(attachment)):
            click('groupDefaultFile1')
        assert json.loads(g.rows[1]['content'])[1]['path'] == str(attachment)

        # An ordinary button edits precisely the selected person's selected field.
        panel.setProperty('selectedRow', g.pendingModel.get(1))
        panel.setProperty('selectedField', 2)
        click('groupEditCellButton')
        assert item('groupSingleCellDialog').property('visible')
        item('groupSingleCellText').setProperty('text', '李四的补充说明')
        click('saveGroupSingleCell')
        assert json.loads(g.rows[1]['content'])[2]['text'] == '李四的补充说明'
        assert json.loads(g.rows[0]['content'])[2]['text'] == '完成后请回复，感谢配合。'

        # Sending settings live behind the explicit configuration entry and still auto-save.
        assert not item('groupSettingsPanel').property('visible')
        click('groupConfigurationButton')
        assert item('groupSettingsPanel').property('visible')
        capture('group-configuration.png')
        assert item('groupPreviewButton').parent().property('visible')
        assert window.findChild(QObject, 'saveGroupSettings') is None
        assert window.findChild(QObject, 'resetGroupSettings') is None
        # The per-message option sits directly under "paste then Enter" and follows it.
        confirm_send = item('groupConfirmSend')
        single_send = item('groupSingleSend')
        assert single_send.property('text') == '每条消息单独发送'
        assert single_send.property('enabled') and single_send.property('y') > confirm_send.property('y')
        click('groupCloseConfiguration')
        # An empty contact prefix only warns: the preview can still continue.
        click('groupPreviewButton')
        reminder = item('groupEmptyPrefixReminder')
        assert reminder.property('visible') and not item('groupSendPreview').property('visible')
        capture('group-empty-prefix.png')
        click('groupEmptyPrefixBack')
        assert not reminder.property('visible') and not item('groupSendPreview').property('visible')
        click('groupPreviewButton')
        assert reminder.property('visible')
        click('groupEmptyPrefixContinue')
        assert item('groupSendPreview').property('visible')
        click('groupPreviewBack')
        item('groupContactPrefix').setProperty('text', '测试班-')
        confirm_send.setProperty('checked', False)
        QTest.qWait(750)
        assert g.selected['prefix'] == '测试班-'
        assert not g.selected['options']['confirm_send']
        assert not single_send.property('enabled'), '未勾选回车发送时不应还能选择每条消息单独发送'
        assert not g.preview

        # Preview is per person, preserves file/text order, and never invokes the driver.
        click('groupPreviewButton')
        preview = item('groupSendPreview')
        assert preview.property('visible') and len(g.preview) == 3
        assert item('groupPreviewSummary').property('text').startswith('仅粘贴，不发送 · 按下列顺序粘贴')
        assert item('groupPreviewContact').property('text') == '联系人：测试班-张三'
        assert item('groupStartButton').property('text') == '开始粘贴 · 3 人'
        click('groupPreviewNext')
        assert item('groupPreviewContact').property('text') == '联系人：测试班-李四'
        current = preview.property('currentRecipient').toVariant()
        assert [r['type'] for r in current['content']] == ['text', 'file', 'text']
        assert current['content'][2]['text'] == '李四的补充说明'
        capture('group-preview.png')
        click('groupPreviewEditPerson')
        editor = item('recipientMessageEditor')
        assert editor.property('visible') and editor.property('recipientId') == g.rows[1]['id']
        invoke(editor, 'close')

        # Auto-saving a changed setting invalidates the previously confirmed preview.
        item('groupContactPrefix').setProperty('text', '改过的前缀-')
        QTest.qWait(750)
        assert g.selected['prefix'] == '改过的前缀-'
        assert not g.preview and not g.start()
        driver.assert_not_called()
        item('groupContactPrefix').setProperty('text', '测试班-')
        QTest.qWait(750)

        # Small-window layout still exposes primary actions and preview controls.
        window.resize(720, 480)
        QTest.qWait(100)
        capture('group-center-small.png')
        assert item('groupPreviewButton').property('visible')
        assert item('groupRecipientList').height() > 70
        assert item('groupDefaultText0').parentItem().height() >= 16
        table=item('groupRecipientList')
        table.setProperty('contentY', 44)
        QTest.qWait(60)
        assert abs(item('groupNamesTable').property('contentY')-table.property('contentY')) < 1
        assert abs(item('groupInformationTable').property('contentY')-table.property('contentY')) < 1
        item('groupNamesTable').setProperty('contentY',0)
        QTest.qWait(60)
        assert abs(table.property('contentY')) < 1
        invoke(item('groupDefaultText2'), 'forceActiveFocus')
        assert item('groupDefaultsViewport').property('contentX') > 0
        click('groupPreviewButton')
        assert preview.property('width') <= window.width() and preview.property('height') <= window.height()
        assert item('groupStartButton').property('visible')
        capture('group-preview-small.png')
        click('groupPreviewBack')
        capture('group-center-small.png')

        # The existing contact-risk acknowledgment remains required and resets each preview.
        assert g.saveOptions(list_id, '测试班-', dict(confirm_send=True, verify_contact=False))
        invoke(item('groupCenterPage'), 'loadOptions')
        assert item('groupSingleSend').property('enabled'), '恢复回车发送后应重新可选'
        click('groupPreviewButton')
        assert item('groupPreviewSummary').property('text').startswith('回车发送 · ')
        assert item('groupAcceptRisk').property('visible')
        assert not item('groupStartButton').property('enabled')
        item('groupAcceptRisk').setProperty('checked', True)
        assert item('groupStartButton').property('enabled')
        click('groupPreviewBack')
        click('groupPreviewButton')
        assert not item('groupStartButton').property('enabled')
        click('groupPreviewBack')

        # While sending, UI edit/preview actions are disabled as before.
        g._worker = object()
        g._notify_activity()
        app.processEvents()
        assert not item('groupApplyDefaults').property('enabled')
        assert not item('groupAddDefault').property('enabled')
        assert not item('groupDefaultText0').property('enabled')
        assert not item('groupConfigurationButton').property('enabled')
        assert not item('groupContactPrefix').property('enabled')
        assert not item('groupPreviewButton').property('enabled')
        g._worker = None
        g._notify_activity()

        # Dark mode keeps both the unified row and the roster readable.
        window.resize(1250, 800)
        assert b.settingsModule.setAppearanceMode('dark')
        QTest.qWait(100)
        capture('group-center-dark.png')
        window.resize(720, 480)
        QTest.qWait(100)
        capture('group-center-dark-small.png')
        assert b.settingsModule.setAppearanceMode('light')

        # A changed roster never silently overwrites the pending unified-row draft.
        edit_default(0, '仍保留的草稿')
        assert g.saveRecipientField(list_id, g.rows[1]['id'], 0, dict(type='text',text='外部编辑'))
        click('groupPreviewButton')
        assert panel.property('defaultsDirty') and not preview.property('visible')
        assert item('groupDefaultText0').property('text') == '仍保留的草稿'
        click('groupResetDefaults')

        # A names-only roster still displays synchronized name/information rows.
        assert g.copyList('仅人员名单',False)
        QTest.qWait(80)
        assert g.pendingCount==3 and g.pendingFieldCount==0
        assert item('groupRecipientList').property('rows')==3
        assert item('groupNamesTable').property('rows')==3
        assert item('groupInformationTable').property('rows')==3
        capture('group-names-only.png')
        click('groupAddDefault')
        edit_default(0,'新增给-{姓名}')
        click('groupApplyDefaults')
        assert g.pendingFieldCount==1
        assert json.loads(g.rows[2]['content'])[0]['text']=='新增给-王五'

        # A quick list switch flushes edits to the old list, never the new one.
        assert g.createCustom('另一份名单', '甲|第二份消息')
        other_id = g.selected['id']
        item('groupContactPrefix').setProperty('text', '第二份前缀-')
        edit_default(0, '第二份统一消息-{姓名}')
        invoke(item('groupCenterPage'), 'selectList', next(i for i,r in enumerate(g.lists) if r['id']==list_id))
        assert g.store.get(other_id)['prefix'] == '第二份前缀-'
        assert json.loads(g.store.rows(other_id)[0]['content'])[0]['text'] == '第二份统一消息-甲'
        assert g.selected['id'] == list_id
        assert item('groupContactPrefix').property('text') == '测试班-'

        # Closing before the debounce expires still saves the active list's edit.
        click('groupAddDefault')
        window.close()
        app.processEvents()
        assert window.isVisible() and panel.property('defaultsDirty')
        click('groupResetDefaults')
        item('groupContactPrefix').setProperty('text', '关闭前前缀-')
        edit_default(2, '关闭前默认消息')
        window.close()
        app.processEvents()
        assert g.store.get(list_id)['prefix'] == '关闭前前缀-'
        assert json.loads(g.store.rows(list_id)[0]['content'])[2]['text'] == '关闭前默认消息'
        assert json.loads(g.store.rows(list_id)[1]['content'])[2]['text'] == '李四的补充说明'
        assert not warnings, warnings
        driver.assert_not_called()
        import shiboken6
        shiboken6.delete(engine)
        shiboken6.delete(b)
        print('Group interaction smoke OK: unified defaults, draft cancellation/add/remove, personal edits, settings, ordered preview, light/dark/small layout, activity guards; no sending')


if __name__ == '__main__':
    run()
