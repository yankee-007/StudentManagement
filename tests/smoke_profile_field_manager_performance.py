"""Measure actual QML drops with a disposable 1000-student roster."""
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
        b = Backend(Path(folder) / 'bench.db')
        with b.db.connect() as conn:
            for i in range(1000):
                sid, name = str(i + 1), f'虚构学员{i + 1:04d}'
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-10-09'))
                insert_profile(conn, sid, name, i)
        b.profilesModule.refresh()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(i.toString() for i in entries))
        engine.rootContext().setContextProperty('backend', b)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 860); window.show(); window.switchModule(1); QTest.qWait(200)
        manager = window.findChild(QObject, 'profileFieldManager')
        manager.open(); QTest.qWait(150)
        order = manager.findChild(QObject, 'profileFieldOrder')
        field_list = order.findChild(QObject, 'profileFieldList')
        references = []

        def find(item, predicate):
            references.append(item)
            if predicate(item):
                return item
            for child in item.childItems():
                found = find(child, predicate)
                if found is not None:
                    return found

        def row(index):
            item = find(field_list, lambda obj: obj.objectName() == 'profileFieldRow' and obj.property('index') == index)
            assert item is not None
            return item

        elapsed, repaint = [], []
        roster, selection = b.profilesModule.tableModel.rows, b.profilesModule.selected
        with patch.object(b.repo, 'list_students', wraps=b.repo.list_students) as reads:
            for _ in range(8):
                field_list.positionViewAtBeginning(); QTest.qWait(80)
                source = row(0)
                handle = find(source, lambda item: item.objectName() == 'fieldDragHandle')
                start = handle.mapToScene(QPointF(handle.width()/2, handle.height()/2)).toPoint()
                QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
                QTest.mouseMove(window, start + QPoint(12, 12), 30)
                target = row(2)
                y = target.mapToItem(order, QPointF(0, target.height())).y() + order.property('rowSpacing') / 2
                finish = order.mapToScene(QPointF(40, y)).toPoint()
                QTest.mouseMove(window, finish, 50)
                assert order.property('dropIndex') == 3
                began = perf_counter()
                QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, finish)
                elapsed.append((perf_counter() - began) * 1000)
                app.processEvents()
                window.grabWindow()
                repaint.append((perf_counter() - began) * 1000)
                assert not order.property('dragging')
                assert row(2) is source, 'Moving a field must preserve its delegate'
                assert b.profilesModule.tableModel.rows is roster
                assert b.profilesModule.selected is selection
                QTest.qWait(80)
            assert reads.call_count == 0, 'Dropping fields must not reread the full roster'
            result = dict(students=1000, drops=len(elapsed),
                          release_median_ms=round(statistics.median(elapsed), 2), release_max_ms=round(max(elapsed), 2),
                          repaint_median_ms=round(statistics.median(repaint), 2), repaint_max_ms=round(max(repaint), 2),
                          full_roster_reads=reads.call_count, qml_warnings=warnings)
        assert not warnings, warnings
        output = Path('output/profile-field-manager')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'perf-after.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        assert b.profilesModule.flushFieldOrder()
        manager.close(); window.close(); app.processEvents()


if __name__ == '__main__':
    run()
