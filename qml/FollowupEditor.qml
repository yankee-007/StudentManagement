import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property var daily: backend.dailyWorkspace
    property string studentId: ""
    property var detail: ({options: [], task: {}, selectedItems: []})
    property string loadedKey: ""
    property bool loading: true
    property bool dirty: false
    property bool ready: false
    property string editorToken: "editor-"+Math.random().toString(36).slice(2)
    property var chosen: []
    property var itemOptions: []
    property var alternatives: []
    property bool showContact: true
    property bool compact: false
    property var outerScroll: null
    readonly property bool embedded: !showContact
    readonly property bool tight: !embedded && height < 260
    property bool attempted: false
    property string saveState: "填写后点击保存承诺"
    property bool saveFailed: false
    readonly property bool complete: chosen.length > 0 && validTime(due.text) && (!customReview.checked || validTime(review.text))
    spacing: tight ? 3 : compact ? 5 : 8

    function validTime(value) {
        var match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/)
        if (!match) return false
        var parsed = new Date(Number(match[1]), Number(match[2])-1, Number(match[3]), Number(match[4]), Number(match[5]), Number(match[6] || 0))
        return parsed.getFullYear()===Number(match[1]) && parsed.getMonth()===Number(match[2])-1 && parsed.getDate()===Number(match[3]) && parsed.getHours()===Number(match[4]) && parsed.getMinutes()===Number(match[5]) && parsed.getSeconds()===Number(match[6] || 0)
    }
    function values() { return {items: chosen.slice(), due_at: due.text, review_at: customReview.checked ? review.text : "", review_required: customReview.checked, note: note.text} }
    function queue() {
        if (!loading && loadedKey && !note.inputMethodComposing) {
            dirty = true
            daily.queueDraft(loadedKey, values(), editorToken)
            saveFailed = false
            saveState = detail.task.id ? (complete ? "等待自动保存…" : "草稿已保留，请补齐填写") : "未保存，确认约定后点击保存承诺"
            if (detail.task.id && complete) saveTimer.restart()
            else saveTimer.stop()
        }
    }
    function load() {
        var next = daily.detailsFor(studentId)
        if (loadedKey !== (next.key || "") && dirty && daily.hasDraft(loadedKey, editorToken)) return
        var changedKey = loadedKey !== (next.key || "")
        var changedStudent = !loadedKey || !next.key || JSON.stringify(JSON.parse(loadedKey).slice(0,2))!==JSON.stringify(JSON.parse(next.key).slice(0,2))
        var changedTask = detail.task.id !== next.task.id
        detail = next
        if (JSON.stringify(itemOptions)!==JSON.stringify(next.options || [])) itemOptions=next.options || []
        if (JSON.stringify(alternatives)!==JSON.stringify(next.alternatives || [])) alternatives=next.alternatives || []
        if (!changedKey && !loading) return
        shortcuts.close()
        saveTimer.stop()
        loading = true
        loadedKey = next.key || ""
        chosen = (next.selectedItems || []).slice()
        due.text = (next.task.due_at || "").replace("T", " ").slice(0,16)
        review.text = (next.task.review_at || "").replace("T", " ").slice(0,16)
        customReview.checked = !!next.task.review_at && next.task.review_at !== next.task.due_at
        note.text = next.task.note || ""
        if (changedStudent) { contactOptions.loadPrefix(daily.contactPrefix); historyToggle.checked=false }
        if (changedStudent || changedTask) { cancelReason.text=""; cancelToggle.checked=false }
        attempted = false
        saveFailed = false
        saveState = next.task.id ? "修改后自动保存" : "填写后点击保存承诺"
        dirty = false
        loading = false
    }
    function persist(automatic) {
        if (!loadedKey || note.inputMethodComposing) return false
        saveTimer.stop()
        if (!automatic) attempted = true
        if (!complete) {
            saveFailed = true
            saveState = !chosen.length ? "请至少选择一项课程或作业" : !validTime(due.text) ? "请填写有效的承诺期限" : "请填写有效的复查时间"
            focusField(!chosen.length ? suggestions : !validTime(due.text) ? due : review)
            return false
        }
        var success = daily.saveCommitment(loadedKey, values(), editorToken)
        saveFailed = !success
        saveState = success ? (automatic ? "已自动保存" : "承诺已保存") : (daily.summary.notice || "保存失败，输入已保留")
        if (!success && !automatic) {
            if (!chosen.length) focusField(suggestions)
            else if (!validTime(due.text)) focusField(due)
            else if (customReview.checked && !validTime(review.text)) focusField(review)
        }
        return success
    }
    function focusField(field) {
        field.forceActiveFocus()
        Qt.callLater(function() { editor.ensureVisible(field) })
    }
    function ensureVisible(field) {
        var scroll = embedded ? outerScroll : bodyScroll
        if (!scroll || !field.visible) return
        var viewport = scroll.contentItem
        var y = field.mapToItem(scroll, 0, 0).y
        if (y < 0) viewport.contentY = Math.max(0, viewport.contentY+y-8)
        else if (y+field.height > scroll.availableHeight)
            viewport.contentY += y+field.height-scroll.availableHeight+8
    }
    function chooseDay(field) {
        var captured = loadedKey
        saveTimer.stop()
        var selected = backend.chooseDate(field.text.slice(0,10))
        if (captured === loadedKey && selected) field.text = selected + " " + (field.text.slice(11,16) || "20:00")
        else if (captured === loadedKey && dirty && complete && detail.task.id) saveTimer.restart()
    }
    function quickDeadline(days) {
        var day = new Date()
        day.setDate(day.getDate()+days)
        due.text = day.getFullYear()+"-"+String(day.getMonth()+1).padStart(2,"0")+"-"+String(day.getDate()).padStart(2,"0")+" 20:00"
    }
    Component.onCompleted: { ready=true; load() }
    onStudentIdChanged: if (ready) load()
    Connections {
        target: editor.daily
        function onChanged() { editor.load() }
        function onSaved(key, success, token) {
            if (token !== editor.editorToken || key !== editor.loadedKey) return
            if (success) { editor.dirty=false; editor.load() }
            else { editor.saveFailed=true; editor.saveState=editor.daily.summary.notice || "保存失败，输入已保留" }
        }
    }
    Timer {
        id: saveTimer; interval: 500
        onTriggered: {
            if (editor.dirty && editor.complete && editor.detail.task.id && editor.daily.hasDraft(editor.loadedKey, editor.editorToken)) editor.persist(true)
        }
    }
    RowLayout {
        visible: editor.showContact
        Layout.fillWidth: true; spacing: 6
        Label {
            text: editor.detail.name || "选择学员"; font.bold: true; font.pixelSize: 20; color: UiTheme.ink
            Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight
            ToolTip.visible: nameHover.hovered; ToolTip.text: text
            HoverHandler { id: nameHover }
        }
        UiButton {
            objectName: "dailyOpenContact"; text: backend.contactOpener.active ? "正在打开…" : "打开企微联系人"; font.pixelSize: 12
            enabled: !!editor.loadedKey && !backend.contactOpener.active && !backend.workflow.send_busy && !backend.groupCenter.active
            onClicked: {
                var contactPrefix = contactOptions.effectivePrefix
                Qt.inputMethod.commit()
                if (editor.daily.flushEditor()) backend.contactOpener.openDailyContact(editor.daily.detailsFor(editor.studentId).key, contactPrefix)
            }
        }
        ContactOptions { id: contactOptions; objectName: "dailyContactOptions"; namePrefix: editor.showContact ? "daily" : "followup-"+editor.editorToken }
    }
    Label {
        text: editor.detail.status || ""; visible: text.length > 0 && !editor.tight
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning; font.pixelSize: 12
    }
    Rectangle { visible: editor.showContact; Layout.fillWidth: true; implicitHeight: 1; color: UiTheme.line }
    ScrollView {
        id: bodyScroll; objectName: "dailyDetailScroll"
        Layout.fillWidth: true; Layout.fillHeight: !editor.embedded
        Layout.preferredHeight: editor.embedded ? body.implicitHeight : -1
        Layout.minimumHeight: editor.embedded ? body.implicitHeight : 20
        contentWidth: availableWidth; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: editor.embedded ? ScrollBar.AlwaysOff : ScrollBar.AsNeeded
        ColumnLayout {
            id: body; width: bodyScroll.availableWidth - 6; spacing: 6
            Label { visible: editor.tight && text.length>0; text: editor.detail.status || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning; font.pixelSize: 12 }
            Label { text: editor.detail.profile || ""; visible: text.length>0; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            Label { text: backend.contactOpener.notice; visible: editor.showContact && (backend.contactOpener.active || text !== "按姓名包含匹配，可选择是否保留企微浮窗"); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            RowLayout {
                id: noteRow; Layout.fillWidth: true; spacing: 6
                Label { text: "联系记录"; Layout.preferredWidth: editor.compact ? 56 : 64; color: UiTheme.muted; font.pixelSize: 12 }
                UiTextField {
                    id: note; objectName: "dailyNote"; Layout.fillWidth: true; enabled: !!editor.loadedKey; selectByMouse: true
                    implicitHeight: editor.compact ? 30 : 34
                    placeholderText: "沟通结果或未完成原因"; Accessible.name: "联系记录和未完成原因"
                    onTextChanged: editor.queue()
                    onInputMethodComposingChanged: editor.queue()
                    onTextEdited: shortcuts.close()
                    onActiveFocusChanged: if (activeFocus) editor.ensureVisible(note)
                    onAccepted: { Qt.inputMethod.commit(); editor.detail.task.id ? editor.persist(false) : editor.focusField(due) }
                    TapHandler { enabled: note.enabled; onTapped: { note.forceActiveFocus(); shortcuts.open() } }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "承诺安排"; font.bold: true; color: UiTheme.ink; Layout.fillWidth: true }
                Label { text: "已选"+editor.chosen.length+"项"; color: UiTheme.muted; font.pixelSize: 12 }
            }
            UiComboBox {
                id: suggestions; objectName: "dailySuggestion"
                visible: editor.alternatives.length > 1
                Layout.fillWidth: true; model: editor.alternatives; textRole: "title"
                currentIndex: editor.alternatives.findIndex(function(option) { return option.items.slice().sort().join(",")===editor.chosen.slice().sort().join(",") })
                displayText: currentIndex>=0 ? currentText : "自选项目（可切换建议方案）"
                Accessible.name: "选择建议补齐方案"
                onActiveFocusChanged: if (activeFocus) editor.ensureVisible(suggestions)
                onActivated: { editor.chosen=editor.alternatives[currentIndex].items.slice(); editor.queue() }
            }
            Label { visible: !editor.itemOptions.length; text: "暂无可登记项目，请检查目标和学习数据。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            Repeater {
                model: [{prefix:"c",title:"课程"},{prefix:"z",title:"作业"}]
                RowLayout {
                    required property var modelData
                    readonly property var options: editor.itemOptions.filter(function(option) { return option.key.charAt(0)===modelData.prefix })
                    visible: options.length>0
                    Layout.fillWidth: true; spacing: 6
                    Label { text: modelData.title; Layout.preferredWidth: editor.compact ? 36 : 44; color: UiTheme.muted; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true; spacing: 2
                        Repeater {
                            model: options
                            CheckBox {
                                required property var modelData
                                objectName: "dailyItem_"+modelData.key
                                text: "第"+modelData.key.slice(1)+"节"; checked: editor.chosen.indexOf(modelData.key)>=0; enabled: !!editor.loadedKey
                                implicitHeight: editor.compact ? 28 : 30
                                Accessible.name: modelData.label
                                onActiveFocusChanged: if (activeFocus) editor.ensureVisible(this)
                                onClicked: {
                                    var copy=editor.chosen.slice(), index=copy.indexOf(modelData.key)
                                    if (checked && index<0) copy.push(modelData.key)
                                    else if (!checked && index>=0) copy.splice(index,1)
                                    editor.chosen=copy; editor.queue()
                                }
                            }
                        }
                    }
                }
            }
            Label { visible: editor.attempted && !editor.chosen.length; text: "请至少选择一项课程或作业"; color: UiTheme.danger; Layout.fillWidth: true; wrapMode: Text.Wrap }
            GridLayout {
                columns: editor.compact ? 2 : 3
                Layout.fillWidth: true; columnSpacing: 6; rowSpacing: 4
                Label { text: "承诺期限"; Layout.columnSpan: editor.compact ? 2 : 1; Layout.preferredWidth: editor.compact ? -1 : 64; color: UiTheme.muted; font.pixelSize: 12 }
                UiTextField {
                    id: due; objectName: "dailyDue"; Layout.fillWidth: true; enabled: !!editor.loadedKey
                    implicitHeight: editor.compact ? 30 : 34; placeholderText: "YYYY-MM-DD HH:mm"; selectByMouse: true; Accessible.name: "承诺期限"
                    onTextChanged: editor.queue()
                    onActiveFocusChanged: if (activeFocus) editor.ensureVisible(due)
                    onAccepted: { Qt.inputMethod.commit(); editor.persist(false) }
                }
                UiButton { objectName: "dailyDueDate"; text: "日期"; implicitWidth: 48; leftPadding: 8; rightPadding: 8; enabled: !!editor.loadedKey; onClicked: editor.chooseDay(due) }
            }
            Label { objectName: "dailyDueError"; visible: editor.attempted && !editor.validTime(due.text); text: "请填写有效日期和时间，例如2026-10-09 20:00"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.danger; font.pixelSize: 12 }
            Flow {
                Layout.fillWidth: true; spacing: 6
                UiButton { objectName: "dailyDueToday"; text: "今天20:00"; enabled: !!editor.loadedKey; onClicked: editor.quickDeadline(0) }
                UiButton { objectName: "dailyDueTomorrow"; text: "明天20:00"; enabled: !!editor.loadedKey; onClicked: editor.quickDeadline(1) }
            }
            CheckBox {
                id: customReview; objectName: "dailyCustomReview"; text: "另设复查时间（默认到期复查）"; enabled: !!editor.loadedKey
                onToggled: {
                    if (editor.loading) return
                    if (checked && review.text===due.text) review.text=""
                    editor.queue()
                    if (checked) Qt.callLater(function() { editor.focusField(review) })
                }
                onActiveFocusChanged: if (activeFocus) editor.ensureVisible(customReview)
            }
            GridLayout {
                columns: editor.compact ? 2 : 3
                visible: customReview.checked; Layout.fillWidth: true; columnSpacing: 6; rowSpacing: 4
                Label { text: "复查时间"; Layout.columnSpan: editor.compact ? 2 : 1; Layout.preferredWidth: editor.compact ? -1 : 64; color: UiTheme.muted; font.pixelSize: 12 }
                UiTextField {
                    id: review; objectName: "dailyReview"; Layout.fillWidth: true; enabled: !!editor.loadedKey; implicitHeight: editor.compact ? 30 : 34
                    placeholderText: "YYYY-MM-DD HH:mm"; selectByMouse: true; Accessible.name: "复查时间"
                    onTextChanged: editor.queue()
                    onActiveFocusChanged: if (activeFocus) editor.ensureVisible(review)
                    onAccepted: { Qt.inputMethod.commit(); editor.persist(false) }
                }
                UiButton { objectName: "dailyReviewDate"; text: "日期"; implicitWidth: 48; leftPadding: 8; rightPadding: 8; enabled: !!editor.loadedKey; onClicked: editor.chooseDay(review) }
            }
            Label { visible: customReview.checked && editor.attempted && !editor.validTime(review.text); text: "请填写有效的复查日期和时间"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.danger; font.pixelSize: 12 }
            CheckBox { id: estimateToggle; text: "查看补齐后的指标变化"; onActiveFocusChanged: if (activeFocus) editor.ensureVisible(estimateToggle) }
            Label { visible: estimateToggle.checked; text: editor.daily.estimate(editor.studentId,editor.chosen); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            Label { text: "核验："+(editor.detail.task.result || "尚无承诺")+(editor.detail.task.evidence && editor.detail.task.evidence.time ? " · 完成"+editor.detail.task.evidence.completed.length+"/"+editor.detail.task.items.length+"项，未知"+editor.detail.task.evidence.unknown.length+"项" : ""); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink; font.pixelSize: 12 }
            CheckBox { id: historyToggle; objectName: "dailyHistoryToggle"; text: "查看跟进历史与群发记录"; onActiveFocusChanged: if (activeFocus) editor.ensureVisible(historyToggle) }
            Label { visible: historyToggle.checked; text: editor.detail.sends || "尚未关联群发名单"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            Label { objectName: "dailyHistory"; visible: historyToggle.checked; text: editor.detail.history || "暂无历史"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            CheckBox { id: cancelToggle; objectName: "dailyCancelToggle"; visible: !!editor.detail.task.id; text: "取消当前承诺"; onActiveFocusChanged: if (activeFocus) editor.ensureVisible(cancelToggle) }
            ColumnLayout {
                visible: cancelToggle.checked && !!editor.detail.task.id; Layout.fillWidth: true
                UiTextField { id: cancelReason; Layout.fillWidth: true; placeholderText: "填写取消原因"; Accessible.name: "取消承诺原因" }
                UiButton { text: "确认取消承诺"; onClicked: { saveTimer.stop(); editor.daily.cancelTask(editor.loadedKey,cancelReason.text,editor.editorToken) } }
            }
        }
    }
    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UiTheme.line }
    ColumnLayout {
        objectName: "dailyActions"; Layout.fillWidth: true; spacing: 5
        Flow {
            Layout.fillWidth: true; spacing: 6
            UiButton { objectName: "dailySaveCommitment"; text: "保存承诺"; highlighted: true; enabled: !!editor.loadedKey; onActiveFocusChanged: if (activeFocus && editor.embedded) editor.ensureVisible(this); onClicked: { Qt.inputMethod.commit(); editor.persist(false) } }
            UiButton { objectName: "dailySaveContact"; text: "仅记联系"; enabled: !!editor.loadedKey; onClicked: {
                Qt.inputMethod.commit(); saveTimer.stop()
                if (editor.daily.saveContactNote(editor.loadedKey,note.text,editor.editorToken)) { editor.dirty=false; editor.loading=true; editor.load(); editor.saveState="联系记录已保存" }
                else { editor.saveFailed=true; editor.saveState=editor.daily.summary.notice || "保存失败，输入已保留"; editor.focusField(note) }
            } }
            UiButton { objectName: "dailyDiscard"; text: "撤销输入"; enabled: editor.dirty; onClicked: { saveTimer.stop(); editor.daily.discardDraft(editor.loadedKey,editor.editorToken); editor.dirty=false; editor.loading=true; editor.load() } }
        }
        Label {
            objectName: "dailySaveState"; text: editor.saveState; Layout.fillWidth: true; wrapMode: Text.Wrap
            maximumLineCount: 2; elide: Text.ElideRight
            color: editor.saveFailed ? UiTheme.danger : UiTheme.muted; font.pixelSize: 12
            Accessible.description: text
            ToolTip.visible: stateHover.hovered; ToolTip.text: text
            HoverHandler { id: stateHover }
        }
    }
    Menu {
        id: shortcuts; objectName: editor.showContact ? "dailyShortcutMenu" : "followup-"+editor.editorToken+"ShortcutMenu"; parent: Overlay.overlay; focus: false; modal: false
        width: Math.min(noteRow.width, parent ? parent.width-16 : noteRow.width)
        property string capturedKey: ""
        property point editorPoint: Qt.point(0,0)
        property real bottomSpace: Math.max(0,parent.height-editorPoint.y-noteRow.height-12)
        height: Math.min(implicitHeight,Math.max(bottomSpace,editorPoint.y-12))
        x: Math.max(8,Math.min(editorPoint.x,parent.width-width-8))
        y: bottomSpace>=height ? editorPoint.y+noteRow.height+4 : editorPoint.y-height-4
        function positionAtEditor() { editorPoint=noteRow.mapToItem(parent,0,0) }
        onAboutToShow: { saveTimer.stop(); capturedKey=editor.loadedKey; positionAtEditor() }
        onOpened: positionAtEditor()
        onClosed: if (editor.dirty && editor.complete && editor.detail.task.id) saveTimer.restart()
        Connections { target: bodyScroll.contentItem; function onContentYChanged() { if (shortcuts.visible) Qt.callLater(shortcuts.positionAtEditor) } }
        Instantiator {
            model: backend.workflow.feedbackShortcuts
            delegate: MenuItem {
                required property string modelData
                required property int index
                objectName: "dailyShortcutOption"+index; text: modelData
                onTriggered: {
                    shortcuts.close()
                    if (!editor.loadedKey || shortcuts.capturedKey!==editor.loadedKey) return
                    note.text=note.text.length ? note.text+"；"+modelData : modelData
                    editor.focusField(note); note.cursorPosition=note.text.length
                }
            }
            onObjectAdded: function(index, object) { shortcuts.insertItem(index,object) }
            onObjectRemoved: function(index, object) { shortcuts.removeItem(object) }
        }
    }
}
