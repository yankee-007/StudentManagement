"""Real QML interaction with temporary classes and simulated chat captions."""
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.backend import Backend
from app.database import Database
from app.repository import StudentRepository
from app.fonts import configure_font
from tests.profile_fixtures import insert_profile


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    configure_font(app)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'first.db')
        other = Database(Path(folder) / 'second.db')
        b.workflow._classes.append(dict(name='第二班', path=str(other.path)))
        for db, prefix in ((b.db, 'py101'), (other, 'py102')):
            with db.connect() as conn:
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','示例学员','2026-10-07')")
                insert_profile(conn, '001', '示例学员', 1)
            StudentRepository(db).set_setting('profile_remark_prefix', prefix)
        c = b.profileCompanion
        caption = ['py102 示例学员']
        c._active_wecom_title = lambda: caption[0]
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', b)
        engine.load(QUrl.fromLocalFile(str(Path('qml/FloatingProfile.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.show()
        QTest.qWait(100)
        assert c.displayName == 'py102 示例学员'
        selector = window.findChild(QObject, 'profileCompanionClassSelector')
        assert selector is not None
        assert selector.property('currentIndex') == 0
        # Keyboard selection exercises onActivated and the real QML binding.
        selector.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Down)
        QTest.qWait(50)
        assert c.classIndex == 1
        assert b.workflow.class_index == 0
        QTest.keyClick(window, Qt.Key_Down)
        QTest.qWait(50)
        assert c.classIndex == 2
        assert c.student['_db_path'] == str(other.path)
        caption[0] = '示例学员'
        c.selectClass(0)
        QTest.qWait(50)
        assert not c.student
        assert selector.property('currentIndex') == 0
        c.selectClass(2)
        QTest.qWait(50)
        references = []
        def field(item):
            references.append(item)
            if item.property('caption') == '所在地区':
                return item
            for child in item.childItems():
                found = field(child)
                if found is not None:
                    return found
            return None
        area = field(window.contentItem()).findChild(QObject, 'profileInput')
        area.forceActiveFocus()
        area.setProperty('text', 'Shanghai')
        selector.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Up)
        QTest.qWait(50)
        assert StudentRepository(other).get('001')['profile_fields']['所在地区'] == 'Shanghai'
        assert b.repo.get('001')['profile_fields']['所在地区'] == ''
        c.selectClass(2)
        for width, height in ((240, 490), (220, 280)):
            window.resize(width, height)
            QTest.qWait(100)
            point = selector.mapToScene(QPointF(0, 0))
            assert point.x() >= 0 and point.y() >= 0
            assert point.x() + selector.width() <= window.width()
            output = Path('output/profile-companion')
            output.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(output / f'{width}x{height}.png'))
        assert not warnings, warnings
        window.close()
        c.close()
        engine.deleteLater()
        app.processEvents()
    print('Profile companion QML: PASS (keyboard class switching, 240/220px layout)')


if __name__ == '__main__':
    run()
