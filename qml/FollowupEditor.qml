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
    property bool showContact: true
    spacing: 8
    function values() { return {items: chosen.slice(), due_at: due.text, review_at: review.text, note: note.text} }
    function queue() {
        if (!loading && loadedKey && !note.inputMethodComposing) {
            dirty = true
            daily.queueDraft(loadedKey, values(),editorToken)
        }
    }
    function load() {
        var next = daily.detailsFor(studentId)
        if (loadedKey !== (next.key || "") && dirty && daily.hasDraft(loadedKey,editorToken)) return
        var changedKey = loadedKey !== (next.key || "")
        detail = next
        if (!changedKey && !loading) return
        loading = true
        loadedKey = next.key || ""
        chosen = (next.selectedItems || []).slice()
        due.text = (next.task.due_at || "").replace("T", " ").slice(0,16)
        review.text = (next.task.review_at || "").replace("T", " ").slice(0,16)
        note.text = next.task.note || ""
        prefix.text = daily.contactPrefix
        cancelReason.text = ""
        dirty = false
        loading = false
    }
    function chooseDay(field) {
        var captured = loadedKey
        var selected = backend.chooseDate(field.text.slice(0,10))
        if (captured === loadedKey && selected) field.text = selected + " " + (field.text.slice(11,16) || "20:00")
    }
    Component.onCompleted: { ready=true; load() }
    onStudentIdChanged: if (ready) load()
    Connections {
        target: editor.daily
        function onChanged() { editor.load() }
        function onSaved(key, success, token) { if (token === editor.editorToken && key === editor.loadedKey && success) { editor.dirty=false; editor.load() } }
    }
    Label { text: editor.detail.name || "选择学员"; font.bold: true; font.pixelSize: 18; color: UiTheme.ink; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: editor.detail.profile || ""; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    RowLayout {
        visible: editor.showContact && !!editor.loadedKey
        Layout.fillWidth: true
        UiTextField { id: prefix; objectName: "dailyContactPrefix"; text: backend.contactOpener.defaultPrefix; placeholderText: "联系人前缀"; Layout.fillWidth: true; Accessible.name: "联系人前缀" }
        UiButton { objectName: "dailyOpenContact"; text: "打开联系人"; enabled: !backend.contactOpener.active && !backend.workflow.send_busy; onClicked: {
            var contactPrefix = prefix.text
            Qt.inputMethod.commit()
            if (editor.daily.flushEditor()) backend.contactOpener.openDailyContact(editor.daily.detailsFor(editor.studentId).key, contactPrefix)
        } }
    }
    Label { text: backend.contactOpener.notice; visible: editor.showContact && text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    Label { text: editor.detail.status || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
    Label { text: "承诺完成项目"; font.bold: true; color: UiTheme.ink }
    UiComboBox {
        visible: (editor.detail.alternatives || []).length > 1
        Layout.fillWidth: true; model: editor.detail.alternatives || []; textRole: "title"
        Accessible.name: "选择建议补齐方案"
        onActivated: { editor.chosen=editor.detail.alternatives[currentIndex].items.slice(); editor.queue() }
    }
    Label { visible: !(editor.detail.options || []).length; text: "暂无可登记项目；请检查目标和学习数据。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    Flow {
        Layout.fillWidth: true; spacing: 4
        Repeater {
            model: editor.detail.options || []
            CheckBox {
                required property var modelData
                objectName: "dailyItem_" + modelData.key
                text: modelData.label; checked: editor.chosen.indexOf(modelData.key) >= 0; enabled: !!editor.loadedKey
                onClicked: {
                    var copy=editor.chosen.slice(), index=copy.indexOf(modelData.key)
                    if (checked && index < 0) copy.push(modelData.key)
                    else if (!checked && index >= 0) copy.splice(index,1)
                    editor.chosen=copy; editor.queue()
                }
            }
        }
    }
    Label { text: editor.daily.estimate(editor.studentId,editor.chosen); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    Label { text: "承诺期限（日期 时间）"; color: UiTheme.ink }
    RowLayout {
        Layout.fillWidth: true
        UiTextField { id: due; objectName: "dailyDue"; Layout.fillWidth: true; enabled: !!editor.loadedKey; placeholderText: "YYYY-MM-DD HH:mm"; selectByMouse: true; Accessible.name: "承诺期限"; onTextChanged: editor.queue() }
        UiButton { text: "日期"; enabled: !!editor.loadedKey; onClicked: editor.chooseDay(due) }
    }
    Label { text: "复查时间（留空采用承诺期限）"; color: UiTheme.ink }
    RowLayout {
        Layout.fillWidth: true
        UiTextField { id: review; objectName: "dailyReview"; Layout.fillWidth: true; enabled: !!editor.loadedKey; placeholderText: "YYYY-MM-DD HH:mm"; selectByMouse: true; Accessible.name: "复查时间"; onTextChanged: editor.queue() }
        UiButton { text: "日期"; enabled: !!editor.loadedKey; onClicked: editor.chooseDay(review) }
    }
    Label { text: "联系记录 / 未完成原因"; color: UiTheme.ink }
    UiTextField {
        id: note; objectName: "dailyNote"; Layout.fillWidth: true; enabled: !!editor.loadedKey; selectByMouse: true
        Accessible.name: "联系记录和未完成原因"
        onTextChanged: editor.queue()
        onInputMethodComposingChanged: editor.queue()
    }
    RowLayout {
        Layout.fillWidth: true
        UiButton { objectName: "dailySaveCommitment"; text: "保存承诺"; highlighted: true; enabled: !!editor.loadedKey; onClicked: { Qt.inputMethod.commit(); editor.daily.saveCommitment(editor.loadedKey,editor.values(),editor.editorToken) } }
        UiButton { text: "仅记联系"; enabled: !!editor.loadedKey; onClicked: { Qt.inputMethod.commit(); if(editor.daily.saveContactNote(editor.loadedKey,note.text,editor.editorToken)) { editor.dirty=false; editor.loading=true; editor.load() } } }
        UiButton { text: "撤销输入"; enabled: editor.dirty; onClicked: { editor.daily.discardDraft(editor.loadedKey,editor.editorToken); editor.dirty=false; editor.loading=true; editor.load() } }
    }
    RowLayout {
        visible: !!editor.detail.task.id
        Layout.fillWidth: true
        UiTextField { id: cancelReason; Layout.fillWidth: true; placeholderText: "取消原因"; Accessible.name: "取消承诺原因" }
        UiButton { text: "取消承诺"; onClicked: editor.daily.cancelTask(editor.loadedKey,cancelReason.text,editor.editorToken) }
    }
    Label { text: "核验：" + (editor.detail.task.result || "尚无承诺") + (editor.detail.task.evidence && editor.detail.task.evidence.time ? " · "+editor.detail.task.evidence.time.slice(0,19).replace("T"," ")+" · 完成"+editor.detail.task.evidence.completed.length+"/"+editor.detail.task.items.length+"项，未知"+editor.detail.task.evidence.unknown.length+"项" : ""); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
    Label { text: editor.detail.sends || "尚未关联群发名单"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    Label { text: "跟进历史"; font.bold: true; color: UiTheme.ink }
    Label { objectName: "dailyHistory"; text: editor.detail.history || "暂无历史"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
}
