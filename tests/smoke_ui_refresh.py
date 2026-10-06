"""Exercise real navigation and responsive panes with disposable, fictitious data."""
import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QUrl, Slot, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.roster_sync import sync_roster


class RestartProbe(QObject):
    @Slot(result=bool)
    def requestRestart(self):
        return True


def run():
    QQuickStyle.setStyle("Fusion")
    app = QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output = Path(os.environ.get("UI_REFRESH_SCREENSHOTS", "output/ui-refresh"))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / "test.db")
        rows = [dict(student_id=f"P2026169{i:03d}A", name=f"示例学员{i:02d}",
                     status="在读", student_type="新生", nickname="", source="接口学员")
                for i in range(1, 33)]
        sync_roster(backend.db, dict(termId=551, termNo="P2026169", termName="界面测试班"), rows)
        for row in rows:
            backend.repo.update_profile_field(row["student_id"], "微信", "是")
        backend.repo.set_setting("snapshot", json.dumps([
            dict(student_id=row["student_id"], flags={"c1": "T", "z1": "F", "c2": "F", "z2": "F"})
            for row in rows]))
        backend.workflow.createBatch()
        assert backend.groupCenter.createStructured("界面测试名单", "示例甲\n示例乙", [
            dict(type="text", text="{姓名}同学，请查收学习提醒。")])
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        restart = RestartProbe()
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("restartController", restart)
        engine.load(QUrl.fromLocalFile(str(Path("qml/Main.qml").resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.show()

        def find(name):
            item = window.findChild(QQuickItem, name)
            def visual(parent):
                for child in parent.childItems():
                    if child.objectName() == name:
                        return child
                    found = visual(child)
                    if found is not None:
                        return found
                return None
            if item is None:
                item = visual(window.contentItem())
            assert item is not None, name
            return item

        def inside(item):
            point = item.mapToScene(QPointF(0, 0))
            assert point.x() >= 0 and point.y() >= 0, (item.objectName(), point)
            assert point.x() + item.width() <= window.width() + 1, (item.objectName(), point, item.width())
            assert point.y() + item.height() <= window.height() + 1, (item.objectName(), point, item.height())

        def click(name):
            item = find(name)
            assert item.isVisible() and item.isEnabled(), name
            inside(item)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                            item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint())
            QTest.qWait(100)

        for width, height in ((1280, 800), (1000, 700), (720, 480)):
            window.resize(width, height)
            QTest.qWait(100)
            inside(find("debugRestartButton"))
            for module in (0, 1, 2, 3, 4, 5, 6):
                click(f"moduleButton{module}")
                assert window.property("moduleIndex") == module
                if module == 0:
                    window.grabWindow().save(str(output / f"workbench-check-{width}.png"))
                    assert find("studentTable").height() > 40, (width, height, find("studentTable").height())
                    inside(find("fetchLearningButton"))
                    inside(find("createCampaignButton"))
                    if width < 1000:
                        window.setProperty("campaignDetailOpen", False)
                        QTest.qWait(50)
                        assert find("studentTable").isVisible()
                        click("campaignDetailToggle")
                        assert find("mainCampaignDetail").isVisible() and not find("studentTable").isVisible()
                        click("campaignDetailToggle")
                        assert find("studentTable").isVisible()
                elif module == 1 and width == 720:
                    page = find("profileModule")
                    page.setProperty("cardExpanded", False)
                    QTest.qWait(50)
                    click("profileDetailToggle")
                    assert page.property("cardExpanded") and not find("profileTable").isVisible()
                    click("profileDetailToggle")
                    assert find("profileTable").isVisible()
                elif module == 4:
                    inside(find("groupPreviewButton"))
                elif module == 5:
                    inside(find("remarkTimeoutInput"))
                elif module == 6:
                    inside(find("liveAbsenceIncludeZero"))
                    inside(find("liveAbsenceCreateList"))
                assert window.grabWindow().save(str(output / f"module-{module}-{width}.png"))
        assert not warnings, warnings
        window.close()
        print("UI refresh OK: seven real navigation buttons, restart visibility, narrow pane switching; 21 screenshots; no login or sending")


if __name__ == "__main__":
    run()
