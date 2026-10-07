"""Offscreen GUI smoke check for the workbench 完课次数 分栏.

No platform login and no WeCom window: a disposable database is filled through the same
settings path the app uses, then the real Main.qml is loaded and the tab is switched with a
real mouse click (setting `checked` from Python would not fire onClicked).
"""
import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.roster_sync import sync_roster

HEADERS = ["完课次数", "人数", "所占比例", "可跟进人数", "完成人数", "本周是否有退课", "完课率", "完课人数"]
# 5 名在读学员分别完成 4、3、3、1、0 节；已开课节次＝4（第 4 节只有 0 号完成）。
FLAGS = {"0": {"c1": "T", "c2": "T", "c3": "T", "c4": "T"},
         "1": {"c1": "T", "c2": "T", "c3": "T", "c4": "F"},
         "2": {"c1": "T", "c2": "T", "c3": "T", "c4": "F"},
         "3": {"c1": "T", "c2": "F", "c3": "F", "c4": "F"},
         "4": {"c1": "F", "c2": "F", "c3": "F", "c4": "F"}}
# 0、2 号已回复；1 号是「未回复」标记；3 号待反馈；4 号没有反馈记录。
FEEDBACK = {"0": [("学员已回复", "reply")], "1": [("未回复", "unreplied")], "2": [("学员已回复", "reply")]}


def descendants(item, found=None):
    found = [] if found is None else found
    for child in item.childItems():
        found.append(child)
        descendants(child, found)
    return found


def texts(item):
    values = []
    for node in descendants(item):
        try:
            value = node.property("text")
        except Exception:
            continue
        if isinstance(value, str):
            values.append(value)
    return values


def buttons(item, found=None):
    found = [] if found is None else found
    for child in item.childItems():
        if child.metaObject().indexOfProperty("checkable") >= 0 and child.metaObject().indexOfProperty("text") >= 0:
            found.append(child)
        buttons(child, found)
    return found


def rows_of(list_view):
    """Rendered delegate rows, read back by text. ListView keeps one empty placeholder child."""
    result = []
    for child in list_view.property("contentItem").childItems():
        values = texts(child)
        if values:
            result.append(values)
    return result


def click(window, item):
    """Real mouse click on the item centre, with parent offsets accumulated."""
    x = y = 0.0
    node = item
    while node is not None:
        x += float(node.property("x") or 0)
        y += float(node.property("y") or 0)
        node = node.property("parent")
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(x + float(item.property("width")) / 2),
                            int(y + float(item.property("height")) / 2)))
    QTest.qWait(120)


def run():
    QQuickStyle.setStyle("Fusion")
    app = QApplication([])
    # The offscreen platform may not enumerate Windows' installed CJK fonts.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / "dashboard.db")
        term = dict(termId=564, termNo="P2026175", termName="测试班")
        roster = [dict(student_id=f"P2026175{i:03d}A", name=f"学员{i}", status="在读",
                       student_type="新生", nickname="", source="接口学员") for i in range(5)]
        sync_roster(backend.db, term, roster)
        for row in roster:
            backend.repo.update_profile_field(row["student_id"], "微信", "是")
        backend.repo.set_setting("snapshot", json.dumps(
            [dict(student_id=f"P2026175{i:03d}A", flags=FLAGS[str(i)]) for i in range(5)]))
        backend.workflow.createBatch()
        app.processEvents()
        batch = backend.workflow._batch
        with backend.db.connect() as conn:
            for index, entries in FEEDBACK.items():
                for content, kind in entries:
                    conn.execute("INSERT INTO campaign_feedback(batch_id,student_id,content,kind) VALUES(?,?,?,?)",
                                 (batch, f"P2026175{int(index):03d}A", content, kind))
        backend.workflow.reload_rows()
        app.processEvents()

        stats = backend.workflow.dashboard
        assert stats["opened"] == 4, stats["opened"]
        assert stats["cumulative"]["courses"] == 1, stats["cumulative"]
        buckets = stats["completion"]["courses"]
        assert [b["count"] for b in buckets] == [4, 3, 2, 1, 0], buckets
        assert [b["people"] for b in buckets] == [1, 2, 0, 1, 1], buckets
        assert [b["cumulative"] for b in buckets] == [1, 3, 3, 4, 5], buckets
        # 0、2 号已回复计入 4/3 节桶；1 号是「未回复」标记，不计入；3 号待反馈、4 号还没反馈记录不计入。
        assert [b["followable"] for b in buckets] == [1, 1, 0, 0, 0], buckets

        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("studentModel", backend.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path("qml/Main.qml").resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1000, 760)
        window.show()
        app.processEvents()

        panel = window.findChild(QObject, "learningDashboard")
        assert panel is not None
        panel_buttons = buttons(panel)
        expand = next(b for b in panel_buttons if b.property("text") == "展开")
        click(window, expand)
        app.processEvents()
        assert panel.property("expanded")

        lessons = window.findChild(QObject, "learningDashboardList")
        completion = window.findChild(QObject, "learningDashboardCompletionList")
        assert lessons.property("visible") and not completion.property("visible")
        tabs = [b for b in panel_buttons if b.property("text") in ("现有表格 · 累计率", "完课次数")]
        assert [b.property("text") for b in tabs] == ["现有表格 · 累计率", "完课次数"]
        head = texts(panel)
        # Compact metrics share the title row, preserving the cumulative numerators.
        metrics = {node.objectName(): node.property("text") for node in descendants(panel)
                   if node.objectName().startswith("learningMetric-")}
        assert metrics == {"learningMetric-total": "在读 5 人", "learningMetric-courses": "累计完课 1 人", "learningMetric-homework": "累计作业 0 人"}, metrics
        screenshot = os.environ.get("DASHBOARD_SCREENSHOT")
        if screenshot:
            assert window.grabWindow().save(screenshot + "-lessons.png")

        click(window, tabs[1])
        app.processEvents()
        assert panel.property("tab") == 1
        assert not lessons.property("visible") and completion.property("visible")
        assert completion.property("count") == 5, completion.property("count")
        rows = rows_of(completion)
        assert len(rows) == 5, rows
        assert rows[0] == ["4", "1", "20.00%", "1", "", "", "20.00%", "1"], rows[0]
        assert rows[4] == ["0", "1", "20.00%", "0", "", "", "100.00%", "5"], rows[4]
        header = texts(panel)
        for label in HEADERS:
            assert label in header, (label, header)
        if screenshot:
            assert window.grabWindow().save(screenshot + "-completion.png")

        # 分栏选择在其它界面操作后保持，不回落；数据重算后仍显示完课次数。
        backend.workflow.reapplyFilters()
        backend.workflow.setFieldVisible("courses", True)
        app.processEvents()
        assert panel.property("tab") == 1
        assert window.findChild(QObject, "learningDashboardCompletionList").property("visible")
        assert [message for message in warnings if "Error" in message or "ReferenceError" in message] == [], warnings
        window.close()
        app.processEvents()
    print("dashboard completion smoke OK")


if __name__ == "__main__":
    run()
