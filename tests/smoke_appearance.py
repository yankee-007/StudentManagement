"""Real theme clicks, palette inheritance, charts and windows with synthetic data."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, Qt, QUrl, QTimer, QDate
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.calendar_widget import LeaveCalendar
from app.fonts import configure_font
from app.roster_sync import sync_roster
from tests.test_learning_overview import dashboard, seed


def visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual(child, name)
        if found is not None:
            return found
    return None


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    configure_font(app)
    output = Path('output/appearance')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder, patch('app.settings_module.get_password', return_value=None):
        path = Path(folder) / 'appearance.db'
        b = Backend(path)
        b.profileCompanion._active_wecom_title = lambda: '示例学员01'
        rows = [dict(student_id=f'P2026169{i:03d}A', name=f'示例学员{i:02d}', status='在读',
                     student_type='新生', nickname='', source='接口学员') for i in range(1, 25)]
        sync_roster(b.db, dict(termId=551, termNo='P2026169', termName='主题测试班'), rows)
        for row in rows:
            b.repo.update_profile_field(row['student_id'], '微信', '是')
        b.repo.set_setting('snapshot', json.dumps([
            dict(student_id=r['student_id'], flags={'c1': 'T', 'z1': 'F', 'c2': 'F', 'z2': 'F'}) for r in rows]))
        b.workflow.createBatch()
        with b.db.connect() as conn:
            seed(conn, 2, dashboard(lessons=(1, 2, 3, 4, 5)))
        b.workflow.reload_batches()
        b.workflow.selectBatch(1)
        b.profilesModule.activate()
        assert b.groupCenter.createStructured('主题测试名单', '示例甲\n示例乙', [dict(type='text', text='{姓名}同学，请查收。')])
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(e.toString() for e in entries))
        engine.rootContext().setContextProperty('backend', b)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.show(); QTest.qWait(100)

        def find(name):
            obj = window.findChild(QObject, name)
            if obj is None:
                obj = visual(window.contentItem(), name)
            assert obj is not None, name
            return obj

        def click(name):
            item = find(name)
            assert item.isVisible() and item.isEnabled(), name
            p = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, p)
            QTest.qWait(70)

        floating = [find(name) for name in ('profileFloatingWindow', 'campaignFloatingWindow')]
        # Toggling a theme must retain the exact editor and its unsaved account draft.
        window.switchModule(3); QTest.qWait(70)
        account = find('completionUsername')
        account.setProperty('text', 'unsaved-draft')
        click('appearanceDarkButton')
        assert b.settingsModule.appearanceMode == 'dark'
        assert find('completionUsername') == account and account.property('text') == 'unsaved-draft'
        assert window.color() == QColor('#141c27')
        for float_window in floating:
            assert float_window.color() == window.color()
        assert QQmlProperty.read(find('appearanceDarkButton'), 'palette.text') == QColor('#e6edf7')
        click('appearanceLightButton')
        assert window.color() == QColor('#eef2f6')

        for mode in ('light', 'dark'):
            window.resize(1280, 800)
            window.switchModule(3)
            find('settingsScroll').setProperty('contentY', 0)
            QTest.qWait(50)
            click('appearanceDarkButton' if mode == 'dark' else 'appearanceLightButton')
            ink = QColor('#e6edf7' if mode == 'dark' else '#203047')
            surface = QColor('#1e2938' if mode == 'dark' else '#ffffff')
            for width, height in ((1280, 800), (1000, 700), (720, 480)):
                window.resize(width, height); QTest.qWait(70)
                for module in (0, 7, 1, 2, 6, 5, 3, 4):
                    click(f'moduleButton{module}')
                    assert window.property('moduleIndex') == module
                    if module == 3:
                        find('settingsScroll').setProperty('contentY', 0)
                    QTest.qWait(50)
                    assert window.grabWindow().save(str(output / f'{mode}-module-{module}-{width}.png'))
                # Standard TextArea and popup use the theme palette, not OS light colors.
                dialog = find('customGroupDialog')
                dialog.open(); QTest.qWait(70)
                assert QQmlProperty.read(dialog, 'palette.window') == surface
                assert QQmlProperty.read(find('groupCustomTitle'), 'palette.text') == ink
                assert window.grabWindow().save(str(output / f'{mode}-dialog-{width}.png'))
                dialog.close()
            window.resize(1280, 800); window.switchModule(7); QTest.qWait(80)
            chart = find('overviewRateChart')
            before = chart.property('startIndex')
            b.settingsModule.setAppearanceMode('light' if mode == 'dark' else 'dark')
            QTest.qWait(80)
            assert chart.property('startIndex') == before
            assert window.grabWindow().save(str(output / f'{mode}-chart-live-switch.png'))
            b.settingsModule.setAppearanceMode(mode)
            for float_window in floating:
                if float_window.objectName() == 'campaignFloatingWindow':
                    b.workflow.selectBatch(0)
                    b.profileCompanion._active_wecom_title = lambda: '虚构学员A'
                else:
                    b.profileCompanion._active_wecom_title = lambda: '示例学员01'
                float_window.show(); QTest.qWait(100)
                assert QQmlProperty.read(float_window, 'palette.text') == ink
                if float_window.objectName() == 'campaignFloatingWindow':
                    assert b.campaignCompanion.selected['name'] == '虚构学员A'
                    editor = visual(float_window.contentItem(), 'floatingFeedbackDraft')
                    assert editor is not None, 'floatingFeedbackDraft'
                    assert editor.property('color') == ink, editor.property('color')
                assert float_window.grabWindow().save(str(output / f'{mode}-{float_window.objectName()}.png'))
                float_window.close()
            # Exercise the real modal date chooser, capture it and accept a synthetic date.
            selected = QDate.currentDate().addDays(5).toString('yyyy-MM-dd')
            calendar_checks = []
            def accept_date():
                modal = QApplication.activeModalWidget()
                calendar = modal.findChild(LeaveCalendar)
                calendar_checks.append(calendar.palette().color(QPalette.Base) if calendar else None)
                calendar_checks.append(calendar.headerTextFormat().background().color() if calendar else None)
                calendar_checks.append(modal.grab().save(str(output / f'{mode}-calendar.png')))
                modal.accept()
            QTimer.singleShot(100, accept_date)
            assert b.chooseDate(selected) == selected
            assert calendar_checks == [surface, surface, True], calendar_checks
            QTimer.singleShot(100, lambda: QApplication.activeModalWidget().reject())
            assert b.chooseProfileDate(selected) == selected
        assert not warnings, warnings
        window.close()
        # Reload real QML against the persisted global preference.
        reopened = Backend(path)
        assert reopened.settingsModule.appearanceMode == 'dark'
        reload_engine = QQmlApplicationEngine()
        reload_engine.rootContext().setContextProperty('backend', reopened)
        reload_engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert reload_engine.rootObjects()
        assert reload_engine.rootObjects()[0].color() == QColor('#141c27')
        print('Appearance QML OK: real clicks, persistence, eight pages at three sizes, popups, floating windows and live chart switch')


if __name__ == '__main__':
    run()
