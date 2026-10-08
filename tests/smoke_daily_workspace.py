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
from datetime import datetime, timedelta


def reveal(window, item, scroll):
    viewport=scroll.property('contentItem')
    point=item.mapToScene(QPointF(item.width()/2,item.height()/2))
    top=scroll.mapToScene(QPointF(0,0)).y()
    viewport.setProperty('contentY',max(0,viewport.property('contentY')+point.y()-top-scroll.height()/2))
    QTest.qWait(40)


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
    QTest.qWait(600)
    assert not d.detailsFor(sid(2))['task'], 'A new commitment requires confirmation'
    save=visual(page,'dailySaveCommitment')
    scroll=visual(page,'dailyDetailScroll');viewport=scroll.property('contentItem')
    click(window,save)
    assert d.detailsFor(sid(2))['task'].get('note')=='commitment补齐',d.summary
    # Flushing an edited commitment must preserve the entered contact prefix.
    click(window,visual(page,'dailyContactOptions'))
    options=window.findChild(QObject,'dailyContactOptionsPopup');assert options.property('visible')
    visual(window.contentItem(),'dailyContactPrefix').setProperty('text','虚构前缀')
    options.close()
    note.setProperty('text','更新联系记录')
    viewport.setProperty('contentY',0);QTest.qWait(40)
    with patch('app.contact_opener.ContactOpenTask') as factory:
        click(window,visual(page,'dailyOpenContact'))
        assert factory.call_args.args[0]=='虚构前缀虚构学员2'
        assert d.detailsFor(sid(2))['task']['note']=='更新联系记录'
        assert b.repo.get_setting('campaign_contact_prefix')=='虚构前缀'
        b.contactOpener._result('已打开联系人，可记录沟通结果')
        b.contactOpener._finished()
    # Existing commitments merge continuous edits, preserving IME composition.
    previous_key=d.detailsFor(sid(2))['key']
    before=d.detailsFor(sid(2))['task']['revision']
    note.setProperty('text','连续修改1');QTest.qWait(100)
    note.setProperty('text','连续修改后的最终记录');QTest.qWait(600)
    assert d.detailsFor(sid(2))['task']['note']=='连续修改后的最终记录'
    assert d.detailsFor(sid(2))['task']['revision']==before+1
    assert visual(page,'dailySaveState').property('text')=='已自动保存'
    note.forceActiveFocus()
    app.sendEvent(window,QInputMethodEvent('中文',[]));QTest.qWait(600)
    assert note.property('inputMethodComposing')
    assert d.detailsFor(sid(2))['task']['revision']==before+1
    commit=QInputMethodEvent();commit.setCommitString('中文')
    app.sendEvent(window,commit);QTest.qWait(600)
    assert d.detailsFor(sid(2))['task']['note']==note.property('text')
    # A delayed callback from an earlier revision cannot clear a fresh draft.
    editor=visual(page,'dailyEditor');current_key=editor.property('loadedKey');token=editor.property('editorToken')
    note.setProperty('text','新版本草稿')
    d.saved.emit(previous_key,True,token);d.saved.emit(previous_key,False,token)
    assert editor.property('dirty') and not editor.property('saveFailed') and d.hasDraft(current_key,token)
    QTest.qWait(600);assert d.detailsFor(sid(2))['task']['note']=='新版本草稿'
    # Autosave keeps independent contact settings, disclosure and stable item focus.
    contact_options=visual(page,'dailyContactOptions');contact_options.setProperty('prefixValue','暂用前缀')
    history_toggle=visual(page,'dailyHistoryToggle');history_toggle.setProperty('checked',True)
    selected_item=visual(page,'dailyItem_z2');selected_item.forceActiveFocus()
    note.setProperty('text','保存时保留卡片状态');QTest.qWait(600)
    assert contact_options.property('prefixValue')=='暂用前缀' and history_toggle.property('checked')
    assert visual(page,'dailyItem_z2') is selected_item and selected_item.property('activeFocus')
    history_toggle.setProperty('checked',False);contact_options.setProperty('prefixValue','虚构前缀')
    # Shortcut menu appends the same class-specific choices as the workbench.
    before=d.detailsFor(sid(2))['task']['revision']
    note.setProperty('text','快捷填写')
    reveal(window,note,scroll);click(window,note)
    menu=window.findChild(QObject,'dailyShortcutMenu');assert menu.property('visible')
    QTest.qWait(650)
    assert menu.property('visible') and d.detailsFor(sid(2))['task']['revision']==before
    value=note.property('text')+'；'+b.workflow.feedbackShortcuts[0]
    click(window,visual(window.contentItem(),'dailyShortcutOption0'));QTest.qWait(600)
    assert note.property('text')==value and d.detailsFor(sid(2))['task']['note']==value
    # Quick dates and an optional separate review time use the actual controls.
    tomorrow=visual(page,'dailyDueTomorrow');reveal(window,tomorrow,scroll);click(window,tomorrow)
    expected=(datetime.now()+timedelta(days=1)).strftime('%Y-%m-%d')+' 20:00'
    assert due.property('text')==expected
    custom=visual(page,'dailyCustomReview');reveal(window,custom,scroll);click(window,custom)
    review=visual(page,'dailyReview');assert review.isVisible()
    review.setProperty('text','')
    before=d.detailsFor(sid(2))['task']['revision']
    click(window,save);QTest.qWait(600)
    assert custom.property('checked') and review.property('activeFocus')
    assert d.detailsFor(sid(2))['task']['revision']==before
    d.selectRow(1)
    assert d.selectedId==sid(2) and custom.property('checked') and review.property('text')==''
    review.setProperty('text','2099-12-30 19:30')
    assert d.flushEditor()
    assert d.detailsFor(sid(2))['task']['review_at']=='2099-12-30T19:30:00'
    reveal(window,custom,scroll);click(window,custom)
    due.setProperty('text','2099-12-31 20:00');QTest.qWait(600)
    task=d.detailsFor(sid(2))['task']
    assert task['review_at']==task['due_at'] and not review.isVisible()
    # A calendar can stay open beyond the autosave delay without invalidating its key.
    before=task['revision'];note.setProperty('text','日历选择期间保留输入')
    date_button=visual(page,'dailyDueDate');reveal(window,date_button,scroll)
    def choose_after_wait(initial):
        QTest.qWait(650)
        assert d.detailsFor(sid(2))['task']['revision']==before
        return '2099-12-30'
    with patch.object(b,'chooseDate',side_effect=choose_after_wait): click(window,date_button)
    QTest.qWait(600)
    assert d.detailsFor(sid(2))['task']['due_at']=='2099-12-30T20:00:00'
    assert d.detailsFor(sid(2))['task']['note']=='日历选择期间保留输入'
    # A calendar result must not enter another student's card after a switch.
    date_button=visual(page,'dailyDueDate');reveal(window,date_button,scroll)
    with patch.object(b,'chooseDate',side_effect=lambda initial:(d.selectRow(1),'2099-12-12')[1]):
        click(window,date_button)
    assert d.selectedId==sid(3) and due.property('text')==''
    note.setProperty('text','未联系到，稍后再试')
    click(window,visual(page,'dailySaveContact'))
    assert not d.detailsFor(sid(3))['task'] and '未联系到，稍后再试' in d.detailsFor(sid(3))['history']
    assert not d._drafts
    d.selectRow(0);QTest.qWait(40)
    # Invalid text must survive a rejected close and row switch.
    due.setProperty('text','invalid');QTest.qWait(20)
    click(window,save)
    assert visual(page,'dailyDueError').isVisible() and due.property('activeFocus')
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
        QTest.qWait(650)
        key=visual(page,'dailyEditor').property('loadedKey')
        token=visual(page,'dailyEditor').property('editorToken')
        assert not d.flushEditor()
        assert note.property('text')=='main draft' and d.hasDraft(key,token)
        d.discardDraft(key,token);d.reload(True)
        outer=visual(floating.contentItem(),'campaignDetailScroll')
        floatDue=visual(floatEditor,'dailyDue');floatDue.forceActiveFocus();QTest.qWait(40)
        position=floatDue.mapToScene(QPointF(0,0))
        assert position.y()>=0 and position.y()+floatDue.height()<=floating.height()
        floatSave=visual(floatEditor,'dailySaveCommitment');floatSave.forceActiveFocus();QTest.qWait(40)
        position=floatSave.mapToScene(QPointF(0,0))
        assert position.y()>=0 and position.y()+floatSave.height()<=floating.height()
        reveal(floating,floatNote,outer)
        assert floating.grabWindow().save(str(output/'floating-followup.png'))
        floating.close()
    note.setProperty('text','已确认：明晚补齐第2节作业');QTest.qWait(600)
    assert d.detailsFor(sid(2))['task']['note']==note.property('text')
    # Long history grows only the scrolling body; primary actions stay in place.
    with b.db.connect() as conn:
        for index in range(12): d.store.event(conn,d.detailsFor(sid(2))['task']['id'],sid(2),'联系记录',dict(note=f'虚构历史记录{index}'))
    d.reload(True)
    history=visual(page,'dailyHistoryToggle');reveal(window,history,scroll)
    footer_y=save.mapToScene(QPointF(0,0)).y();click(window,history)
    assert visual(page,'dailyHistory').isVisible() and save.mapToScene(QPointF(0,0)).y()==footer_y
    assert visual(page,'dailyHistory').height()>150
    click(window,history)
    for theme in ('light','dark'):
        b.settingsModule.setAppearanceMode(theme)
        for width,height in ((1280,820),(1000,700),(720,480)):
            window.resize(width,height);QTest.qWait(80)
            visual(page,'dailyDetailScroll').property('contentItem').setProperty('contentY',0)
            assert window.grabWindow().save(str(output/f'{theme}-{width}.png'))
            if width==1280:
                capture=visual(page,'dailyDetailCard').grabToImage()
                for _ in range(10):
                    if not capture.image().isNull(): break
                    QTest.qWait(20)
                assert capture.saveToFile(str(output/f'card-{theme}.png'))
            assert page.width()<width
            table=visual(page,'dailyTable')
            assert table.height()>=100,(width,table.height())
            if width in (1000,720):
                page.setProperty('detailOpen',True);QTest.qWait(40)
                assert window.grabWindow().save(str(output/f'{theme}-detail-{width}.png'))
                for name in ('dailyOpenContact','dailySaveCommitment','dailyDiscard'):
                    item=visual(page,name);position=item.mapToScene(QPointF(0,0))
                    assert item.isVisible() and position.y()+item.height()<=window.height(),(width,name,position,item.height())
                assert visual(page,'dailyDetailScroll').height()>=20
                page.setProperty('detailOpen',False)
    assert not [message for message in errors if any(name in message for name in ('DailyWorkspace.qml','FollowupEditor.qml'))],errors
    window.close();engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
    b._date_timer.stop();d._timer.stop()
    case.doCleanups()
    print('Daily workspace real QML smoke passed (card shortcuts/dates/autosave/IME/conflicts, navigation, themes, 3 sizes, guards, goals, lists).')


if __name__=='__main__':run()
