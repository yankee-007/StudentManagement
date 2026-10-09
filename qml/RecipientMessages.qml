import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: panel
    objectName: "recipientMessages"
    required property var center
    property alias contactPrefix: prefix.text
    property var selectedRow: ({})
    property int currentListId: -1
    property var currentModel: tabs.currentIndex===0 ? center.pendingModel : center.sentModel
    property bool canManage: !center.active && center.editableCount>0
    readonly property bool defaultsDirty: defaults.dirty
    property string draftRevision: ""
    property var pickedKeys: ({})
    property int lastPickedIndex: -1
    property string actionNotice: ""
    signal prefixEdited()
    signal resolveRequested(int recipientId, bool wasSent)
    function isPicked(key) { return pickedKeys[String(key)] === true }
    function clearPicked() { pickedKeys=({}); lastPickedIndex=-1 }
    function pickedRows() {
        var picked=[]
        for (var i=0;i<currentModel.rowCount();i++) {
            var row=currentModel.get(i)
            if (row && row['_record_key']!==undefined && isPicked(row['_record_key'])) picked.push(row)
        }
        return picked
    }
    // 像文件列表一样：单击选中一个，Ctrl 逐个增删，Shift 连选一段。
    function pickIndex(index, modifiers, key) {
        if ((modifiers & Qt.ShiftModifier) && lastPickedIndex>=0) {
            var lo=Math.min(lastPickedIndex,index), hi=Math.max(lastPickedIndex,index), picked={}
            for (var i=lo;i<=hi;i++) {
                var row=currentModel.get(i)
                if (row && row['_record_key']!==undefined) picked[String(row['_record_key'])]=true
            }
            pickedKeys=picked
            return
        }
        if (modifiers & Qt.ControlModifier) {
            var next={}
            for (var existing in pickedKeys) next[existing]=pickedKeys[existing]
            if (next[String(key)]===true) delete next[String(key)]
            else next[String(key)]=true
            pickedKeys=next
            lastPickedIndex=index
            return
        }
        var single={}
        single[String(key)]=true
        pickedKeys=single
        lastPickedIndex=index
    }
    function writeClipboard(text) { clipboard.text=text; clipboard.selectAll(); clipboard.copy() }
    function readClipboard() { clipboard.text=""; clipboard.paste(); var value=clipboard.text; clipboard.text=""; return value }
    function copyPicked() {
        var rows=pickedRows()
        if (!rows.length) { actionNotice="请先点选姓名（Ctrl 或 Shift 可多选）"; return }
        var names=[]
        for (var i=0;i<rows.length;i++) names.push(rows[i]['name'])
        writeClipboard(names.join("\n"))
        actionNotice="已复制 "+names.length+" 个姓名"
    }
    function pasteFromClipboard() {
        var text=String(readClipboard())
        if (!text.trim().length) { actionNotice="剪贴板里没有可粘贴的姓名"; return }
        addNamesFromText(text)
    }
    function addNamesFromText(text) {
        var lines=String(text).split(/[\r\n]+/), names=[]
        for (var i=0;i<lines.length;i++) {
            var value=lines[i].trim()
            if (value.length) names.push(value)
        }
        if (!names.length) { actionNotice="没有可添加的姓名"; return }
        submitNames(names)
    }
    function submitNames(names) {
        var result=center.addNames(center.selected.id,names)
        if (!result || result.added===undefined) { actionNotice=center.status; return 0 }
        var parts=[]
        if (result.added.length) parts.push("已添加 "+result.added.length+" 人")
        if (result.skipped.length) parts.push("跳过名单内同名 "+result.skipped.length+" 人")
        if (result.no_message.length) parts.push(result.no_message.length+" 人还没有消息，请双击单独填写")
        actionNotice=parts.length ? parts.join("；") : "没有可添加的姓名"
        if (result.added.length) { tabs.currentIndex=0; clearPicked() }
        return result.added.length
    }
    function addTypedName(text) {
        var name=String(text).trim()
        if (!name.length) return 0
        return submitNames([name])
    }
    function removePicked() {
        var rows=pickedRows()
        if (!rows.length) { actionNotice="请先点选要删除的姓名"; return }
        var ids=[]
        for (var i=0;i<rows.length;i++) ids.push(rows[i]['id'])
        removeDialog.ids=ids
        removeDialog.open()
    }
    function applyRemove(ids) {
        if (center.removeNames(center.selected.id,ids)) { clearPicked(); actionNotice="已删除 "+ids.length+" 人" }
        else actionNotice=center.status
    }
    function loadDefaults(preserveComposer) {
        defaults.load(center.defaultFields,!!preserveComposer)
        draftRevision=center.contentRevision
    }
    function saveCommittedDefaults(overridePersonal) {
        if(!defaults.dirty && !overridePersonal) return true
        if(!canManage || currentListId!==center.selected.id) return false
        if(!center.saveDefaultRow(currentListId,draftRevision,defaults.values(),!!overridePersonal)) {
            defaults.feedback=center.status+"；消息稿已保留，请修改后重试或重载。"
            return false
        }
        loadDefaults(true)
        return true
    }
    function saveDefaults() {
        if(editor.visible && (messages.dirty || messages.hasPending)) {
            messages.feedback="请先保存个人消息或取消修改。"
            return false
        }
        if(!defaults.checkPending()) return false
        return saveCommittedDefaults(false)
    }
    function editRecipient(recipientId) {
        if(!saveDefaults()) return
        tabs.currentIndex=0
        selectedRow=center.recipientForView(recipientId,false)
        openEditor()
    }
    function openEditor() {
        if(!selectedRow.id || !saveDefaults()) return
        editor.listId=center.selected.id
        editor.recipientId=selectedRow.id
        editor.canEdit=selectedRow.editable && !center.active
        editor.personState=selectedRow.state || ""
        editor.personInfo=selectedRow.detail || ""
        editor.title=(editor.canEdit ? "个人消息 · " : "查看消息 · ") + contactPrefix + selectedRow.name
        messages.load(selectedRow.items,false)
        editor.open()
    }
    function restoreSelection() {
        if(selectedRow.id) selectedRow=center.recipientForView(selectedRow.id,tabs.currentIndex===1)
    }
    Connections {
        target: panel.center
        function onSelectionChanged() {
            var listId=center.selected.id || 0
            if(listId!==panel.currentListId) {
                panel.currentListId=listId
                tabs.currentIndex=0
                panel.selectedRow=({})
                panel.clearPicked()
                panel.actionNotice=""
                panel.loadDefaults(false)
            }
        }
        function onRowsChanged() {
            panel.restoreSelection()
            if(!defaults.dirty && defaults.editingIndex<0) panel.loadDefaults(true)
        }
    }
    Component.onCompleted: { currentListId=center.selected.id || 0; loadDefaults(false) }
    RowLayout {
        anchors.fill: parent; spacing: 10
        UiPanel {
            objectName: "groupTemplatePanel"; Layout.fillWidth: true; Layout.fillHeight: true; padding: panel.height<350 ? 8 : 16
            ColumnLayout {
                anchors.fill: parent; spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Label { objectName: "groupTemplateTitle"; text: "消息模板"; font.bold: true; font.pixelSize: 17; Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                    UiButton { objectName: "groupResetDefaults"; text: "重载"; visible: defaults.dirty || (defaults.editingIndex>=0 && defaults.feedback.length>0); enabled: !center.active; implicitHeight: 28; onClicked: panel.loadDefaults(true) }
                    UiButton { objectName: "groupRetryDefaults"; text: panel.width<500 ? "重试" : "重试保存"; visible: defaults.dirty || (defaults.editingIndex>=0 && defaults.feedback.length>0); enabled: panel.canManage; implicitHeight: 28; onClicked: panel.saveDefaults() }
                    ToolButton {
                        text: "更多"; font.pixelSize: 12; enabled: panel.canManage; implicitHeight: 28
                        Accessible.name: "模板更多操作"; onClicked: templateMenu.popup()
                    }
                }
                Label {
                    text: center.selectedIndex<0 ? "先新建或生成名单" : center.active ? "发送中，消息模板暂不可编辑" : "加入后自动保存 · 保留个人改动 · 预览后开始群发"
                    Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12
                }
                MessageChatEditor {
                    id: defaults; objectName: "groupMessageChat"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    fileChooser: center; controlPrefix: "groupChat"; defaultTemplate: true; editable: panel.canManage
                    onCommitted: commitAccepted=panel.saveCommittedDefaults(false)
                    onEditCancelled: if(!dirty && panel.draftRevision!==center.contentRevision) panel.loadDefaults(true)
                }
            }
        }
        UiPanel {
            objectName: "groupRecipientsPanel"
            Layout.preferredWidth: panel.width<750 ? 150 : 216
            Layout.fillHeight: true; padding: 10
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                Label { text: "群发名单"; font.bold: true; font.pixelSize: 15 }
                Label {
                    objectName: "groupListHint"
                    text: tabs.currentIndex===0
                        ? "单击选中 · Ctrl/Shift 多选 · Ctrl+C/V 复制粘贴 · Delete 删除"
                        : "已发送记录只读；Ctrl+C 可复制姓名"
                    color: UiTheme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true
                }
                UiTextField {
                    id: prefix; objectName: "groupContactPrefix"; Layout.fillWidth: true
                    enabled: !center.active && center.selectedIndex>=0
                    placeholderText: "姓名前缀（可留空）"; Accessible.name: "姓名前缀"
                    onTextChanged: panel.prefixEdited()
                }
                TabBar {
                    id: tabs; objectName: "groupMessageTabs"; Layout.fillWidth: true
                    onCurrentIndexChanged: { panel.selectedRow=({}); panel.clearPicked(); panel.actionNotice="" }
                    TabButton { text: "待处理 "+center.pendingCount; font.pixelSize: 12 }
                    TabButton { text: "已发送 "+center.sentCount; font.pixelSize: 12 }
                }
                ListView {
                    id: namesTable; objectName: "groupNamesTable"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: panel.currentModel; clip: true; reuseItems: true; spacing: 0
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    footer: Item {
                        id: addCell
                        width: namesTable.width
                        height: visible ? 44 : 0
                        visible: tabs.currentIndex===0 && center.selectedIndex>=0
                        Rectangle { anchors.fill: parent; color: UiTheme.surface }
                        UiTextField {
                            id: newName; objectName: "groupAddNameInput"
                            anchors.fill: parent; anchors.margins: 5
                            placeholderText: "填写姓名，回车添加"; enabled: !center.active
                            Accessible.name: "添加群发名单姓名"
                            // 页脚是独立组件作用域：清空和重新聚焦只能在这里做。
                            onAccepted: if (panel.addTypedName(text)>0) { newName.text=""; newName.forceActiveFocus() }
                        }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: UiTheme.line }
                    }
                    delegate: Rectangle {
                        id: nameCell
                        required property int index
                        required property string display
                        required property string recordKey
                        objectName: "groupName"+index
                        width: namesTable.width; height: 42
                        color: panel.isPicked(recordKey) ? UiTheme.selection : nameMouse.containsMouse ? UiTheme.stripe : UiTheme.surface
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: panel.contactPrefix+display
                        Accessible.description: "双击查看或编辑个人消息；Ctrl 或 Shift 可多选"
                        Text {
                            objectName: "groupNameLabel"+nameCell.index
                            anchors.fill: parent; anchors.leftMargin: 7; anchors.rightMargin: 7
                            text: panel.contactPrefix+nameCell.display; textFormat: Text.PlainText
                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: UiTheme.ink; font.pixelSize: 14
                        }
                        // 表格式横线：每行底边一条分隔线。
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: UiTheme.line }
                        MouseArea {
                            id: nameMouse
                            anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.LeftButton
                            onClicked: function(mouse) {
                                panel.selectedRow=panel.currentModel.get(nameCell.index)
                                panel.pickIndex(nameCell.index,mouse.modifiers,nameCell.recordKey)
                                nameCell.forceActiveFocus()
                            }
                            onDoubleClicked: { panel.selectedRow=panel.currentModel.get(nameCell.index); panel.openEditor() }
                        }
                        Keys.onPressed: function(event) {
                            if (event.modifiers & Qt.ControlModifier && event.key===Qt.Key_C) { panel.copyPicked(); event.accepted=true }
                            else if (event.modifiers & Qt.ControlModifier && event.key===Qt.Key_V) { panel.pasteFromClipboard(); event.accepted=true }
                            else if (event.key===Qt.Key_Delete) { panel.removePicked(); event.accepted=true }
                            else if (event.key===Qt.Key_Return || event.key===Qt.Key_Enter) { panel.openEditor(); event.accepted=true }
                        }
                        ToolTip.visible: nameMouse.containsMouse
                        ToolTip.text: panel.contactPrefix+display+" · 双击查看或编辑"
                    }
                }
                Label {
                    objectName: "groupListNotice"
                    text: panel.actionNotice.length ? panel.actionNotice : "双击姓名查看或编辑个人消息"
                    color: panel.actionNotice.length ? UiTheme.warning : UiTheme.muted
                    font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                }
            }
        }
    }
    // QML 侧的系统剪贴板桥：与 TextField 自带的复制粘贴共用同一份文本。
    TextEdit { id: clipboard; objectName: "groupClipboardBridge"; visible: false; width: 0; height: 0 }
    Dialog {
        id: removeDialog; objectName: "groupRemoveNamesDialog"; anchors.centerIn: parent; modal: true; title: "从群发名单删除"
        property var ids: []
        width: Math.min(panel.width-20,430)
        ColumnLayout {
            anchors.fill: parent
            Label {
                text: "将从当前群发方案的待处理名单里删除选中的 "+removeDialog.ids.length+" 人。已发送、待核实以及已有发送记录的姓名不会被删除。"
                wrapMode: Text.Wrap; Layout.fillWidth: true
            }
            RowLayout {
                UiButton { objectName: "cancelRemoveNames"; text: "取消"; onClicked: removeDialog.close() }
                UiButton { objectName: "confirmRemoveNames"; text: "删除"; highlighted: true; onClicked: { removeDialog.close(); panel.applyRemove(removeDialog.ids) } }
            }
        }
    }
    Menu {
        id: templateMenu
        MenuItem { objectName: "groupOverridePersonal"; text: "将模板应用到个人改动…"; onTriggered: if(panel.saveDefaults()) overrideDialog.open() }
    }
    Dialog {
        id: overrideDialog; objectName: "groupOverrideDialog"; anchors.centerIn: parent; modal: true; title: "覆盖个人改动"
        width: Math.min(panel.width-20,430)
        ColumnLayout {
            anchors.fill: parent
            Label { text: "将已保存的模板应用到所有可编辑人员，覆盖个人消息改动。已发送和待核实记录保留。"; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                UiButton { text: "取消"; onClicked: overrideDialog.close() }
                UiButton { objectName: "groupConfirmOverride"; text: "应用模板"; highlighted: true; onClicked: if(panel.saveCommittedDefaults(true)) overrideDialog.close() }
            }
        }
    }
    Dialog {
        id: editor; objectName: "recipientMessageEditor"
        parent: Overlay.overlay
        anchors.centerIn: parent; modal: true; closePolicy: Popup.NoAutoClose
        onClosed: messages.cancelEdit()
        width: Math.min(parent.width-32,760); height: Math.min(parent.height-32,650)
        property int listId: 0
        property int recipientId: 0
        property bool canEdit: false
        property string personState: ""
        property string personInfo: ""
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            Label {
                text: editor.canEdit ? "只修改此人，保存后生效。个人消息按原文保存。" : "该记录只读，保留发送时内容。"
                wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted; font.pixelSize: 12
            }
            Label { text: editor.personState+(editor.personInfo ? " · "+editor.personInfo : ""); Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            MessageChatEditor {
                id: messages; objectName: "recipientMessageChat"
                Layout.fillWidth: true; Layout.fillHeight: true
                fileChooser: center; controlPrefix: "personChat"; editable: editor.canEdit && !center.active
            }
            Label { text: center.status; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight; wrapMode: Text.Wrap; color: UiTheme.warning; font.pixelSize: 12; ToolTip.visible: statusHover.hovered; ToolTip.text: text; HoverHandler { id: statusHover } }
            RowLayout {
                visible: editor.personState==="结果待确认" || editor.personState==="仅粘贴未发送"
                Layout.fillWidth: true; enabled: !center.active
                Label { text: "核实前不可编辑或重发"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning; font.pixelSize: 12 }
                UiButton { objectName: "groupResolveSent"; text: "核实已发送"; onClicked: { editor.close(); panel.resolveRequested(editor.recipientId,true) } }
                UiButton { objectName: "groupResolveUnsent"; text: "核实未发送"; onClicked: { editor.close(); panel.resolveRequested(editor.recipientId,false) } }
            }
            RowLayout {
                Layout.fillWidth: true
                UiButton { objectName: "cancelRecipientMessages"; text: editor.canEdit ? "取消" : "关闭"; onClicked: editor.close() }
                Item { Layout.fillWidth: true }
                Label { visible: editor.canEdit && messages.messageCount===0; text: "至少保留一条消息"; color: UiTheme.warning; font.pixelSize: 12 }
                UiButton {
                    objectName: "saveRecipientMessages"; text: "保存个人消息"; highlighted: true
                    visible: editor.canEdit; enabled: !center.active && messages.messageCount>0
                    onClicked: if(messages.checkPending() && center.saveRecipientContent(editor.listId,editor.recipientId,messages.values())) editor.close()
                }
            }
        }
    }
}
