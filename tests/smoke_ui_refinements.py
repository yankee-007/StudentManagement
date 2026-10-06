"""Real pointer/keyboard checks for shared selectors and contact option popups.

Disposable databases and a mocked contact worker: never logs in or drives WeCom.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backend import Backend
from app.fonts import configure_font
from app.roster_sync import sync_roster


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output = Path('output/ui-refresh')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        b = Backend(Path(folder) / 'test.db')
        term = dict(termId=551, termNo='P2026169', termName='界面测试班')
        row = dict(student_id='P2026169001A', name='示例学员', status='在读', student_type='新生', nickname='', source='接口学员')
        sync_roster(b.db, term, [row])
        b.repo.update_profile_field(row['student_id'], '微信', '是')
        b.repo.set_setting('snapshot', json.dumps([dict(student_id=row['student_id'], flags={'c1':'T', 'z1':'F'})]))
        b.workflow.createBatch()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', b)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1280, 800)
        window.show()
        QTest.qWait(100)

        def find(name):
            detail = window.findChild(QObject, 'mainCampaignDetail')
            node = detail.findChild(QObject, name) if detail is not None else None
            if node is None:
                node = window.findChild(QObject, name)
            def visual(parent):
                for child in parent.childItems():
                    if child.objectName() == name:
                        return child
                    found = visual(child)
                    if found is not None:
                        return found
                return None
            if node is None:
                node = visual(window.contentItem())
            assert node is not None, name
            return node

        def click(name):
            item = find(name)
            assert item.isVisible() and item.isEnabled(), (name, item.isVisible(), item.isEnabled(), window.property('moduleIndex'), window.property('campaignDetailOpen'), b.workflow.canEdit, b.contactOpener.active)
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name, point)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(80)

        # Group messaging is last in the entire navigation, including settings.
        assert find('moduleButton5').mapToScene(QPointF()).y() < find('moduleButton4').mapToScene(QPointF()).y()
        assert find('moduleButton3').mapToScene(QPointF()).y() < find('moduleButton4').mapToScene(QPointF()).y()
        window.switchModule(3)
        QTest.qWait(80)
        scroll = find('settingsScroll')
        card = find('contactDefaultsCard')
        scroll.setProperty('contentY', min(card.y(), scroll.property('contentHeight') - scroll.height()))
        QTest.qWait(100)
        click('defaultContactPrefix')
        for char in 'py169':
            QTest.keyClick(window, Qt.Key(ord(char.upper())))
        click('saveDefaultContactPrefix')
        assert b.contactOpener.defaultPrefix == 'py169'

        window.switchModule(1)
        QTest.qWait(100)
        profile_search_width = find('profileSearchInput').width()
        click('profileContactOptions')
        popup = find('profileContactOptionsPopup')
        assert popup.property('visible')
        assert find('profileContactPrefix').property('text') == 'py169'
        click('profileContactPrefix')
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in 'py175':
            QTest.keyClick(window, Qt.Key(ord(char.upper())))
        b.repo.update_profile_field(row['student_id'], '所在地区', '示例地区')
        b.profilesModule.refresh()
        QTest.qWait(80)
        assert find('profileContactPrefix').property('text') == 'py175', 'same-student autosave/refresh must preserve pending prefix'
        click('profileUseDefaultPrefix')
        # Keep the popup open while making multiple choices.
        click('verifyProfileContact')
        assert not b.contactOpener.verifyContact
        assert not find('keepProfileContactFloat').isEnabled()
        click('profileUseContactPrefix')
        assert not find('profileContactPrefix').isEnabled()
        assert popup.property('visible')
        window.grabWindow().save(str(output / 'profile-contact-options-1280.png'))
        QTest.keyClick(window, Qt.Key_Escape)
        assert not popup.property('visible')
        with patch('app.contact_opener.ContactOpenTask') as task:
            click('openProfileContact')
            assert task.call_args.args[0] == '示例学员'
            assert not task.call_args.kwargs['verify_contact']
            b.contactOpener._finished()
        click('profileContactOptions')
        click('profileUseDefaultPrefix')
        assert find('profileContactPrefix').property('text') == 'py169'
        assert find('profileUseContactPrefix').property('checked')
        click('verifyProfileContact')
        click('keepProfileContactFloat')
        QTest.keyClick(window, Qt.Key_Escape)
        with patch('app.contact_opener.ContactOpenTask') as task:
            click('openProfileContact')
            assert task.call_args.args[0] == 'py169示例学员'
            assert task.call_args.kwargs['verify_contact'] and not task.call_args.kwargs['keep_float']
            b.contactOpener._finished()

        window.switchModule(0)
        QTest.qWait(100)
        assert abs(find('campaignSearchInput').width() - profile_search_width) < 1
        click('campaignContactOptions')
        assert find('campaignContactPrefix').property('text') == 'py169'
        assert find('verifyCampaignContact').property('checked')
        assert not find('keepCampaignContactFloat').property('checked')
        QTest.keyClick(window, Qt.Key_Escape)
        with patch('app.contact_opener.ContactOpenTask') as task:
            click('openCampaignContact')
            assert task.call_args.args[0] == 'py169示例学员'
            assert task.call_args.kwargs['verify_contact'] and not task.call_args.kwargs['keep_float']
            b.contactOpener._finished()

        for module, kind, toggle in ((0, 'campaign', 'campaignDetailToggle'), (1, 'profile', 'profileDetailToggle')):
            window.resize(720, 480)
            QTest.qWait(100)
            window.switchModule(module)
            QTest.qWait(100)
            opened = window.property('campaignDetailOpen') if module == 0 else find('profileModule').property('cardExpanded')
            if not opened:
                click(toggle)
            name = find(kind + 'ContactName')
            button = find('open' + kind.capitalize() + 'Contact')
            assert abs(name.mapToScene(QPointF()).y() - button.mapToScene(QPointF()).y()) < 10
            assert name.mapToScene(QPointF()).x() + name.width() <= button.mapToScene(QPointF()).x()
            click(kind + 'ContactOptions')
            popup = find(kind + 'ContactOptionsPopup')
            panel = popup.property('contentItem')
            point = panel.mapToScene(QPointF())
            window.grabWindow().save(str(output / (kind + '-contact-options-720.png')))
            assert point.x() >= 0 and point.y() >= 0
            assert point.x() + panel.width() <= window.width() + 1
            assert point.y() + panel.height() <= window.height() + 1, (kind, point, panel.height())
            QTest.keyClick(window, Qt.Key_Escape)
        assert not warnings, warnings
        window.close()
        print('UI refinements OK: default saved in settings, multi-select popup, original mocked contact actions, aligned search/name buttons, narrow popups')


if __name__ == '__main__':
    run()
