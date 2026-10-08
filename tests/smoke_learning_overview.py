"""Real QML overview, synthetic batches, no platform/WeCom or production DB."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from tests.test_learning_overview import dashboard, records, seed


def visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual(child, name)
        if found is not None:
            return found
    return None


def click(window, item):
    point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
    if item.objectName() == 'overviewHomeworkCandidatesButton':
        scroll = visual(window.contentItem(), 'overviewScroll')
        top = scroll.mapToScene(QPointF(0, 0)).y()
        viewport = scroll.property('contentItem')
        viewport.setProperty('contentY', max(0, viewport.property('contentY') + point.y() - top - scroll.height()/2))
        QTest.qWait(40)
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
    QTest.qWait(60)


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder)/'overview.db')
        with b.db.connect() as conn:
            seed(conn, 1)
            seed(conn, 2, dashboard(lessons=(1, 2, 3, 4, 5), homework=1), marks={'A':'是', 'B':'否'})
            members = records()
            for sid, snap in members:
                snap.update(homework='1,2,3,4,5' if sid in ('A','B') else '',
                            completed_courses='5',
                            completed_homework='0' if sid in ('A','B') else '5')
                if sid == 'C':
                    snap.update(courses='2,3,4,5', completed_courses='1', homework='1', completed_homework='4')
            seed(conn, 3, dashboard(lessons=(1, 2, 3, 4, 5)), members,
                 marks={'A':'是', 'B':'否', 'C':'否', 'D':'否'})
        b.workflow.reload_batches()
        b.contactOpener.setDefaultPrefix('py169')
        b.workflow.filterRows('all', '虚构学员A')
        cursor = b.workflow.editorKey
        assert b.workflow.queueFeedbackForSelection(cursor, '合成反馈')
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(x.toString() for x in entries))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 820); window.show(); QTest.qWait(100)
        page = window.findChild(QObject, 'learningOverviewPage')
        assert page
        nav = visual(window.contentItem(), 'moduleButton7')
        assert nav is not None
        click(window, nav)
        assert window.property('moduleIndex') == 7
        assert b.workflow.editorKey == cursor
        assert b.workflow.store.rows(3,'A')[0]['feedback'] == '合成反馈'
        assert b.learningOverview.view['latest']
        charts = [visual(window.contentItem(), name) for name in ('overviewRateChart','overviewGapChart')]
        assert all(charts)
        assert charts[0].property('width') > 350
        chart = charts[0]
        chart.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Home)
        assert chart.property('inspected') == 0
        QTest.keyClick(window, Qt.Key_Right)
        assert chart.property('inspected') == 1
        slider = visual(window.contentItem(), 'overviewRateChartRange')
        assert QQmlProperty.read(slider,'second.value') == chart.property('endIndex')
        slider.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Right)
        QTest.qWait(40)
        assert chart.property('startIndex') > 0, chart.property('startIndex')
        handle = QQmlProperty.read(slider, 'first.handle')
        start = handle.mapToScene(QPointF(handle.width()/2,handle.height()/2))
        end = start + QPointF(slider.width()/4,0)
        before_zoom = chart.property('startIndex')
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start.toPoint())
        QTest.mouseMove(window,end.toPoint(),30)
        QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,end.toPoint())
        QTest.qWait(40)
        assert chart.property('startIndex') > before_zoom
        # All tabs are keyboard operable; selectors are native controls.
        tab = visual(window.contentItem(), 'overviewTab0')
        tab.forceActiveFocus(); QTest.keyClick(window, Qt.Key_Right)
        assert b.learningOverview.tabIndex == 3
        assert visual(window.contentItem(), 'overviewTarget0').isVisible()
        QTest.keyClick(window, Qt.Key_Right)
        assert b.learningOverview.tabIndex == 1
        history = visual(window.contentItem(), 'overviewHistoryBatch')
        history.setProperty('currentIndex', 2); history.activated.emit(2); QTest.qWait(30)
        assert not b.learningOverview.view['lessonRows']
        assert b.learningOverview.view['completionRows']
        tab = visual(window.contentItem(), 'overviewTab1')
        tab.forceActiveFocus(); QTest.keyClick(window, Qt.Key_Right)
        assert b.learningOverview.tabIndex == 2
        assert len(b.learningOverview.view['rateChart']['series']) == 4
        assert charts[1].property('chart').toVariant()['thresholds'] == [5,10,15]
        QTest.keyClick(window, Qt.Key_End)
        assert b.learningOverview.tabIndex == 2
        QTest.keyClick(window, Qt.Key_Home)
        assert b.learningOverview.tabIndex == 0
        QTest.keyClick(window, Qt.Key_Right)
        assert b.learningOverview.tabIndex == 3
        target = visual(window.contentItem(), 'overviewTarget0')
        target.forceActiveFocus(); target.selectAll()
        QTest.keyClick(window, Qt.Key_9); QTest.keyClick(window, Qt.Key_2)
        assert visual(window.contentItem(), 'overviewTarget0') == target
        assert target.property('activeFocus') and target.property('text') == '92'
        assert b.learningOverview.targets[0] == '92'
        gap_trend = visual(window.contentItem(), 'overviewTrend2')
        assert gap_trend.property('minimum') == 0 and gap_trend.property('maximum') >= 50
        assert b.workflow.editorKey == cursor
        assert b.learningOverview.historyIndex == 2
        output = Path(os.environ.get('OVERVIEW_SCREENSHOT_DIR', 'output/learning-overview'))
        output.mkdir(parents=True, exist_ok=True)
        for width, height in ((1280,820),(1000,700),(720,480)):
            window.resize(width,height); QTest.qWait(80)
            for index, name in ((0,'latest'),(1,'history'),(2,'compare'),(3,'goals')):
                click(window, visual(window.contentItem(), 'overviewTab'+str(index)))
                scroll = visual(window.contentItem(), 'overviewScroll')
                scroll.property('contentItem').setProperty('contentY', 0)
                QTest.qWait(70)
                assert window.grabWindow().save(str(output/f'{name}-{width}.png'))
                assert page.width() <= width
                if index==3:
                    button = visual(window.contentItem(), 'overviewHomeworkCandidatesButton')
                    assert button.isVisible() and button.isEnabled()
                    click(window, button)
                    dialog = window.findChild(QObject, 'overviewHomeworkDialog')
                    assert dialog.property('visible')
                    table = visual(window.contentItem(), 'overviewHomeworkTable')
                    table_rows = table.property('rows')
                    if hasattr(table_rows, 'toVariant'): table_rows = table_rows.toVariant()
                    assert table.property('headers').toVariant() == ['姓名','学号','欠交作业节次','联系人']
                    assert table_rows[0]['cells'] == ['虚构学员A','A','1、2、3、4、5']
                    assert table_rows[1]['cells'] == ['虚构学员B','B','1、2、3、4、5']
                    assert len(table_rows) == 2
                    assert dialog.property('title') == '第1～5节 · 补作业名单'
                    if width == 1280:
                        click(window, visual(window.contentItem(), 'overviewHomeworkContactOptions'))
                        prefix = visual(window.contentItem(), 'overviewHomeworkContactPrefix')
                        assert prefix.property('text') == 'py169'
                        prefix.setProperty('text', 'camp-')
                        click(window, visual(window.contentItem(), 'overviewHomeworkKeepContactFloat'))
                        click(window, visual(window.contentItem(), 'overviewHomeworkVerifyContact'))
                        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(30)
                        with patch('app.contact_opener.ContactOpenTask') as task:
                            click(window, visual(window.contentItem(), 'overviewOpenContactB'))
                            assert task.call_args.args[0] == 'camp-虚构学员B'
                            assert not task.call_args.kwargs['keep_float'] and not task.call_args.kwargs['verify_contact']
                            assert not visual(window.contentItem(), 'overviewOpenContactA').isEnabled()
                            assert b.workflow.editorKey == cursor
                            b.contactOpener._result('已搜索联系人（未验证）：camp-虚构学员B')
                            b.contactOpener._finished(); QTest.qWait(40)
                        assert visual(window.contentItem(), 'overviewOpenContactA').isEnabled()
                        assert b.contactOpener.campaignContactPrefix == 'camp-'
                    assert window.grabWindow().save(str(output/f'homework-candidates-{width}.png'))
                    b.learningOverview.selectLesson(1); QTest.qWait(40)
                    assert dialog.property('visible')
                    assert dialog.property('title') == '第1节 · 补作业名单'
                    filter_text = visual(window.contentItem(), 'overviewHomeworkFilter').property('text')
                    assert '排除第1节内仍有未完课程' in filter_text
                    assert '保留第1节内仍有欠交作业' in filter_text
                    table_rows = table.property('rows')
                    if hasattr(table_rows, 'toVariant'): table_rows = table_rows.toVariant()
                    assert [row['cells'][1:] for row in table_rows] == [['A','1'],['B','1'],['C','1']]
                    assert window.grabWindow().save(str(output/f'homework-first-lesson-{width}.png'))
                    if width == 720:
                        viewport = visual(window.contentItem(), 'overviewHomeworkScroll').property('contentItem')
                        bottom = max(0, viewport.property('contentHeight')-viewport.property('height'))
                        assert bottom > 0
                        viewport.setProperty('contentY', bottom); QTest.qWait(40)
                        assert viewport.property('contentY') > 0
                        assert window.grabWindow().save(str(output/'homework-first-lesson-bottom-720.png'))
                        viewport.setProperty('contentY', 0)
                    b.learningOverview.selectLesson(5); QTest.qWait(40)
                    assert len(b.learningOverview.view['homeworkCandidates']['rows']) == 2
                    QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(30)
                    assert not dialog.property('visible')
                if index==2:
                    # Hover and select the same point used in cumulative table.
                    chart = visual(window.contentItem(), 'overviewRateChart')
                    chart.forceActiveFocus(); QTest.keyClick(window, Qt.Key_Home)
                    QTest.keyClick(window, Qt.Key_Return)
                    assert b.learningOverview.view['selectedLesson'] == 1
                    assert b.workflow.editorKey == cursor
                if index in (0,2,3):
                    viewport = scroll.property('contentItem')
                    viewport.setProperty('contentY', max(0,viewport.property('contentHeight')-viewport.property('height')))
                    QTest.qWait(70)
                    assert window.grabWindow().save(str(output/f'{name}-bottom-{width}.png'))
        b.learningOverview.selectLesson(1)
        b.settingsModule.setAppearanceMode('dark'); QTest.qWait(40)
        click(window, visual(window.contentItem(), 'overviewHomeworkCandidatesButton'))
        assert dialog.property('visible') and dialog.property('title') == '第1节 · 补作业名单'
        assert len(b.learningOverview.view['homeworkCandidates']['rows']) == 3
        assert window.grabWindow().save(str(output/'homework-first-lesson-dark-720.png'))
        viewport = visual(window.contentItem(), 'overviewHomeworkScroll').property('contentItem')
        viewport.setProperty('contentY', max(0, viewport.property('contentHeight')-viewport.property('height')))
        QTest.qWait(40)
        with patch('app.contact_opener.ContactOpenTask') as task:
            button = visual(window.contentItem(), 'overviewOpenContactC')
            assert button.isEnabled()
            button.forceActiveFocus(); QTest.keyClick(window, Qt.Key_Space); QTest.qWait(40)
            assert task.call_args.args[0] == 'camp-虚构学员C'
            b.contactOpener._result('已搜索联系人（未验证）：camp-虚构学员C')
            b.contactOpener._finished(); QTest.qWait(40)
        assert window.grabWindow().save(str(output/'homework-first-lesson-dark-bottom-720.png'))
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(30)
        b.settingsModule.setAppearanceMode('light')
        window.resize(1280,820); window.switchModule(0); QTest.qWait(80)
        with patch('app.contact_opener.ContactOpenTask') as task:
            button = visual(window.contentItem(), 'openCampaignContact')
            assert button.isVisible() and button.isEnabled()
            click(window, button)
            assert task.call_args.args[0] == 'camp-虚构学员A'
            assert not task.call_args.kwargs['verify_contact'] and not task.call_args.kwargs['keep_float']
            b.contactOpener._result('已搜索联系人（未验证）：camp-虚构学员A')
            b.contactOpener._finished(); QTest.qWait(40)
        assert b.workflow.editorKey == cursor
        window.switchModule(7); QTest.qWait(80)
        b.learningOverview.selectBatch('goal', 1); QTest.qWait(40)
        scroll.property('contentItem').setProperty('contentY', 0); QTest.qWait(40)
        assert b.learningOverview.view['homeworkCandidates']['rows'] == []
        click(window, visual(window.contentItem(), 'overviewHomeworkCandidatesButton'))
        assert dialog.property('visible')
        b.learningOverview.selectBatch('goal', 2); QTest.qWait(40)
        assert not dialog.property('visible')
        assert not visual(window.contentItem(), 'overviewHomeworkCandidatesButton').isEnabled()
        b.learningOverview.selectBatch('goal', 0); QTest.qWait(40)
        click(window, visual(window.contentItem(), 'overviewHomeworkCandidatesButton'))
        b.workflow._classes.append(dict(name='空测试班', path=str(Path(folder)/'other.db')))
        b.workflow.selectClass(1); QTest.qWait(80)
        assert not b.learningOverview.view['available']
        assert not dialog.property('visible')
        assert not [m for m in warnings if ('Error' in m or 'Binding loop' in m or 'Unable to assign' in m)], warnings
        click(window, visual(window.contentItem(),'moduleButton0'))
        window.close(); engine.deleteLater(); app.processEvents()
        print('Learning overview QML passed: navigation, flush/cursor, tabs, selectors, keyboard/zoom, targets/focus, homework candidates, class isolation and three sizes.')


if __name__ == '__main__': run()
