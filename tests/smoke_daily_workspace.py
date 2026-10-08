"""Synthetic Qt Quick end-to-end editing, themes, layouts, list creation and guards."""
import os
from pathlib import Path
from PySide6.QtCore import QObject, QPointF, Qt, QUrl, QEvent, QCoreApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtGui import QFontDatabase, QInputMethodEvent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.fonts import configure_font
from tests.test_daily_workspace import DailyTests
from tests.test_latest_batch_refresh import sid
from tests.smoke_learning_overview import visual, click
from unittest.mock import patch


def run():
    QQuickStyle.setStyle('Fusion')
    app=QApplication([])
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists(): QFontDatabase.addApplicationFont(str(font))
    configure_font(app)
    case=DailyTests('test_review_due_and_cancel_reason');case.setUp()
    b=case.b; d=b.dailyWorkspace
    errors=[]
    engine=QQmlApplicationEngine()
    engine.warnings.connect(lambda messages: errors.extend(str(message.toString()) for message in messages))
    engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(Path('qml/Main.qml').resolve())))
    assert engine.rootObjects(),errors
    window=engine.rootObjects()[0];window.show();QTest.qWait(150)
    # Opening the daily page must not trap navigation to any other module.
    with patch.object(b.termsModule,'activate'),patch.object(b.liveAbsence,'activate'):
        for index in (8,0,8,1,8,2,8,3,8,4,8,5,8,6,8,7,8):
            click(window,visual(window.contentItem(),f'moduleButton{index}'))
            assert window.property('moduleIndex')==index,(index,d.summary)
    assert not d._drafts
    page=visual(window.contentItem(),'dailyWorkspacePage')
    assert page is not None and page.isVisible()
    d.selectTab(0);d.selectRow(0);QTest.qWait(40)
    assert d.selectedId==sid(2)
    due=visual(window.contentItem(),'dailyDue')
    # Search within this page; the shared campaign editor has the same control names.
    due=visual(page,'dailyDue');due.forceActiveFocus();due.setProperty('text','2099-12-31 20:00')
    note=visual(page,'dailyNote');note.forceActiveFocus()
    for character in 'commitment': QTest.keyClick(window,Qt.Key(ord(character.upper())))
    QTest.qWait(30)
    assert note.property('activeFocus') and note.property('text')=='commitment'
    preedit=QInputMethodEvent('补齐',[])
    app.sendEvent(window,preedit)
    assert note.property('inputMethodComposing')
    commit=QInputMethodEvent();commit.setCommitString('补齐')
    app.sendEvent(window,commit);QTest.qWait(20)
    assert not note.property('inputMethodComposing') and note.property('text')=='commitment补齐'
    assert d.hasDraft(d.detailsFor(sid(2))['key'])
    save=visual(page,'dailySaveCommitment')
    scroll=visual(page,'dailyDetailScroll');viewport=scroll.property('contentItem')
    point=save.mapToScene(QPointF(0,0));bottom=scroll.mapToScene(QPointF(0,scroll.height())).y()
    if point.y()+save.height()>bottom:
        viewport.setProperty('contentY',viewport.property('contentY')+point.y()+save.height()-bottom+8)
        QTest.qWait(40)
    click(window,save)
    assert d.detailsFor(sid(2))['task'].get('note')=='commitment补齐',d.summary
    # Flushing an edited commitment must preserve the entered contact prefix.
    visual(page,'dailyContactPrefix').setProperty('text','虚构前缀')
    note.setProperty('text','更新联系记录')
    viewport.setProperty('contentY',0);QTest.qWait(40)
    with patch('app.contact_opener.ContactOpenTask') as factory:
        click(window,visual(page,'dailyOpenContact'))
        assert factory.call_args.args[0]=='虚构前缀虚构学员2'
        assert d.detailsFor(sid(2))['task']['note']=='更新联系记录'
        assert b.repo.get_setting('campaign_contact_prefix')=='虚构前缀'
        b.contactOpener._finished()
    # Invalid text must survive a rejected close and row switch.
    due.setProperty('text','invalid');QTest.qWait(20)
    old=d.selectedId;d.selectRow(1)
    assert d.selectedId==old and due.property('text')=='invalid'
    assert not window.close()
    assert window.isVisible()
    # Incomplete input stays in the same editor while other modules remain usable.
    draft_key=visual(page,'dailyEditor').property('loadedKey')
    draft_token=visual(page,'dailyEditor').property('editorToken')
    with patch.object(b.termsModule,'activate'),patch.object(b.liveAbsence,'activate'):
        for index in (0,1,2,3,4,5,6,7,8):
            click(window,visual(window.contentItem(),f'moduleButton{index}'))
            assert window.property('moduleIndex')==index,(index,d.summary)
            assert due.property('text')=='invalid' and d.selectedId==old
            assert d.hasDraft(draft_key,draft_token)
    key=d.detailsFor(old)['key'];d.discardDraft(key)
    due.setProperty('text','2099-12-31 20:00')
    assert d.flushEditor()
    # Goal configuration uses the actual dialog and preserves existing values.
    click(window,visual(page,'dailyEditGoal'))
    dialog=window.findChild(QObject,'dailyGoalDialog');assert dialog.property('visible')
    target=visual(window.contentItem(),'dailyGoalCourse')
    assert target.property('text')=='90'
    target.setProperty('text','92')
    click(window,visual(window.contentItem(),'dailySaveGoal'))
    assert d.goal['course']==92 and not dialog.property('visible')
    # Independent page actions preserve the campaign cursor.
    cursor=b.workflow.editorKey
    d.checkAll(True)
    click(window,visual(page,'dailyCreateList'))
    dialog=window.findChild(QObject,'dailyListDialog');assert dialog.property('visible')
    click(window,visual(window.contentItem(),'dailyConfirmList'))
    assert window.property('moduleIndex')==4 and b.groupCenter.store.rows(b.groupCenter._id)
    assert all(row['state']=='待发送' for row in b.groupCenter.store.rows(b.groupCenter._id))
    assert b.workflow.editorKey==cursor
    window.setProperty('moduleIndex',8)
    output=Path(os.environ.get('DAILY_SCREENSHOT_DIR','output/daily-workspace'));output.mkdir(parents=True,exist_ok=True)
    floating=window.findChild(QObject,'campaignFloatingWindow')
    with patch.object(b.profileCompanion,'_active_wecom_title',return_value='虚构学员2'):
        floating.show();b.campaignCompanion._match_title('虚构学员2');QTest.qWait(40)
        floating.findChild(QObject,'floatingCampaignDetail').setProperty('followupExpanded',True);QTest.qWait(40)
        floatEditor=visual(floating.contentItem(),'campaignFollowupEditor')
        assert floatEditor.isVisible()
        floatNote=visual(floatEditor,'dailyNote')
        floatNote.setProperty('text','floating draft')
        note.setProperty('text','main draft')
        key=visual(page,'dailyEditor').property('loadedKey')
        token=visual(page,'dailyEditor').property('editorToken')
        assert not d.flushEditor()
        assert note.property('text')=='main draft' and d.hasDraft(key,token)
        d.discardDraft(key,token);d.reload(True)
        assert floating.grabWindow().save(str(output/'floating-followup.png'))
        floating.close()
    for theme in ('light','dark'):
        b.settingsModule.setAppearanceMode(theme)
        for width,height in ((1280,820),(1000,700),(720,480)):
            window.resize(width,height);QTest.qWait(80)
            visual(page,'dailyDetailScroll').property('contentItem').setProperty('contentY',0)
            assert window.grabWindow().save(str(output/f'{theme}-{width}.png'))
            assert page.width()<width
            table=visual(page,'dailyTable')
            assert table.height()>=100,(width,table.height())
            if width==720:
                page.setProperty('detailOpen',True);QTest.qWait(40)
                assert window.grabWindow().save(str(output/f'{theme}-detail-720.png'))
                page.setProperty('detailOpen',False)
    assert not [message for message in errors if any(name in message for name in ('DailyWorkspace.qml','FollowupEditor.qml'))],errors
    window.close();engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
    b._date_timer.stop();d._timer.stop()
    case.doCleanups()
    print('Daily workspace real QML smoke passed (themes, 3 sizes, edits, close guard, goals, independent lists).')


if __name__=='__main__':run()
