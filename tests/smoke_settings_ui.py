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
    path = Path(folder) / 'test.db'
    backend = Backend(path)
    settings = backend.settingsModule
    assert settings.saveAccount('completion', 'saved-completion', 'saved-password')
    assert settings.saveAccount('homework', 'saved-homework', 'saved-password')
    terms = [{'termId': 551, 'termName': '测试完课班一', 'termNo': 'P2026169'},
             {'termId': 564, 'termName': '测试完课班二', 'termNo': 'P2026175'},
             {'termId': 578, 'termName': '测试完课班三', 'termNo': 'P2026180'}]
    backend.termsModule._accept('terms', terms)
    homework_classes = [{'id': 23, 'name': '测试作业班一', 'course_ids': [2]},
                        {'id': 31, 'name': '测试作业班二', 'course_ids': [5, 9]}]
    settings._classes_loaded(homework_classes)
    assert settings.saveBinding('551', 23), settings.notice
    assert settings.saveBinding('564', 31, 9), settings.notice
    # 从同一临时库重建 Backend，实际覆盖启动恢复。
    backend = Backend(path)
    settings = backend.settingsModule

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
        if found is None:
            def visual(parent):
                if parent.objectName() == name:
                    return parent
                for child in parent.childItems():
                    match = visual(child)
                    if match is not None:
                        return match
            found = visual(window.contentItem())
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

    scroll = item('settingsScroll')

    def click(control):
        # 外观卡片与后续设置可以增长：先把目标滚入视口再做真实点击。
        top = scroll.mapToScene(QPointF()).y()
        center = control.mapToScene(QPointF(0, control.property('height') / 2)).y()
        if center < top + 20 or center > top + scroll.property('height') - 20:
            target = scroll.property('contentY') + center - top - scroll.property('height') / 2
            scroll.setProperty('contentY', min(max(0, target), max(0, scroll.property('contentHeight') - scroll.property('height'))))
            QTest.qWait(40)
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

    assert item('bindingRows').property('count') == len(terms), '绑定行数应跟随完课平台班期数量'
    assert window.findChild(QObject, 'settingTermBox') is None, '完课班期应固定展示'
    course = item('settingCourseBox_551')
    assert not course.isVisible(), '单课程班级不应显示课程下拉框'
    assert item('settingClassBox_551').property('currentIndex') == 1, '重启后没有带出已确认的作业班级'
    assert item('settingClassBox_578').property('currentIndex') == 0, '未绑定班期必须留空，不能默认选作业班级'
    assert item('settingCourseBox_564').property('currentIndex') == 1, '多课程绑定没有恢复已保存课程'
    binding = settings.bindingFor('551')
    assert binding['class_id'] == 23 and binding['course_id'] == 2, binding

    # 重新打开设置页 / 刷新状态后，切换班期仍能带出已确认的对应关系。
    window.switchModule(0)
    QTest.qWait(50)
    window.switchModule(3)
    QTest.qWait(150)
    assert item('settingClassBox_551').property('currentIndex') == 1, '重新进入设置页后没有带出对应关系'
    settings.refresh()
    QTest.qWait(100)
    assert item('settingClassBox_551').property('currentIndex') == 1, '刷新状态后对应关系被清空'

    def choose(control, index):
        click(control)
        QTest.keyClick(window, Qt.Key_Home)
        for _ in range(index):
            QTest.keyClick(window, Qt.Key_Down)
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(50)
        assert control.property('currentIndex') == index, (control.objectName(), control.property('currentIndex'), index)

    # 使用真实下拉交互，选择后无需确认立即保存；清空仅作用于该行。
    choose(item('settingClassBox_551'), 2)
    assert settings.bindingFor('551')['class_id'] == 31
    assert settings.bindingFor('551')['course_id'] == 5
    choose(item('settingCourseBox_551'), 1)
    assert settings.bindingFor('551')['course_id'] == 9
    choose(item('settingClassBox_564'), 0)
    assert not settings.bindingFor('564')
    assert settings.bindingFor('551')['course_id'] == 9
    choose(item('settingClassBox_578'), 1)
    assert settings.bindingFor('578')['class_id'] == 23
    choose(item('settingClassBox_578'), 0)
    assert not settings.bindingFor('578')

    # 不允许无课程班级覆盖已保存的绑定；错误贴在所属班期下。
    settings._classes_loaded(homework_classes + [{'id': 40, 'name': '测试无课程班', 'course_ids': []}])
    control = item('settingClassBox_551')
    click(control)
    QTest.keyClick(window, Qt.Key_End)
    QTest.keyClick(window, Qt.Key_Return)
    QTest.qWait(50)
    assert settings.bindingFor('551')['course_id'] == 9
    assert control.property('currentIndex') == 2, '保存失败必须恢复原绑定'
    assert '课程' in item('bindingError_551').property('text')
    choose(control, 2)
    assert settings.bindingFor('551')['course_id'] == 9, '重复选择同一班级不应重置已保存课程'

    # 目录暂缺仍显示旧绑定，并且可以在没有目录时清空。
    settings._classes_loaded([])
    QTest.qWait(50)
    assert '已保存，目录暂缺' in item('settingClassBox_551').property('currentText')
    assert settings.bindingFor('551')['course_id'] == 9
    choose(item('settingClassBox_551'), 0)
    assert not settings.bindingFor('551'), '目录缺失时也应允许清空旧绑定'
    settings._classes_loaded(homework_classes)
    QTest.qWait(50)
    choose(item('settingClassBox_551'), 2)
    choose(item('settingCourseBox_551'), 1)

    # 平台列表刷新时增删行，历史绑定保留在数据库，不增加额外界面行。
    backend.termsModule._accept('terms', terms[1:])
    QTest.qWait(50)
    assert item('bindingRows').property('count') == 2
    assert settings.bindingFor('551')['course_id'] == 9
    backend.termsModule._accept('terms', terms)
    QTest.qWait(50)
    assert item('bindingRows').property('count') == 3
    assert item('settingCourseBox_551').property('currentIndex') == 1

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

    # 光标停在作业班级下拉框上时滚轮滚动页面，不能改选项。
    term = item('settingClassBox_551')
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
    assert term.property('currentIndex') == 2, '滚轮不应改动作业班级下拉框的选中项'

    window.resize(1280, 900)
    QTest.qWait(100)
    click(item('settingClassBox_551'))
    QTest.keyClick(window, Qt.Key_Escape)
    assert window.grabWindow().save(str(output / 'bindings-wide.png'))
    settings.setAppearanceMode('dark')
    QTest.qWait(80)
    assert window.grabWindow().save(str(output / 'bindings-dark.png'))
    settings.setAppearanceMode('light')

    # 窄窗口改为上下排列，内容依旧可以滚动。
    window.resize(760, 700)
    QTest.qWait(200)
    cards = [item('completionAccountCard'), item('homeworkAccountCard')]
    assert abs(cards[0].property('x') - cards[1].property('x')) < 1, '窄窗口没有改为上下排列'
    assert cards[1].property('y') > cards[0].property('y'), '窄窗口账号卡片重叠'
    assert abs(cards[0].property('width') - scroll.property('contentWidth')) < 1, '窄窗口账号卡片没有铺满'
    assert scroll.property('contentWidth') == cards[0].property('width') or cards[0].property('width') <= scroll.property('contentWidth') + 1

    # Narrow stacked cards still accept mouse focus and continuous keyboard input.
    for platform, username in (('completion', '13800000001'), ('homework', '13800000002')):
        control = item(platform + 'Username')
        target_y = scroll.property('contentY') + control.mapToScene(QPointF()).y() - scroll.mapToScene(QPointF()).y() - 100
        scroll.setProperty('contentY', min(max(0, target_y), scroll.property('contentHeight') - scroll.property('height')))
        QTest.qWait(50)
        enter(control, username)
    assert window.grabWindow().save(str(output / 'narrow.png'))
    click(item('settingClassBox_551'))
    QTest.keyClick(window, Qt.Key_Escape)
    assert not item('bindingRow_551').property('sideBySide'), '窄窗口绑定行必须纵向排列'
    assert window.grabWindow().save(str(output / 'bindings-narrow.png'))

    # 新建引擎/后端模拟再次启动，界面也应恢复修改与留空。
    assert not warnings, warnings
    window.close()
    engine.deleteLater()
    app.processEvents()
    backend = Backend(path)
    settings = backend.settingsModule
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.rootContext().setContextProperty('backend', backend)
    engine.rootContext().setContextProperty('studentModel', backend.studentModel)
    engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    window.show()
    window.switchModule(3)
    QTest.qWait(100)
    assert item('bindingRows').property('count') == 3
    assert item('settingClassBox_551').property('currentIndex') == 2
    assert item('settingCourseBox_551').property('currentIndex') == 1
    assert item('settingClassBox_564').property('currentIndex') == 0
    assert item('settingClassBox_578').property('currentIndex') == 0

    assert not warnings, warnings
    engine.deleteLater()
    app.processEvents()
print('Settings module QML smoke OK')
