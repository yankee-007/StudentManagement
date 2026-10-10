"""Exercise real QML with synthetic students, credentials and AI responses."""
import json
import os
from pathlib import Path
import time
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.fonts import configure_font
from tests.test_business_logic import seeded
from tests.test_ai_campaign import AiIntegrationTests, fake_chat


def run():
    QQuickStyle.setStyle('Fusion')
    app = QApplication([])
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    output = Path(os.environ.get('AI_UI_CAPTURE_DIR', 'output/ai-campaign'))
    output.mkdir(parents=True, exist_ok=True)
    vault = {}
    def provider(config, key, messages):
        if messages[-1]['content'].startswith('只返回JSON'):
            return '{"ok":true}'
        return fake_chat(config, key, messages)
    with seeded(2) as backend, \
         patch('keyring.get_password', side_effect=lambda service, user: vault.get((service, user))), \
         patch('keyring.set_password', side_effect=lambda service, user, key: vault.update({(service, user):key})), \
         patch('app.ai_campaign.chat', side_effect=provider) as request:
        AiIntegrationTests().setup_campaign(backend)
        engine = QQmlApplicationEngine()
        warnings=[]
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.rootContext().setContextProperty('backend', backend)
        engine.rootContext().setContextProperty('studentModel', backend.studentModel)
        engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
        assert engine.rootObjects(), warnings
        window=engine.rootObjects()[0]; window.resize(1200,800); window.show(); QTest.qWait(100)
        def item(name):
            result=window.findChild(QObject,name)
            assert result is not None, name
            return result
        def click(name):
            control=item(name)
            point=control.mapToScene(QPointF(control.property('width')/2,control.property('height')/2))
            assert 0<point.x()<window.width() and 0<point.y()<window.height(), (name,point)
            QTest.mouseClick(window,Qt.LeftButton,pos=point.toPoint()); QTest.qWait(40)
        def wait():
            deadline=time.monotonic()+5
            while backend.aiCampaign.busy and time.monotonic()<deadline: QTest.qWait(10)
            assert not backend.aiCampaign.busy,backend.aiCampaign.notice
        window.switchModule(3); QTest.qWait(50)
        item('aiModel').setProperty('text','test')
        item('aiApiKey').setProperty('text','synthetic-secret')
        scroll=item('settingsScroll')
        card=item('aiSettingsCard')
        scroll.setProperty('contentY',card.property('y'))
        QTest.qWait(50)
        click('saveAiConfig')
        assert item('aiApiKey').property('text')==''
        assert 'synthetic-secret' not in backend.workflow.registry.get_setting('ai_campaign_config')
        click('testAiConnection'); wait()
        assert '连接测试通过' in backend.aiCampaign.notice,backend.aiCampaign.notice
        assert window.grabWindow().save(str(output/'ai-settings-light.png'))
        window.switchModule(0); QTest.qWait(50)
        item('campaignListDialog').open(); QTest.qWait(80)
        click('campaignAiMode')
        assert item('aiTemplateSelector').property('currentText')=='自动 · 当前第 2 节课'
        assert not item('createCampaignSelection').property('enabled')
        click('generateAiCampaign'); wait(); QTest.qWait(100)
        assert backend.aiCampaign.ready and backend.aiCampaign.failureCount==0,backend.aiCampaign.notice
        assert item('createCampaignSelection').property('enabled')
        assert window.grabWindow().save(str(output/'ai-dialog-light.png'))
        backend.settingsModule.setAppearanceMode('dark'); window.resize(720,480); QTest.qWait(100)
        results=item('aiCampaignResults')
        results.setProperty('contentY',0)
        QTest.qWait(60)
        assert results.property('contentHeight')>results.property('height')
        assert window.grabWindow().save(str(output/'ai-dialog-dark-720.png'))
        assert item('createCampaignSelection').property('width')>100
        button=item('createCampaignSelection')
        bottom=button.mapToScene(QPointF(0,button.property('height'))).y()
        assert bottom <= window.height(), ('create button clipped',bottom)
        # Actual create click writes an independent list, and never starts sending.
        click('createCampaignSelection')
        assert window.property('moduleIndex')==4
        assert len(backend.groupCenter.rows)==2 and not backend.groupCenter.active
        assert request.call_count==2
        window.resize(1200,800); backend.settingsModule.setAppearanceMode('light')
        window.switchModule(0); item('campaignListDialog').open(); QTest.qWait(80)
        click('campaignAiMode')
        with patch('app.ai_campaign.chat',return_value='{}'):
            click('generateAiCampaign'); wait()
        assert backend.aiCampaign.failureCount==2
        click('createCampaignSelection')
        assert backend.aiCampaign.listFailureCount==2
        QTest.qWait(50); assert item('groupRetryAiFailures').property('visible')
        assert window.grabWindow().save(str(output/'ai-failed-list-light.png'))
        click('groupRetryAiFailures'); wait()
        assert backend.aiCampaign.listFailureCount==0
        assert not backend.groupCenter.active
        # Settings remain accessible at the minimum size and in the dark theme.
        backend.settingsModule.setAppearanceMode('dark'); window.resize(720,480)
        window.switchModule(3); QTest.qWait(80)
        scroll.setProperty('contentY',card.property('y')); QTest.qWait(50)
        assert window.grabWindow().save(str(output/'ai-settings-dark-720.png'))
        bad=[w for w in warnings if any(s in w for s in ('AiCampaign','AiSettings','Binding loop','TypeError','ReferenceError'))]
        assert not bad,bad
        # Closing during an active request cancels safely and keeps the window alive.
        window.switchModule(0); item('campaignListDialog').open(); QTest.qWait(80)
        click('campaignAiMode')
        started=Event(); release=Event()
        def delayed(config,key,messages):
            started.set(); release.wait(3)
            return fake_chat(config,key,messages)
        with patch('app.ai_campaign.chat',side_effect=delayed):
            click('generateAiCampaign')
            assert started.wait(2)
            assert not window.close()
            assert window.isVisible() and backend.aiCampaign._worker.cancel.is_set()
            release.set(); wait()
        assert backend.aiCampaign.ready
        window.hide(); engine.deleteLater(); app.processEvents()
    print('AI campaign QML smoke OK (settings, JSON connection, generate, create, failed-list retry, safe close/cancel, light/dark, 720x480).')


if __name__=='__main__': run()
