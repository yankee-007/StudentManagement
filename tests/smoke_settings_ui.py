"""设置页 QML 冒烟：账号输入/验证/保存、滚动布局与班期对应关系。"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font

sys.stdout.reconfigure(encoding='utf-8')

QQuickStyle.setStyle('Fusion')
app = QApplication([])
font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
if font.exists():
    QFontDatabase.addApplicationFont(str(font))
configure_font(app)

vault = {}
with tempfile.TemporaryDirectory() as folder, \
        patch('keyring.get_password', side_effect=lambda service, user: vault.get((service, user))), \
        patch('keyring.set_password', side_effect=lambda service, user, password: vault.update({(service, user): password})):
    backend = Backend(Path(folder) / 'test.db')
    settings = backend.settingsModule
    assert settings.saveAccount('completion', 'saved-completion', 'saved-password')
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

    def click(control):
        point = control.mapToScene(QPointF(control.property('width') / 2, control.property('height') / 2)).toPoint()
        assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), point
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(30)

    def enter(control, text):
        click(control)
        assert control.property('activeFocus'), control.objectName()
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for index, char in enumerate(text):
            QTest.keyClick(window, Qt.Key(ord(char.upper())))
            assert control.property('text') == text[:index + 1], (control.objectName(), control.property('text'))

    # Real clicks/keystrokes must survive every verification-state notification,
    # both for an existing account and for a platform with no saved account.
    completion = item('completionUsername')
    homework = item('homeworkUsername')
    settings._verification['completion'] = {'state': 'error', 'message': '模拟验证失败'}
    settings.changed.emit()
    enter(completion, 'newcompletion')
    assert 'completion' not in settings.verification
    enter(homework, 'newhomework')
    enter(item('completionPassword'), 'newpassword')
    enter(item('homeworkPassword'), 'otherpassword')
    assert completion.property('text') == 'newcompletion'
    assert homework.property('text') == 'newhomework'
    # Verification uses the draft credentials, without saving or resetting them.
    with patch('app.acquisition.tasks.AcquisitionTask.start'):
        click(item('completionVerifyLogin'))
        assert settings._task.completion == ('newcompletion', 'newpassword')
        assert not completion.property('enabled')
        settings._login_failed('模拟验证失败')
        QTest.qWait(30)
    assert completion.property('text') == 'newcompletion'
    assert settings.accounts['completion']['username'] == 'saved-completion'
    enter(completion, 'editedcompletion')
    save = next(child for child in cards[0].findChildren(QObject) if child.property('text') == '保存')
    click(save)
    assert settings.accounts['completion']['username'] == 'editedcompletion'
    assert item('completionPassword').property('text') == ''
    assert homework.property('text') == 'newhomework', '保存另一平台不应覆盖未保存的账号'
    assert item('homeworkPassword').property('text') == 'otherpassword'
    output = Path('output/settings-input')
    output.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(output / 'wide.png'))

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
    # The sidebar and larger controls change the form's geometry. Bring the
    # actual combo into the viewport before sending wheel events over it.
    term_y = term.mapToScene(QPointF(0, 0)).y()
    scroll_y = scroll.mapToScene(QPointF(0, 0)).y()
    scroll.setProperty('contentY', max(0, scroll.property('contentY') + term_y - scroll_y - 50))
    QTest.qWait(50)
    before_combo_scroll = scroll.property('contentY')
    combo = QPoint(round(term.property('width') / 2), round(term.property('height') / 2))
    windowPoint = term.mapToScene(QPointF(combo)).toPoint()
    for _ in range(3):
        QGuiApplication.sendEvent(window, QWheelEvent(QPointF(windowPoint), QPointF(window.mapToGlobal(windowPoint)), QPoint(),
            QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False))
        QTest.qWait(30)
    assert scroll.property('contentY') > before_combo_scroll, '光标停在班期下拉框上时页面无法滚动'
    assert term.property('currentIndex') == 0, '滚轮不应改动画期下拉框的选中项'

    # 窄窗口改为上下排列，内容依旧可以滚动。
    window.resize(760, 700)
    QTest.qWait(200)
    cards = [item('completionAccountCard'), item('homeworkAccountCard')]
    assert abs(cards[0].property('x') - cards[1].property('x')) < 1, '窄窗口没有改为上下排列'
    assert cards[1].property('y') > cards[0].property('y'), '窄窗口账号卡片重叠'
    assert cards[0].property('width') > 600, '窄窗口账号卡片没有铺满'
    assert scroll.property('contentWidth') == cards[0].property('width') or cards[0].property('width') <= scroll.property('contentWidth') + 1

    # Narrow stacked cards still accept mouse focus and continuous keyboard input.
    for platform, username in (('completion', '13800000001'), ('homework', '13800000002')):
        control = item(platform + 'Username')
        target_y = scroll.property('contentY') + control.mapToScene(QPointF()).y() - scroll.mapToScene(QPointF()).y() - 100
        scroll.setProperty('contentY', min(max(0, target_y), scroll.property('contentHeight') - scroll.property('height')))
        QTest.qWait(50)
        enter(control, username)
    assert window.grabWindow().save(str(output / 'narrow.png'))

    assert not warnings, warnings
    engine.deleteLater()
    app.processEvents()
print('Settings module QML smoke OK')
