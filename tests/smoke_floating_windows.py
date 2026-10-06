"""Check independent floating windows and profile typing in a disposable QML UI."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QMetaObject, Q_ARG, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from tests.profile_fixtures import insert_profile


def visual(item, name):
    if item.objectName() == name:
        return item
    for child in item.childItems():
        found = visual(child, name)
        if found is not None:
            return found
    return None


def field(item, label):
    if item.property('caption') == label:
        return item
    for child in item.childItems():
        found = field(child, label)
        if found is not None:
            return found
    return None


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        backend = Backend(Path(folder) / 'test.db')
        with backend.db.connect() as conn:
            for sid, name in [('001', '测试甲'), ('002', '测试乙')]:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-09-29'))
                insert_profile(conn, sid, name, int(sid))
        backend.workflow.createBatch()
        backend.profilesModule.refresh()
        backend.profileCompanion._active_wecom_title = lambda: '测试甲'
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', backend)
        engine.rootContext().setContextProperty('studentModel', backend.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        main = engine.rootObjects()[0]
        profile = main.findChild(QObject, 'profileFloatingWindow')
        campaign = main.findChild(QObject, 'campaignFloatingWindow')
        assert profile.width() == 240 and campaign.width() == 246
        assert not hasattr(backend.profileCompanion, 'setLocked')
        assert not hasattr(backend.campaignCompanion, 'setLocked')
        assert profile.transientParent() is None and campaign.transientParent() is None
        for floating in (profile, campaign):
            floating.setProperty('pinned', False)
            floating.setProperty('pinned', True)
            assert floating.transientParent() is None
        main.resize(960, 640)
        main.show()
        # At a narrow width the detail pane is opened explicitly.
        main.setProperty('campaignDetailOpen', True)
        profile.show()
        campaign.show()
        app.processEvents()
        backend.profileCompanion._timer.stop()
        assert visual(campaign.contentItem(), 'openCampaignContact').isVisible() is False
        assert visual(main.contentItem(), 'openCampaignContact').isVisible()
        main.showMinimized()
        app.processEvents()
        assert main.windowState() & Qt.WindowMinimized
        assert not profile.windowState() & Qt.WindowMinimized
        assert not campaign.windowState() & Qt.WindowMinimized
        assert profile.isVisible() and campaign.isVisible()
        campaign.close()
        profile.raise_()
        profile.requestActivate()
        QTest.qWait(50)
        assert main.windowState() & Qt.WindowMinimized
        owner = field(profile.contentItem(), '所在地区')
        editor = owner.findChild(QObject, 'profileInput')
        editor.forceActiveFocus()
        editor.setProperty('text', '上')
        editor.setProperty('text', '上海')
        assert backend.repo.get('001')['profile_fields']['所在地区'] == ''
        QTest.qWait(240)
        assert backend.repo.get('001')['profile_fields']['所在地区'] == '上海'
        choice_owner = field(profile.contentItem(), '微信')
        choice = choice_owner.findChild(QObject, 'profileChoice')
        choice.setProperty('currentIndex', 1)
        assert QMetaObject.invokeMethod(choice, 'activated', Q_ARG(int, 1))
        assert choice.property('displayText') == '是'
        assert backend.repo.get('001')['profile_fields']['微信'] == ''
        editor.setProperty('text', '北京')
        profile.close()
        assert backend.repo.get('001')['profile_fields']['所在地区'] == '北京'
        assert backend.repo.get('001')['profile_fields']['微信'] == '是'
        assert not warnings, warnings
        main.close()
        backend._date_timer.stop()
        print('Floating windows OK: compact layout, no lock, independent visibility, deferred choice and text saves')


if __name__ == '__main__':
    run()
