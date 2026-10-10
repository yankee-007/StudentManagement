"""Real pointer gestures and adaptive field management, using disposable data."""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, QPointF, QUrl, Qt, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from tests.profile_fixtures import insert_profile


@contextmanager
def capture_role_warnings():
    warnings = []

    def capture(kind, context, message):
        if "Can't assign to existing role" in message:
            warnings.append(message)
        if previous_handler is not None:
            previous_handler(kind, context, message)

    previous_handler = qInstallMessageHandler(capture)
    try:
        yield warnings
    finally:
        qInstallMessageHandler(previous_handler)


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    configure_font(app)
    output = Path('output/profile-field-manager')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None), capture_role_warnings() as role_warnings:
        db_path = Path(folder) / 'fields.db'
        b = Backend(db_path)
        with b.db.connect() as conn:
            conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','示例学员','2026-10-09')")
            insert_profile(conn, '001', '示例学员', 1)
        b.refresh()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(e.toString() for e in entries))
        engine.rootContext().setContextProperty('backend', b)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 860); window.show()
        window.switchModule(1); QTest.qWait(120)
        manager = window.findChild(QObject, 'profileFieldManager')
        manager.open(); QTest.qWait(150)
        order = manager.findChild(QObject, 'profileFieldOrder')
        field_list = order.findChild(QObject, 'profileFieldList')
        preview = order.findChild(QObject, 'fieldDragPreview')
        gap = order.findChild(QObject, 'fieldInsertionGap')
        assert order.height() > 250 and manager.property('wideLayout')
        references = []

        def visual(item, predicate):
            references.append(item)
            if predicate(item):
                return item
            for child in item.childItems():
                found = visual(child, predicate)
                if found is not None:
                    return found

        def row(index):
            item = visual(field_list, lambda obj: obj.objectName() == 'profileFieldRow' and obj.property('index') == index)
            assert item is not None, index
            return item

        def named(item, name):
            found = visual(item, lambda obj: obj.objectName() == name)
            assert found is not None, name
            return found

        def center(item):
            return item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()

        def click(item):
            QTest.mouseMove(window, center(item))
            QTest.qWait(60)
            point = center(item)
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(25)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(60)

        def ids():
            return [field['field_id'] for field in b.profilesModule.managedFields]

        grab_fraction = None

        def verify_anchor(point):
            local = preview.mapFromScene(QPointF(point))
            actual = (local.x() / preview.width(), local.y() / preview.height())
            assert all(abs(a - e) < 0.002 for a, e in zip(actual, grab_fraction)), ('Pressed position must stay under the pointer', actual, grab_fraction)

        def start(index, relative_y=0.5):
            nonlocal grab_fraction
            handle = named(row(index), 'fieldDragHandle')
            card = named(row(index), 'profileFieldCard')
            point = handle.mapToScene(QPointF(handle.width()/2, handle.height()*relative_y)).toPoint()
            original_local = card.mapFromScene(QPointF(point))
            grab_fraction = (original_local.x()/card.width(), original_local.y()/card.height())
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
            assert handle.property('pressed')
            assert not order.property('dragging'), 'A click must not start dragging'
            current = point + QPointF(12, 12).toPoint()
            QTest.mouseMove(window, current, 30)
            assert order.property('dragging') and preview.isVisible()
            verify_anchor(current)
            for _ in range(4):
                QTest.qWait(30)
                verify_anchor(current)
            assert preview.width() < card.width() * 0.95 and 0.5 < preview.opacity() < 0.8
            return point

        def move_to_gap(index, wait=30):
            # Derive the actual space between rendered cards, not the implementation formula.
            if index == 0:
                y = row(0).mapToItem(order, QPointF(0, 0)).y() - order.property('rowSpacing') / 2
            else:
                previous = row(index - 1)
                y = previous.mapToItem(order, QPointF(0, previous.height())).y() + order.property('rowSpacing') / 2
            point = order.mapToScene(QPointF(order.width() * 0.65, y)).toPoint()
            QTest.mouseMove(window, point, wait)
            verify_anchor(point)
            assert order.property('dropIndex') == index, (index, order.property('dropIndex'))
            assert gap.isVisible()
            assert abs(gap.y() + gap.height()/2 - y) <= 1, ('Highlight must sit in the actual gap', gap.y(), y, field_list.property('originY'), field_list.property('contentY'), row(0).mapToItem(field_list.property('contentItem'), QPointF(0, 0)).y())
            return point

        def release(point):
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(60)
            for _ in range(125):
                if not b.profilesModule.fieldOrderSaving:break
                QTest.qWait(40)
            assert not b.profilesModule.fieldOrderSaving
            assert not order.property('dragging') and not preview.isVisible() and not gap.isVisible()

        initial = ids()
        window.grabWindow().save(str(output / 'wide-light.png'))
        # The cursor retains upper, middle and lower grab positions while the card fades/narrows.
        for fraction in (0.1, 0.5, 0.9):
            origin = start(2, fraction)
            moved = origin + QPointF(170, 24).toPoint()
            QTest.mouseMove(window, moved, 30)
            verify_anchor(moved)
            QTest.keyClick(window, Qt.Key_Escape); release(moved)
            assert ids() == initial
        # Move field 4 precisely between fields 1 and 2.
        moved_row = row(3)
        start(3)
        destination = move_to_gap(1)
        QTest.qWait(120)
        assert row(3).property('pickedUp')
        window.grabWindow().save(str(output / 'drag-between-light.png'))
        release(destination)
        expected = initial[:]
        expected.insert(1, expected.pop(3))
        assert ids() == expected
        assert row(1) is moved_row, 'A drop should move the existing card without rebuilding it'
        assert json.loads(b.repo.get_setting('profile_field_order')) == expected
        # Downward insertion uses the index after removal, and a neighbouring gap is a no-op.
        start(1); destination = move_to_gap(4); release(destination)
        expected.insert(3, expected.pop(1))
        assert ids() == expected
        start(1); destination = move_to_gap(2); release(destination)
        assert ids() == expected
        # First insertion and Esc cancel, including movement after cancellation.
        start(3); destination = move_to_gap(0); release(destination)
        expected.insert(0, expected.pop(3))
        assert ids() == expected
        original_point = start(2)
        QTest.keyClick(window, Qt.Key_Escape)
        assert manager.property('visible') and not order.property('dragging')
        QTest.mouseMove(window, original_point + QPointF(20, 30).toPoint(), 30)
        assert not order.property('dragging'), 'Esc must cancel the entire gesture'
        release(original_point)
        assert ids() == expected
        # Releasing outside the list cannot reorder fields.
        start(2)
        outside = order.mapToScene(QPointF(order.width() + 40, 150)).toPoint()
        QTest.mouseMove(window, outside, 30)
        verify_anchor(outside)
        assert order.property('dropIndex') == -1
        release(outside)
        assert ids() == expected
        # A refreshed model invalidates an in-flight drag instead of writing stale positions.
        origin = start(2)
        b.profilesModule.refresh(); QTest.qWait(50)
        assert not order.property('dragging')
        release(origin)
        assert ids() == expected
        # A held stationary pointer continues scrolling, keeping the source alive.
        start(0)
        bottom = order.mapToScene(QPointF(40, order.height()-3)).toPoint()
        QTest.mouseMove(window, bottom, 30)
        before_scroll = field_list.property('contentY')
        QTest.qWait(180)
        assert field_list.property('contentY') > before_scroll
        QTest.qWait(2400)
        verify_anchor(bottom)
        assert order.property('dropIndex') == len(expected), (order.property('dropIndex'), len(expected))
        window.grabWindow().save(str(output / 'drag-last-light.png'))
        release(bottom)
        expected.append(expected.pop(0))
        assert ids() == expected, 'Last insertion must survive viewport recycling'
        field_list.positionViewAtBeginning(); QTest.qWait(60)
        origin = start(1)
        manager.close(); QTest.qWait(80)
        assert not order.property('dragging') and not preview.isVisible()
        release(origin)
        manager.open(); QTest.qWait(100)
        assert ids() == expected, 'Closing the dialog must cancel without saving a move'
        # Non-drag controls and locked visibility preserve the backend contract.
        field_list.positionViewAtBeginning(); QTest.qWait(60)
        click(named(row(0), 'fieldMoveDown'))
        expected.insert(1, expected.pop(0))
        assert ids() == expected
        field_list.positionViewAtBeginning(); QTest.qWait(60)
        locked_index = next(i for i, f in enumerate(b.profilesModule.managedFields) if f['locked'])
        locked = named(row(locked_index), 'fieldVisibility')
        assert not locked.isEnabled() and locked.property('checked')
        visible_index = next(i for i, f in enumerate(b.profilesModule.managedFields) if not f['locked'])
        key = ids()[visible_index]
        visible_row = row(visible_index)
        visibility = named(visible_row, 'fieldVisibility')
        click(visibility)
        assert not next(f for f in b.profilesModule.managedFields if f['field_id'] == key)['show_column']
        assert row(visible_index) is visible_row and not visibility.property('checked')
        b.profilesModule.setFieldVisible(key, True); QTest.qWait(60)
        assert row(visible_index) is visible_row and visibility.property('checked')
        b.profilesModule.setFieldVisible(key, False); QTest.qWait(60)
        assert row(visible_index) is visible_row and not visibility.property('checked')
        assert not role_warnings, role_warnings
        # Add a choice field with explicit labels; it remains present after reopening the database.
        name_input = manager.findChild(QObject, 'profileFieldName')
        type_input = manager.findChild(QObject, 'profileFieldType')
        options = manager.findChild(QObject, 'profileFieldOptions')
        name_input.setProperty('text', '方便联系时间')
        type_input.setProperty('currentIndex', 2)
        options.setProperty('text', '上午\n晚上')
        QTest.qWait(60)
        click(manager.findChild(QObject, 'profileFieldAdd'))
        added = next(f for f in b.profilesModule.managedFields if f['name'] == '方便联系时间')
        assert added['kind'] == 'choice' and added['options'] == ['上午', '晚上']
        field_list.positionViewAtEnd(); QTest.qWait(60)
        click(named(row(len(ids()) - 1), 'fieldRemove'))
        delete_dialog = window.findChild(QObject, 'deleteProfileFieldDialog')
        assert delete_dialog.property('visible') and delete_dialog.property('fieldId') == added['field_id']
        delete_dialog.reject(); QTest.qWait(60)
        assert added['field_id'] in ids(), 'Cancelling deletion must retain the field'
        # Reset only layout: show every surviving field and keep custom definitions and saved values.
        assert b.profilesModule.autoSaveField('001', '方便联系时间', '晚上')
        saved = b.repo.get('001')['profile_fields']
        b.profilesModule.setFieldVisible(added['field_id'], False)
        b.profilesModule.moveField(added['field_id'], 0)
        click(manager.findChild(QObject, 'profileFieldReset'))
        assert ids() == initial + [added['field_id']]
        assert all(f['show_column'] for f in b.profilesModule.managedFields)
        assert b.repo.get('001')['profile_fields'] == saved
        first_y = row(0).mapToItem(order, QPointF(0, 0)).y()
        assert 0 <= first_y <= 12, ('Reset should show the first field', first_y, field_list.property('contentY'), field_list.property('originY'))
        reopened = Backend(db_path)
        assert [f['field_id'] for f in reopened.profilesModule.managedFields] == ids()
        # Both themes and small windows retain the list, done button, and a usable add form.
        for mode in ('light', 'dark'):
            b.settingsModule.setAppearanceMode(mode)
            manager.close(); window.resize(1280, 860); QTest.qWait(60)
            manager.open(); field_list.positionViewAtBeginning(); QTest.qWait(100)
            QTest.mouseMove(window, QPoint(40, 40)); QTest.qWait(60)
            window.grabWindow().save(str(output / f'wide-{mode}.png'))
            start(3); destination = move_to_gap(1); QTest.qWait(100)
            window.grabWindow().save(str(output / f'drag-between-{mode}.png'))
            QTest.keyClick(window, Qt.Key_Escape); release(destination)
            manager.close(); window.resize(720, 480); QTest.qWait(80)
            manager.setProperty('addingField', False); manager.open(); QTest.qWait(100)
            assert not manager.property('wideLayout') and order.height() >= 100
            add_panel = manager.findChild(QObject, 'profileFieldAddPanel')
            assert not add_panel.isVisible()
            window.grabWindow().save(str(output / f'narrow-{mode}.png'))
            click(manager.findChild(QObject, 'profileFieldShowAdd'))
            assert add_panel.isVisible() and not order.isVisible()
            assert add_panel.mapToScene(QPointF(0, add_panel.height())).y() <= manager.findChild(QObject, 'profileFieldDone').mapToScene(QPointF(0, 0)).y(), 'The add form must stay above the footer'
            window.grabWindow().save(str(output / f'narrow-add-{mode}.png'))
            # The compact form scrolls to its primary action and accepts actual pointer clicks.
            add_scroll = manager.findChild(QObject, 'profileFieldAddScroll')
            flick = add_scroll.property('contentItem')
            flick.setProperty('contentY', 0)
            name_input.setProperty('text', '窄窗字段-' + mode)
            type_input.setProperty('currentIndex', 0)
            wheel_point = add_scroll.mapToScene(QPointF(12, add_scroll.height()/2))
            for _ in range(10):
                event = QWheelEvent(wheel_point, QPointF(window.mapToGlobal(wheel_point.toPoint())), QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
                app.sendEvent(window, event); QTest.qWait(25)
            for _ in range(60):
                QTest.qWait(30)
                limit = max(0, flick.property('contentHeight') - flick.height())
                if not flick.property('moving') and not flick.property('flicking') and 0 <= flick.property('contentY') <= limit + 0.1:
                    break
            assert not flick.property('moving') and not flick.property('flicking'), 'Wait for real wheel scrolling to finish before clicking'
            assert flick.property('contentY') > 0
            assert type_input.property('currentIndex') == 0, 'Scrolling the form must not change the field type'
            add_button = manager.findChild(QObject, 'profileFieldAdd')
            assert add_scroll.mapToScene(QPointF(0, 0)).y() <= center(add_button).y() <= add_scroll.mapToScene(QPointF(0, add_scroll.height())).y()
            window.grabWindow().save(str(output / f'narrow-add-scrolled-{mode}.png'))
            click(add_button)
            assert any(f['name'] == '窄窗字段-' + mode for f in b.profilesModule.managedFields), (b.profilesModule.notice, name_input.property('text'), type_input.property('currentIndex'), center(add_button))
            assert order.isVisible() and not add_panel.isVisible()
            done = manager.findChild(QObject, 'profileFieldDone')
            assert center(done).y() < window.height()
            click(done)
            assert not manager.property('visible') and not order.property('dragging')
        window.close(); app.processEvents()
        assert not warnings, warnings
        assert not role_warnings, role_warnings
        print('Profile fields UI OK: compact cards, reset preserving custom fields and values, stable delegates on drop, translucent narrower card, stable pointer anchor, exact gaps, cancellation, scrolling, visibility, add/delete confirmation, persistence, light/dark, 720x480 and 1280x860')


if __name__ == '__main__':
    run()
