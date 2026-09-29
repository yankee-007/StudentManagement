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
            assert result is not None, name
            return result

        def invoke(obj, method, *args):
            assert QMetaObject.invokeMethod(obj, method, *[Q_ARG('QVariant', arg) for arg in args])
            QTest.qWait(60)

        def click(name):
            obj = item(name)
            assert obj.property('enabled'), name
            invoke(obj, 'click')

        def capture(name):
            directory = os.environ.get('GROUP_UI_CAPTURE_DIR')
            if directory:
                path = Path(directory)
                path.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(path / name))

        invoke(window, 'switchModule', 4)
        panel = item('recipientMessages')
        capture('group-center.png')

        # Explicit column entry opens the existing editor; cancellation writes nothing.
        before = [r['content'] for r in g.rows]
        click('groupBulkEditButton')
        dialog = item('groupColumnMessageDialog')
        assert dialog.property('visible') and dialog.property('impactCount') == 2
        item('groupColumnTemplateInput').setProperty('text', '取消的修改')
        invoke(dialog, 'close')
        assert [r['content'] for r in g.rows] == before
        click('groupBulkEditButton')
        item('groupColumnTemplateInput').setProperty('text', '{姓名}，本周资料已经更新。')
        capture('group-bulk-edit.png')
        click('saveGroupColumnField')
        content = [json.loads(r['content']) for r in g.rows]
        assert content[0][0]['text'] == '张三的个人消息'
        assert content[1][0]['text'] == '李四，本周资料已经更新。'
        assert all(r[1]['type'] == 'file' and r[2]['text'] == '完成后请回复，感谢配合。' for r in content)

        # An ordinary button edits precisely the selected person's selected field.
        panel.setProperty('selectedRow', g.pendingModel.get(1))
        panel.setProperty('selectedField', 2)
        click('groupEditCellButton')
        assert item('groupSingleCellDialog').property('visible')
        item('groupSingleCellText').setProperty('text', '李四的补充说明')
        click('saveGroupSingleCell')
        assert json.loads(g.rows[1]['content'])[2]['text'] == '李四的补充说明'
        assert json.loads(g.rows[0]['content'])[2]['text'] == '完成后请回复，感谢配合。'

        # Left settings save automatically and the single preview action stays beside the heading.
        assert item('groupSettingsPanel').property('visible')
        assert item('groupPreviewButton').parent().property('visible')
        assert window.findChild(QObject, 'saveGroupSettings') is None
        assert window.findChild(QObject, 'resetGroupSettings') is None
        item('groupContactPrefix').setProperty('text', '测试班-')
        item('groupConfirmSend').setProperty('checked', False)
        QTest.qWait(750)
        assert g.selected['prefix'] == '测试班-'
        assert not g.selected['options']['confirm_send']
        assert not g.preview

        # Preview is per person, preserves file/text order, and never invokes the driver.
        click('groupPreviewButton')
        preview = item('groupSendPreview')
        assert preview.property('visible') and len(g.preview) == 3
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
        assert item('groupPreviewButton').property('visible')
        assert item('groupRecipientList').height() > 70
        click('groupPreviewButton')
        assert preview.property('width') <= window.width() and preview.property('height') <= window.height()
        assert item('groupStartButton').property('visible')
        capture('group-preview-small.png')
        click('groupPreviewBack')
        capture('group-center-small.png')

        # The existing contact-risk acknowledgment remains required and resets each preview.
        assert g.saveOptions(list_id, '测试班-', dict(confirm_send=True, verify_contact=False))
        invoke(item('groupCenterPage'), 'loadOptions')
        click('groupPreviewButton')
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
        assert not item('groupBulkEditButton').property('enabled')
        assert not item('groupContactPrefix').property('enabled')
        assert not item('groupPreviewButton').property('enabled')
        g._worker = None
        g._notify_activity()

        # A quick list switch flushes edits to the old list, never the new one.
        assert g.createCustom('另一份名单', '甲|第二份消息')
        other_id = g.selected['id']
        item('groupContactPrefix').setProperty('text', '第二份前缀-')
        invoke(item('groupCenterPage'), 'selectList', 1)
        assert g.store.get(other_id)['prefix'] == '第二份前缀-'
        assert g.selected['id'] == list_id
        assert item('groupContactPrefix').property('text') == '测试班-'

        # Closing before the debounce expires still saves the active list's edit.
        item('groupContactPrefix').setProperty('text', '关闭前前缀-')
        window.close()
        app.processEvents()
        assert g.store.get(list_id)['prefix'] == '关闭前前缀-'
        assert not warnings, warnings
        driver.assert_not_called()
        import shiboken6
        shiboken6.delete(engine)
        shiboken6.delete(b)
        print('Group interaction smoke OK: batch/personal edits, cancel, settings, ordered preview, small layout, activity guards; no sending')


if __name__ == '__main__':
    run()
