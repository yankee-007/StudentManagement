"""设置页 QML 冒烟：滚动、并排布局、班期对应关系缓存与课程自动对应。"""
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend

sys.stdout.reconfigure(encoding='utf-8')

QQuickStyle.setStyle('Fusion')
app = QApplication([])

with tempfile.TemporaryDirectory() as folder:
    backend = Backend(Path(folder) / 'test.db')
    settings = backend.settingsModule
    backend.workflow._classes[0]['term_id'] = '551'
    settings._homework_classes = [{'id': 23, 'name': '正式课py169', 'course_ids': [2]},
                                  {'id': 31, 'name': '正式课py175', 'course_ids': [5]}]
    settings._classes_loaded(settings._homework_classes)
    assert settings.saveBinding('551', 23), settings.notice

    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.rootContext().setContextProperty('backend', backend)
    engine.rootContext().setContextProperty('studentModel', backend.studentModel)
    engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    # 高度刻意偏小，验证内容超出时页面可以滚动。
    window.resize(1280, 460)
    window.show()
    assert backend.settingsModule.termClasses, 'no term classes to bind'
    window.switchModule(3)
    QTest.qWait(200)

    def item(name):
        found = window.findChild(QObject, name)
        assert found is not None, name
        return found

    cards = [item('completionAccountCard'), item('homeworkAccountCard')]
    for card in cards:
        assert card.property('visible') and card.property('width') > 200, (card.property('width'), card.property('height'))
    assert abs(cards[0].property('y') - cards[1].property('y')) < 1, '账号卡片没有并排'
    assert cards[0].property('x') + cards[0].property('width') <= cards[1].property('x') + 1, '账号卡片横向重叠'
    # 输入框、按钮必须留在卡片内，文字不能被裁掉。
    for card in cards:
        for field in ('Username', 'Password', 'VerifyLogin'):
            child = card.findChild(QObject, card.property('platform') + field)
            assert child is not None, field
            assert child.property('x') >= 0 and child.property('x') + child.property('width') <= card.property('width') + 1, \
                (field, child.property('x'), child.property('width'), card.property('width'))

    course = item('settingCourseBox')
    assert not course.property('visible'), '单课程班级不应显示课程下拉框'
    assert item('settingClassBox').property('currentIndex') == 0, '重启后没有带出已确认的作业班级'
    binding = settings.bindingFor('551')
    assert binding['class_id'] == 23 and binding['course_id'] == 2, binding

    # 重新打开设置页 / 刷新状态后，切换班期仍能带出已确认的对应关系。
    window.switchModule(0)
    QTest.qWait(50)
    window.switchModule(3)
    QTest.qWait(150)
    assert item('settingClassBox').property('currentIndex') == 0, '重新进入设置页后没有带出对应关系'
    settings.refresh()
    QTest.qWait(100)
    assert item('settingClassBox').property('currentIndex') == 0, '刷新状态后对应关系被清空'

    scroll = item('settingsScroll')
    assert scroll.property('contentHeight') > scroll.property('height'), \
        (scroll.property('contentHeight'), scroll.property('height'))
    scroll.setProperty('contentY', 0)
    QTest.qWait(50)
    down = QPoint(round(scroll.property('width') / 2), round(scroll.property('height') / 2))
    for _ in range(3):
        QGuiApplication.sendEvent(window, QWheelEvent(QPointF(down), QPointF(window.mapToGlobal(down)), QPoint(),
            QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False))
        QTest.qWait(30)
    assert scroll.property('contentY') > 0, '滚轮没有滚动设置页'

    # 下拉框只列出一个课程时滚轮也应滚动页面，而不是切换选项。
    term = item('settingTermBox')
    term.setProperty('currentIndex', 0)
    scroll.setProperty('contentY', 0)
    QTest.qWait(50)
    combo = QPoint(round(term.property('width') / 2), round(term.property('height') / 2))
    windowPoint = term.mapToScene(QPointF(combo)).toPoint()
    for _ in range(3):
        QGuiApplication.sendEvent(window, QWheelEvent(QPointF(windowPoint), QPointF(window.mapToGlobal(windowPoint)), QPoint(),
            QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False))
        QTest.qWait(30)
    assert scroll.property('contentY') > 0, '光标停在班期下拉框上时页面无法滚动'
    assert term.property('currentIndex') == 0, '滚轮不应改动画期下拉框的选中项'

    # 窄窗口改为上下排列，内容依旧可以滚动。
    window.resize(760, 700)
    QTest.qWait(200)
    cards = [item('completionAccountCard'), item('homeworkAccountCard')]
    assert abs(cards[0].property('x') - cards[1].property('x')) < 1, '窄窗口没有改为上下排列'
    assert cards[1].property('y') > cards[0].property('y'), '窄窗口账号卡片重叠'
    assert cards[0].property('width') > 600, '窄窗口账号卡片没有铺满'
    assert scroll.property('contentWidth') == cards[0].property('width') or cards[0].property('width') <= scroll.property('contentWidth') + 1

    assert not warnings, warnings
    engine.deleteLater()
    app.processEvents()
print('Settings module QML smoke OK')
