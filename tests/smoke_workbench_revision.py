"""Load the revised workbench against a disposable database, without WeCom."""
import tempfile
import json
from unittest.mock import patch
import os
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuick import QQuickItem
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

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
        sync_roster(backend.db, term, [dict(student_id=sid, name="学员", status="在读",
                                            student_type="新生", nickname="", source="接口学员")])
        backend.repo.update_profile_field(sid, "微信", "是")
        backend.repo.set_setting("snapshot", json.dumps([dict(student_id=sid, flags={"c1":"T","z1":"F"})]))
        backend.workflow.createBatch()
        app.processEvents()
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
        draft.forceActiveFocus()
        draft.setProperty("text", "界面草稿")
        app.processEvents()
        assert backend.workflow.store.rows(backend.workflow._batch, sid)[0]["draft"] == "界面草稿"
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
        assert float_draft.property('text')=='界面草稿'
        float_draft.forceActiveFocus()
        float_draft.setProperty('text','浮窗草稿')
        app.processEvents()
        assert backend.workflow.store.rows(backend.workflow._batch,sid)[0]['draft']=='浮窗草稿'
        assert QMetaObject.invokeMethod(floating,'close')
        assert not window.findChild(QObject, "markUnrepliedButton").property("visible")
        view = window.findChild(QObject, "campaignViewSelector")
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
        window.close()
        app.processEvents()


if __name__ == "__main__":
    run()
