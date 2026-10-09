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
    signal prefixEdited()
    signal resolveRequested(int recipientId, bool wasSent)
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
                panel.loadDefaults(false)
            }
        }
        function onRowsChanged() {
            panel.restoreSelection()
            if(!defaults.dirty && defaults.editingIndex<0) panel.loadDefaults(true)
        }
        function onModelInfoChanged() { namesTable.forceLayout() }
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
            Layout.preferredWidth: panel.width<750 ? 140 : 204
            Layout.fillHeight: true; padding: 10
            ColumnLayout {
                anchors.fill: parent; spacing: 8
                Label { text: "收件人"; font.bold: true; font.pixelSize: 15 }
                UiTextField {
                    id: prefix; objectName: "groupContactPrefix"; Layout.fillWidth: true
                    enabled: !center.active && center.selectedIndex>=0
                    placeholderText: "姓名前缀（可留空）"; Accessible.name: "姓名前缀"
                    onTextChanged: panel.prefixEdited()
                }
                TabBar {
                    id: tabs; objectName: "groupMessageTabs"; Layout.fillWidth: true
                    onCurrentIndexChanged: panel.selectedRow=({})
                    TabButton { text: "待处理 "+center.pendingCount; font.pixelSize: 12 }
                    TabButton { text: "已发送 "+center.sentCount; font.pixelSize: 12 }
                }
                TableView {
                    id: namesTable; objectName: "groupNamesTable"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: panel.currentModel; clip: true; reuseItems: true; rowSpacing: 2
                    columnWidthProvider: function(c) { return c===0 ? namesTable.width : 0 }
                    rowHeightProvider: function(r) { return 42 }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: Rectangle {
                        id: nameCell
                        required property int row
                        required property string display
                        required property string recordKey
                        objectName: "groupName"+row
                        implicitWidth: 160; implicitHeight: 42; radius: 5
                        color: recordKey===String(panel.selectedRow.id || "") ? UiTheme.selection : nameHover.hovered ? UiTheme.stripe : UiTheme.surface
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: panel.contactPrefix+display
                        Accessible.description: "双击查看或编辑个人消息"
                        Text {
                            objectName: "groupNameLabel"+nameCell.row
                            anchors.fill: parent; anchors.margins: 7
                            text: panel.contactPrefix+nameCell.display; textFormat: Text.PlainText
                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: UiTheme.ink; font.pixelSize: 14
                        }
                        TapHandler {
                            onTapped: { panel.selectedRow=panel.currentModel.get(nameCell.row); nameCell.forceActiveFocus() }
                            onDoubleTapped: { panel.selectedRow=panel.currentModel.get(nameCell.row); panel.openEditor() }
                        }
                        Keys.onReturnPressed: { panel.selectedRow=panel.currentModel.get(row); panel.openEditor() }
                        Keys.onEnterPressed: { panel.selectedRow=panel.currentModel.get(row); panel.openEditor() }
                        HoverHandler { id: nameHover }
                        ToolTip.visible: nameHover.hovered
                        ToolTip.text: panel.contactPrefix+display+" · 双击查看或编辑"
                    }
                }
                Label { text: "双击姓名 · 单独编辑"; color: UiTheme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                UiButton { objectName: "groupEditPersonButton"; text: "查看个人消息"; Layout.fillWidth: true; visible: !!panel.selectedRow.id; enabled: !center.active; onClicked: panel.openEditor() }
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
