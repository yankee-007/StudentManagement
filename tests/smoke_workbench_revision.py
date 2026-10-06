"""Load the revised workbench against a disposable database, without WeCom."""
import tempfile
import json
from unittest.mock import patch
import os
import time
import statistics
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QUrl, QMetaObject, Q_ARG, Qt
from PySide6.QtGui import QFontDatabase, QInputMethodEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app.backend import Backend
from app.fonts import configure_font
from app.roster_sync import sync_roster


def run():
    QQuickStyle.setStyle("Fusion")
    app = QApplication([])
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / "workbench.db")
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("studentModel", backend.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path("qml/Main.qml").resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1000, 700)
        window.show()
        app.processEvents()
        for name in ("studentTable", "campaignColumnFilter", "campaignFieldDialog",
                     "campaignExportDialog", "campaignListDialog", "campaignFloatingWindow"):
            assert window.findChild(QObject, name), name
        term = dict(termId=551, termNo="P2026169", termName="测试班")
        sid = "P2026169001A"
        size = int(os.environ.get('WORKBENCH_STUDENTS', '1'))
        roster = [dict(student_id=f'P2026169{i:03d}A', name='学员' if i == 1 else f'测试学员{i}', status='在读',
                       student_type='新生', nickname='', source='接口学员') for i in range(1, size + 1)]
        sync_roster(backend.db, term, roster)
        backend.repo.update_profile_field(sid, "微信", "是")
        backend.repo.set_setting("snapshot", json.dumps([dict(student_id=r['student_id'], flags={"c1":"T","z1":"F"}) for r in roster]))
        backend.workflow.createBatch()
        app.processEvents()
        refresh_button = window.findChild(QObject, "fetchLearningButton")
        create_button = window.findChild(QObject, "createCampaignButton")
        assert refresh_button.property("text") == "刷新数据", refresh_button.property("text")
        assert refresh_button.property("visible") and create_button.property("visible")
        assert refresh_button.mapToScene(QPointF(0, 0)).x() < create_button.mapToScene(QPointF(0, 0)).x()
        screenshot = os.environ.get("WORKBENCH_SCREENSHOT")
        if screenshot:
            assert window.grabWindow().save(screenshot)
        detail = window.findChild(QObject, "mainCampaignDetail")
        def visual(item, name):
            for child in item.childItems():
                if child.objectName() == name:
                    return child
                found = visual(child, name)
                if found:
                    return found
            return None
        draft = visual(detail, "feedbackDraft")
        assert draft is not None
        assert draft.height() < 40
        menu = draft.property('menu')
        assert visual(detail, 'feedbackShortcutButton') is None and menu.property('count') == 4
        assert backend.workflow.feedbackShortcuts == ['答应补课', '未接听电话']
        draft.forceActiveFocus()
        draft.setProperty("text", "界面草稿")
        app.processEvents()
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]["feedback"] == ""
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]["feedback"] == "界面草稿"
        assert visual(detail, "feedbackDraft") == draft and draft.hasActiveFocus()
        latencies = []
        with patch.object(backend.workflow.store, 'save_feedback', wraps=backend.workflow.store.save_feedback) as save:
            for i in range(100):
                start = time.perf_counter()
                draft.setProperty('text', '连续输入' + str(i))
                app.processEvents()
                latencies.append((time.perf_counter() - start) * 1000)
                assert visual(detail, 'feedbackDraft') == draft and draft.hasActiveFocus()
            save.assert_not_called()
            draft.setProperty('cursorPosition', 2)
            QTest.qWait(650)
            assert save.call_count == 1
            assert draft.property('cursorPosition') == 2
        print(f'Feedback typing: students={size}, events=100, median={statistics.median(latencies):.2f}ms, p95={sorted(latencies)[94]:.2f}ms, writes=1')
        draft.setProperty("text", "界面修改")
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]["feedback"] == "界面修改"
        # Deliver real input-method events through the Qt Quick focus window.
        assert app.sendEvent(window, QInputMethodEvent('军训', []))
        assert draft.property('inputMethodComposing')
        QTest.qWait(650)
        assert draft.property('inputMethodComposing')
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '界面修改'
        commit = QInputMethodEvent()
        commit.setCommitString('军训')
        assert app.sendEvent(window, commit)
        QTest.qWait(650)
        assert not draft.property('inputMethodComposing')
        assert '军训' in backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback']
        draft.setProperty('text', '界面修改')
        QTest.qWait(650)
        def open_shortcuts():
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, draft.mapToScene(QPointF(draft.width() / 2, draft.height() / 2)).toPoint())
            app.processEvents()
            assert menu.property('visible')
            top = draft.mapToScene(QPointF(0, 0)).y()
            assert menu.property('y') >= top + draft.height() or menu.property('y') + menu.property('height') <= top
        def pick_shortcut(name):
            item = visual(menu.property('contentItem'), name)
            assert item is not None, name
            assert QMetaObject.invokeMethod(item, 'triggered')
            app.processEvents()
        open_shortcuts()
        assert draft.property('text') == '界面修改'
        draft.setProperty('cursorPosition', len('界面修改'))
        QTest.keyClick(window, Qt.Key_X)
        app.processEvents()
        assert draft.property('text') == '界面修改x' and not menu.property('visible')
        draft.setProperty('text', '界面修改')
        open_shortcuts()
        if os.environ.get('WORKBENCH_MENU_SCREENSHOT'):
            assert window.grabWindow().save(os.environ['WORKBENCH_MENU_SCREENSHOT'])
        pick_shortcut('feedbackShortcutOption0')
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '界面修改；答应补课'
        open_shortcuts()
        pick_shortcut('feedbackShortcutOption1')
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '界面修改；答应补课；未接听电话'
        open_shortcuts()
        footer = visual(menu.property('contentItem'), 'addFeedbackShortcutItem')
        assert footer.y() >= visual(menu.property('contentItem'), 'feedbackShortcutOption1').y()
        pick_shortcut('addFeedbackShortcutItem')
        shortcut_dialog = detail.findChild(QObject, 'feedbackShortcutDialog')
        shortcut_input = shortcut_dialog.findChild(QObject, 'feedbackShortcutInput')
        assert shortcut_dialog.property('visible')
        shortcut_input.setProperty('text', '已联系家长')
        assert QMetaObject.invokeMethod(shortcut_dialog, 'accept')
        app.processEvents()
        assert menu.property('count') == 5
        assert draft.property('text') == '界面修改；答应补课；未接听电话'
        open_shortcuts()
        pick_shortcut('feedbackShortcutOption2')
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '界面修改；答应补课；未接听电话；已联系家长'
        draft.forceActiveFocus()
        draft.setProperty('text', '')
        open_shortcuts()
        pick_shortcut('feedbackShortcutOption0')
        QTest.qWait(650)
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '答应补课'
        if size > 1:
            open_shortcuts()
            backend.workflow.selectRow(1)
            pick_shortcut('feedbackShortcutOption0')
            QTest.qWait(650)
            assert backend.workflow.selected['feedback'] == ''
            backend.workflow.selectRow(0)
        draft.forceActiveFocus()
        draft.setProperty('text', '界面修改')
        QTest.qWait(650)
        if screenshot:
            assert window.grabWindow().save(screenshot)
        backend.workflow.setFieldVisible("courses", False)
        app.processEvents()
        assert "courses" not in [field["key"] for field in detail.property("fields").toVariant()]
        backend.workflow.setFieldVisible("courses", True)
        backend.workflow.moveField("courses", 0)
        app.processEvents()
        assert detail.property("fields").toVariant()[0]["key"] == "courses"
        floating=window.findChild(QObject,"campaignFloatingWindow")
        with patch.object(backend.profileCompanion,'_active_wecom_title',return_value='学员'):
            assert QMetaObject.invokeMethod(floating,'show')
            app.processEvents()
            float_draft=visual(floating.contentItem(),'floatingFeedbackDraft')
            assert float_draft is not None
            assert float_draft.property('text')=='界面修改'
            assert float_draft.property('menu').property('count') == 5
            float_draft.forceActiveFocus()
            float_draft.setProperty('text','浮窗草稿')
            app.processEvents()
            QTest.qWait(650)
            assert backend.workflow.store.rows(backend.workflow._batch,sid)[0]['feedback']=='浮窗草稿'
            assert visual(floating.contentItem(),'floatingFeedbackDraft') == float_draft
            float_menu = float_draft.property('menu')
            def open_float_shortcuts():
                QTest.mouseClick(floating, Qt.LeftButton, Qt.NoModifier, float_draft.mapToScene(QPointF(float_draft.width() / 2, float_draft.height() / 2)).toPoint())
            open_float_shortcuts()
            app.processEvents()
            float_top = float_draft.mapToScene(QPointF(0, 0)).y()
            assert float_menu.property('y') >= float_top + float_draft.height() or float_menu.property('y') + float_menu.property('height') <= float_top
            if os.environ.get('WORKBENCH_FLOAT_MENU_SCREENSHOT'):
                assert floating.grabWindow().save(os.environ['WORKBENCH_FLOAT_MENU_SCREENSHOT'])
            assert QMetaObject.invokeMethod(visual(float_menu.property('contentItem'), 'feedbackShortcutOption0'), 'triggered')
            QTest.qWait(650)
            assert backend.workflow.store.rows(backend.workflow._batch,sid)[0]['feedback']=='浮窗草稿；答应补课'
            if size > 1:
                for index in range(20):
                    assert backend.workflow.addFeedbackShortcut(f'更多快捷选项{index}')
                open_float_shortcuts()
                app.processEvents()
                assert float_menu.property('height') < float_menu.property('implicitHeight')
                viewport = float_menu.property('contentItem')
                assert viewport.property('contentHeight') > viewport.property('height') and viewport.property('interactive')
                viewport.setProperty('contentY', viewport.property('contentHeight') - viewport.property('height'))
                app.processEvents()
                last_item = visual(viewport, 'addFeedbackShortcutItem')
                last_top = last_item.mapToScene(QPointF(0, 0)).y()
                assert last_top >= float_menu.property('y') and last_top + last_item.height() <= float_menu.property('y') + float_menu.property('height')
                assert float_menu.property('y') >= float_top + float_draft.height() or float_menu.property('y') + float_menu.property('height') <= float_top
                assert QMetaObject.invokeMethod(float_menu, 'close')
            float_draft.forceActiveFocus()
            float_draft.setProperty('text','关闭前输入')
            assert backend.workflow._pending_feedback, (float_draft.property('activeFocus'), float_draft.property('text'))
            assert QMetaObject.invokeMethod(floating,'close')
            assert backend.workflow.store.rows(backend.workflow._batch,sid)[0]['feedback']=='关闭前输入', backend.workflow.store.rows(backend.workflow._batch,sid)[0]['feedback']
        assert not window.findChild(QObject, "markUnrepliedButton").property("visible")
        view = window.findChild(QObject, "campaignViewSelector")
        assert view.property('count') == 2
        view.setProperty("currentIndex", 1)
        assert QMetaObject.invokeMethod(view, "activated", Q_ARG(int, 1))
        app.processEvents()
        assert window.findChild(QObject, "markUnrepliedButton").property("visible")
        campaign_dialog = window.findChild(QObject, "campaignListDialog")
        create_button = window.findChild(QObject, "createCampaignSelection")
        assert QMetaObject.invokeMethod(campaign_dialog, "open")
        app.processEvents()
        assert campaign_dialog.property("recordKeys").toVariant() == backend.workflow.recipientKeys
        window.findChild(QObject, "campaignNamesOnly").setProperty("checked", True)
        assert QMetaObject.invokeMethod(create_button, "click")
        app.processEvents()
        assert backend.groupCenter.selected["content_template"] == []
        assert QMetaObject.invokeMethod(campaign_dialog, "open")
        app.processEvents()
        assert not window.findChild(QObject, "campaignNamesOnly").property("checked")
        assert QMetaObject.invokeMethod(create_button, "click")
        app.processEvents()
        assert backend.groupCenter.selected["content_template"][0]["type"] == "text"
        export_dialog = window.findChild(QObject, "campaignExportDialog")
        assert QMetaObject.invokeMethod(export_dialog, "open")
        app.processEvents()
        ordered = export_dialog.property("orderedFields").toVariant()
        moved = [ordered[-1]] + ordered[:-1]
        export_dialog.setProperty("orderedFields", moved)
        export_dialog.setProperty("selectedKeys", [moved[0]["key"]])
        app.processEvents()
        assert QMetaObject.invokeMethod(export_dialog, "close")
        assert QMetaObject.invokeMethod(export_dialog, "open")
        app.processEvents()
        assert export_dialog.property("orderedFields").toVariant()[0]["key"] == moved[0]["key"]
        assert export_dialog.property("selectedKeys").toVariant() == [moved[0]["key"]]
        export_dialog.close()
        assert not [message for message in warnings if "Error" in message or "ReferenceError" in message], warnings
        assert backend.workflow.queueFeedbackForSelection(backend.workflow.editorKey, '主窗口关闭前输入')
        window.close()
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]['feedback'] == '主窗口关闭前输入'
        app.processEvents()


if __name__ == "__main__":
    run()
