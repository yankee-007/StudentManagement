"""Offscreen GUI smoke check for the live-room absence module.

No platform login and no enterprise-WeChat window: the fetch result is injected through the
same success path a finished AcquisitionTask uses, and the list is created in a temp group
database without sending anything.
"""
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, QPoint, Qt, QUrl, Q_ARG
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.database import Database
from app.fonts import configure_font
from app.profile_storage import set_exemption
from tests.profile_fixtures import insert_profile

LESSONS = [dict(resource_id='pre', label='【9月30日19：30课前准备】VIP专属预热课'),
           dict(resource_id='L01', label='01【Python核心语法精讲】_09HHQC14'),
           dict(resource_id='L02', label='02【运算符与数据处理】_09HHQC14')]


def click(window, item):
    """Real mouse click: setting `checked` from Python never emits toggled()."""
    x = y = 0.0
    node = item
    while node is not None:
        x += float(node.property('x') or 0)
        y += float(node.property('y') or 0)
        node = node.property('parent')
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                     QPoint(int(x + float(item.property('width')) / 2),
                            int(y + float(item.property('height')) / 2)))
    QTest.qWait(120)


def student_row(n, name, seconds):
    return dict(student_id=f'P2026175{n:03d}A', name=name, live_seconds=seconds,
                status='在读', student_type='新生')


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    # The offscreen platform may not enumerate Windows' installed CJK fonts.
    if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'test.db')
        entry = b.workflow._classes[b.workflow.class_index]
        entry.update(term_id='564', term_no='P2026175', name='编程175期')
        people = [('P2026175001A', '张三', None, '是'), ('P2026175002A', '李四', 0, '是'),
                  ('P2026175003A', '王五', 137, '是'), ('P2026175004A', '赵六', None, '是'),
                  ('P2026175005A', '周七', None, '否')]
        with b.db.connect() as conn:
            for i, (sid, name, _, wechat) in enumerate(people, 1):
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-09-30'))
                insert_profile(conn, sid, name, i, {'微信': wechat, '所在地区': '杭州'})
        set_exemption(b.db, 'P2026175004A', (date.today() + timedelta(days=1)).isoformat())
        b.refresh()
        module = b.liveAbsence
        module._store.save_lessons('564', LESSONS, '')
        module.reload()
        assert module.lessons == LESSONS, module.lessons
        module.selectLesson(1)
        assert module.lessonLabel.startswith('01'), module.lessonLabel
        # Same success path AcquisitionTask drives; no network.
        module._request = dict(term_id='564', resource_id='L01')
        module._busy = True
        module._succeeded([student_row(i, name, seconds) for i, (_, name, seconds, _) in enumerate(people, 1)])
        assert (module.apiCount, module.readyCount, module.eligibleCount) == (5, 5, 3), module.summary
        assert (module.absentCount, module.enteredCount, module.zeroCount) == (1, 2, 1), module.summary
        assert module.recipientKeys == ['P2026175001A'], module.recipientKeys
        assert '1 人画像微信不是「是」' in module.issues and '1 人在免催中' in module.issues, module.issues

        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', b)
        engine.rootContext().setContextProperty('studentModel', b.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 820)
        window.show()
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 6))
        QTest.qWait(250)
        page = window.findChild(QObject, 'liveAbsencePage')
        assert page is not None and page.property('visible'), '缺少未进直播间页面'
        assert window.findChild(QObject, 'classSelector').property('visible') is True
        lesson_box = window.findChild(QObject, 'liveAbsenceLessonBox')
        assert lesson_box.property('currentIndex') == 1, lesson_box.property('currentIndex')
        table = window.findChild(QObject, 'liveAbsenceTable')
        assert table is not None and table.property('rows') == 1, table.property('rows')
        assert window.findChild(QObject, 'liveAbsenceClass').property('text') == '编程175期'
        assert '未进入 1' in window.findChild(QObject, 'liveAbsenceSummary').property('text')
        assert '可加入新名单 1 人' in window.findChild(QObject, 'liveAbsenceListable').property('text')
        assert window.findChild(QObject, 'liveAbsenceFetch').property('enabled') is True
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-live-absence-preview.png'))

        # 0 秒默认算已进入；勾选后立刻进入未进入名单。
        zero_box = window.findChild(QObject, 'liveAbsenceIncludeZero')
        assert zero_box.property('checked') is False
        click(window, zero_box)
        assert zero_box.property('checked') is True and module.includeZero is True
        assert table.property('rows') == 2, table.property('rows')
        assert '可加入新名单 2 人' in window.findChild(QObject, 'liveAbsenceListable').property('text')
        show_box = window.findChild(QObject, 'liveAbsenceShowAll')
        click(window, show_box)
        assert show_box.property('checked') is True and module.showAll is True
        assert table.property('rows') == 3, table.property('rows')
        click(window, show_box)
        click(window, zero_box)
        assert table.property('rows') == 1, table.property('rows')
        assert module.includeZero is False and module.showAll is False

        # Creating the list must go through the real dialog and really create it.
        dialog = window.findChild(QObject, 'liveAbsenceCreateDialog')
        QMetaObject.invokeMethod(dialog, 'open')
        QTest.qWait(150)
        assert dialog.property('visible') and not b.groupCenter.active, '打开对话框不得启动发送'
        assert dialog.property('recordKeys').toVariant() == ['P2026175001A'], dialog.property('recordKeys')
        title = window.findChild(QObject, 'liveAbsenceListTitle')
        assert title.property('text') == '编程175期 · 本节未进直播间', title.property('text')
        QMetaObject.invokeMethod(window.findChild(QObject, 'liveAbsenceConfirmCreate'), 'clicked')
        QTest.qWait(250)
        lists = b.groupCenter.store.lists()
        assert len(lists) == 1 and lists[0]['count'] == 1, lists
        rows = b.groupCenter.store.rows(lists[0]['id'])
        assert rows[0]['name'] == '张三', rows
        assert '张三同学，01【Python核心语法精讲】_09HHQC14已经开始了' in rows[0]['content'], rows[0]['content']
        assert module.remindedCount == 1 and module.recipientCount == 0, module.summary
        assert window.property('moduleIndex') == 4, '创建后应跳到群发中心'
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-live-absence-created.png'))

        # Back on this page the reminded student stays visible and marked.
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 6))
        QTest.qWait(200)
        assert table.property('rows') == 1, table.property('rows')
        assert '已提醒' in module.tableModel.rows[0]['remind_state'], module.tableModel.rows[0]
        assert window.findChild(QObject, 'liveAbsenceCreateList').property('enabled') is False
        assert window.findChild(QObject, 'liveAbsenceClearReminders').property('enabled') is True
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-live-absence-reminded.png'))

        clear_dialog = window.findChild(QObject, 'liveAbsenceClearDialog')
        QMetaObject.invokeMethod(clear_dialog, 'open')
        QTest.qWait(120)
        assert clear_dialog.property('visible')
        QMetaObject.invokeMethod(clear_dialog, 'accepted')
        QTest.qWait(150)
        assert module.remindedCount == 0 and module.recipientCount == 1, module.summary

        # Switching class must re-read this module instead of keeping the old term's rows.
        other = Database(Path(folder) / 'class_other.db')
        with other.connect() as conn:
            conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', ('P2026169001A', '别班学员', '2026-09-30'))
            insert_profile(conn, 'P2026169001A', '别班学员', 1, {'微信': '是'})
        b.workflow._classes.append({'name': '编程169期', 'path': str(other.path), 'term_id': '551', 'term_no': 'P2026169'})
        b.workflow.changed.emit()
        QTest.qWait(60)
        b.workflow.selectClass(1)
        QTest.qWait(250)
        assert str(b.db.path) == str(other.path), b.db.path
        assert window.findChild(QObject, 'liveAbsenceClass').property('text') == '编程169期'
        assert not module.hasResult and table.property('rows') == 0, module.summary
        assert module.lessons == [], '另一个班期没有课程缓存时不得沿用上一班的节次'
        window.grabWindow().save(str(Path(tempfile.gettempdir()) / 'student-live-absence-class-switch.png'))

        window.close()
        app.processEvents()
        assert not warnings, warnings
        print('未进直播间页面、0 秒口径、每节一次提醒、生成名单与切班重读：OK')


if __name__ == '__main__':
    run()
