"""Mouse dragging in the real overview QML, using disposable synthetic batches."""
import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, QPointF, Property, Qt, QUrl, Signal
from PySide6.QtGui import QFontDatabase, QMouseEvent, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.learning_overview import LearningOverview
from app.fonts import configure_font


class WorkflowStub(QObject):
    overviewSourceChanged = Signal()

    @Property(str, constant=True)
    def className(self):
        return '虚构拖拽测试班'


class SettingsStub(QObject):
    @Property(str, constant=True)
    def appearanceMode(self):
        return 'light'


class OverviewOwner(QObject):
    def __init__(self, path):
        super().__init__()
        self.db = SimpleNamespace(path=path)
        self._workflow = WorkflowStub(self)
        self._settings = SettingsStub(self)
        self._overview = LearningOverview(self)

    @Property(QObject, constant=True)
    def workflow(self):
        return self._workflow

    @Property(QObject, constant=True)
    def settingsModule(self):
        return self._settings

    @Property(QObject, constant=True)
    def learningOverview(self):
        return self._overview


def seed(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript('''
            CREATE TABLE campaigns(id INTEGER, class_name TEXT, created_at TEXT);
            CREATE TABLE campaign_students(batch_id INTEGER, student_id TEXT, name TEXT, snapshot TEXT);
            CREATE TABLE campaign_dashboards(batch_id INTEGER, data TEXT);
            CREATE TABLE campaign_followup_status(batch_id INTEGER, student_id TEXT, status TEXT);
        ''')
        for batch in range(1, 4):
            conn.execute('INSERT INTO campaigns VALUES(?,?,?)',
                         (batch, '虚构拖拽测试班', f'2026-10-{batch:02d}T12:00:00'))
            for sid in range(20):
                snapshot = dict(roster_status='在读', completed_courses=str(sid % 11),
                                completed_homework=str(sid % 9), courses='1', homework='1')
                conn.execute('INSERT INTO campaign_students VALUES(?,?,?,?)',
                             (batch, str(sid), f'虚构学员{sid}', json.dumps(snapshot)))
            def rows(done):
                return [dict(lesson=n, completed=done, completedRate=f'{done*5:.2f}%')
                        for n in range(1, 11)]
            dashboard = dict(version=3, total=20, opened=10,
                             courses=rows(16), homework=rows(12 + batch))
            conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',
                         (batch, json.dumps(dashboard)))
        conn.commit()


def drag(app, window, viewport, start, end):
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start.toPoint())
    for step in range(1, 9):
        point = start + (end - start) * step / 8
        app.sendEvent(window, QMouseEvent(
            QEvent.MouseMove, point, point,
            QPointF(window.mapToGlobal(point.toPoint())),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        QTest.qWait(20)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end.toPoint())
    QTest.qWait(50)
    viewport.cancelFlick()


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'scroll.db'
        seed(path)
        owner = OverviewOwner(path)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(x.toString() for x in entries))
        engine.rootContext().setContextProperty('backend', owner)
        engine.loadData(b'''
            import QtQuick
            import QtQuick.Controls
            import "qml"
            ApplicationWindow {
                width: 1050; height: 720; visible: true
                LearningOverview { anchors.fill: parent; anchors.margins: 16 }
            }
        ''', QUrl.fromLocalFile(str(Path('overview-scroll-test.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        QTest.qWait(100)
        scroll = window.findChild(QObject, 'overviewScroll')
        viewport = scroll
        output = Path(os.environ.get('OVERVIEW_SCROLL_SCREENSHOT_DIR', 'output/overview-scroll'))
        output.mkdir(parents=True, exist_ok=True)
        for width, height in ((1050, 720), (600, 480)):
            window.resize(width, height)
            for tab in (0, 3, 1, 2):
                owner.learningOverview.selectTab(tab)
                QTest.qWait(60)
                viewport.cancelFlick()
                viewport.setProperty('contentY', 0)
                QTest.qWait(30)
                assert viewport.property('contentHeight') > viewport.property('height'), (
                    owner.learningOverview.view, viewport.property('contentHeight'),
                    viewport.property('height'), warnings)
                start = viewport.mapToScene(QPointF(35, 180))
                end = viewport.mapToScene(QPointF(35, 50))
                drag(app, window, viewport, start, end)
                moved = viewport.property('contentY')
                print(f'{width}px tab={tab}: dragged={moved:.1f}, '
                      f'interactive={viewport.property("interactive")}', flush=True)
                assert moved > 40, (width, tab, moved)
                assert viewport.property('interactive')
                viewport.setProperty('contentY', 0)
                QTest.qWait(30)
                before = viewport.property('contentY')
                point = viewport.mapToScene(QPointF(35, 100))
                QTest.mouseMove(window, point.toPoint())
                for _ in range(3):
                    wheel = QWheelEvent(
                        point, QPointF(window.mapToGlobal(point.toPoint())),
                        QPointF(0, 0).toPoint(), QPointF(0, -120).toPoint(),
                        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
                    wheel.setTimestamp(round(time.monotonic() * 1000))
                    app.sendEvent(window, wheel)
                    QTest.qWait(30)
                assert viewport.property('contentY') > before, (
                    width, tab, before, viewport.property('contentY'),
                    viewport.property('contentHeight'), viewport.property('height'))
                assert window.grabWindow().save(str(output / f'tab-{tab}-{width}.png'))
        window.resize(1050, 720)
        owner.learningOverview.selectTab(1)
        QTest.qWait(60)
        viewport.cancelFlick()
        viewport.setProperty('contentY', 0)
        QTest.qWait(30)
        chart = window.findChild(QObject, 'overviewRateChart')
        selected = owner.learningOverview.view['selectedLesson']
        start = chart.mapToScene(QPointF(70, 150))
        drag(app, window, viewport, start, start - QPointF(0, 100))
        assert viewport.property('contentY') > 40, 'Dragging over a chart must scroll the page'
        assert owner.learningOverview.view['selectedLesson'] == selected, 'Dragging must not click a point'
        viewport.setProperty('contentY', 0)
        QTest.qWait(30)
        point = chart.mapToScene(QPointF(70, 100))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        QTest.qWait(40)
        assert owner.learningOverview.view['selectedLesson'] == 1
        slider = window.findChild(QObject, 'overviewRateChartRange')
        handle = QQmlProperty.read(slider, 'first.handle')
        start = handle.mapToScene(QPointF(handle.width()/2, handle.height()/2))
        viewport.setProperty('contentY', max(0, viewport.property('contentY') +
                             start.y() - viewport.mapToScene(QPointF(0, 0)).y() - 250))
        QTest.qWait(30)
        start = handle.mapToScene(QPointF(handle.width()/2, handle.height()/2))
        before = viewport.property('contentY')
        drag(app, window, viewport, start, start + QPointF(slider.width()/4, 0))
        assert chart.property('startIndex') > 0, 'The chart range slider must remain draggable'
        assert abs(viewport.property('contentY') - before) < 1
        assert not [m for m in warnings if any(x in m for x in
                   ('Error', 'Binding loop', 'Unable to assign'))], warnings
        window.close()
        engine.deleteLater()
        app.processEvents()
    print('Overview mouse dragging and wheel scrolling passed: four tabs, two sizes, '
          'chart dragging, point clicks and range slider.')


if __name__ == '__main__':
    run()
