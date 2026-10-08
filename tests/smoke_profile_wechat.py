"""Real QML, synthetic rosters and a gated fake desktop driver."""
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from app.backend import Backend
from tests.profile_fixtures import insert_profile
from tests.test_profile_wechat import FakeDriver


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Microsoft YaHei', 10))
    output = Path('output/profile-wechat')
    output.mkdir(parents=True, exist_ok=True)

    def wait_until(condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert condition(), '等待异步验证超时'

    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'test.db')
        with b.db.connect() as conn:
            for ordinal, (sid, name, status, wechat) in enumerate([
                    ('P2026175001A', '示例甲', '在读', '否'),
                    ('P2026175002A', '示例乙', '', ''),
                    ('P2026175003A', '示例丙', '在读', '是'),
                    ('P2026175004A', '示例丁', '已退课', '否')], 1):
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-10-08'))
                insert_profile(conn, sid, name, ordinal, {'微信': wechat})
                conn.execute('UPDATE class_roster SET status=? WHERE student_id=?', (status, sid))
        b.refresh()
        profiles, verifier = b.profilesModule, b.profilesModule.wechatVerifier
        profiles.setColumnFilter('profile:微信', 'values', ['否'], '')
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
        QMetaObject.invokeMethod(window, 'switchModule', Q_ARG('QVariant', 1))
        QTest.qWait(160)
        button = window.findChild(QObject, 'verifyProfileWechat')
        assert button is not None and button.property('enabled')
        QMetaObject.invokeMethod(button, 'click')
        QTest.qWait(100)
        dialog = window.findChild(QObject, 'profileWechatDialog')
        assert dialog.property('visible') and verifier.total == 3
        assert not verifier.active, '打开预览不应操作企微'
        assert window.findChild(QObject, 'profileWechatTable').property('rows') == 3
        window.grabWindow().save(str(output / 'preview-light.png'))

        entered, release = threading.Event(), threading.Event()
        driver = FakeDriver({'示例甲': '示例甲/新生', '示例乙': None, '示例丙': '示例丙'})
        read = driver.read_remark

        def gated_read(name):
            entered.set()
            release.wait(5)
            return read(name)

        driver.read_remark = gated_read
        with patch.object(verifier, '_driver_factory', return_value=driver), patch.object(verifier._hotkey, 'start'), patch.object(verifier._hotkey, 'close'):
            QMetaObject.invokeMethod(window.findChild(QObject, 'profileWechatStart'), 'click')
            try:
                assert verifier.active and entered.wait(2)
                QTest.qWait(80)
                assert not window.findChild(QObject, 'profileWechatStart').property('enabled')
                assert not window.findChild(QObject, 'classSelector').property('enabled')
                QMetaObject.invokeMethod(window.findChild(QObject, 'profileWechatPause'), 'click')
                release.set()
                wait_until(lambda: verifier.isPaused)
                assert verifier.completed == 1
                assert window.findChild(QObject, 'profileWechatPause').property('text') == '继续验证'
                QMetaObject.invokeMethod(window.findChild(QObject, 'profileWechatPause'), 'click')
                wait_until(lambda: not verifier.active)
                assert driver.reads == ['示例甲', '示例乙', '示例丙']
                assert verifier.completed == 3 and verifier.updated == 1
                assert b.repo.get('P2026175001A')['profile:微信'] == '是'
                assert b.repo.get('P2026175002A')['profile:微信'] == ''
                assert b.repo.get('P2026175004A')['profile:微信'] == '否'
                assert profiles.visibleCount == 2 and profiles.staleCount == 1
                assert window.findChild(QObject, 'classSelector').property('enabled')
                window.grabWindow().save(str(output / 'result-light.png'))
                QMetaObject.invokeMethod(dialog, 'close')
                QMetaObject.invokeMethod(button, 'click')
                QTest.qWait(80)
                assert verifier.completed == 3, '重新打开应可查看已完成结果'
                b.settingsModule.setAppearanceMode('dark')
                QTest.qWait(160)
                window.grabWindow().save(str(output / 'result-dark.png'))
                window.resize(720, 700)
                QTest.qWait(180)
                assert dialog.property('width') <= 720
                for name in ('profileWechatStart', 'profileWechatPause', 'profileWechatStop'):
                    control = window.findChild(QObject, name)
                    if control.property('visible'):
                        assert control.property('width') > 0
                window.grabWindow().save(str(output / 'result-dark-narrow.png'))
                QMetaObject.invokeMethod(dialog, 'close')
                profiles.setAllClasses(True)
                QTest.qWait(80)
                assert not button.property('enabled')
                profiles.setAllClasses(False)
                # Closing while a contact is being checked stops safely after it finishes.
                entered.clear()
                release.clear()
                assert verifier.prepare() and verifier.start()
                assert entered.wait(2)
                assert not window.close()
                assert verifier.stopping
                release.set()
                wait_until(lambda: not verifier.active)
                assert verifier.completed == 1
                assert window.close()
            finally:
                release.set()
                verifier.shutdown()
        assert not [w for w in warnings if 'ProfileWechat' in w], warnings
        print('Profile WeChat preview/full scope, pause/resume, results, freeze, read-only, safe close and light/dark/narrow QML: OK')


if __name__ == '__main__':
    run()
