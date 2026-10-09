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
    property bool canManage: !center.active && center.selectedIndex>=0 && (center.editableCount>0 || center.pendingCount+center.sentCount===0)
    readonly property bool defaultsDirty: defaults.dirty
    property string draftRevision: ""
    property var pickedKeys: ({})
    property int lastPickedIndex: -1
    property string actionNotice: ""
    property bool listMode: false
    property bool syncingLists: false
    property int rowsRevision: 0
    readonly property int messageFieldCount: tabs.currentIndex===0 ? Math.max(1,center.pendingFieldCount,center.defaultFields.length) : Math.max(1,center.sentFieldCount)
    readonly property real messageColumnWidth: Math.max(220,messageList.width/messageFieldCount)
    onMessageColumnWidthChanged: Qt.callLater(refreshListGeometry)
    readonly property real sharedHeaderHeight: Math.max(namesHeader.implicitHeight, templateHeader.implicitHeight)
    function setListMode(value) {
        if(value===listMode || !saveDefaults()) return
        templateDialog.close()
        listMode=value
        Qt.callLater(refreshListGeometry)
    }
    function syncLists(source, target) {
        if(!listMode || syncingLists) return
        syncingLists=true
        var offset=source.contentY-source.originY
        if(Math.abs(target.contentY-target.originY-offset)>0.1) {
            target.cancelFlick()
            target.contentY=target.originY+offset
        }
        syncingLists=false
    }
    function refreshListGeometry() {
        if(!listMode) return
        namesTable.forceLayout(); messageList.forceLayout()
        syncLists(namesTable,messageList)
    }
    function scrollRows(view,wheel,allowHorizontal) {
        view.cancelFlick()
        var horizontal=allowHorizontal && ((wheel.modifiers & Qt.ShiftModifier) || wheel.angleDelta.x!==0 || wheel.pixelDelta.x!==0)
        if(horizontal) {
            var dx=wheel.pixelDelta.x || wheel.pixelDelta.y || (wheel.angleDelta.x || wheel.angleDelta.y)/2
            view.contentX=Math.max(0,Math.min(view.contentX-dx,view.contentWidth-view.width))
        } else {
            var dy=wheel.pixelDelta.y || wheel.angleDelta.y/2
            view.contentY=Math.max(view.originY,Math.min(view.contentY-dy,view.originY+Math.max(0,view.contentHeight+view.bottomMargin-view.height)))
        }
        wheel.accepted=true
    }
    function cellText(row,column) {
        var item=(row.items || [])[column]
        return !item ? "" : item.type==="file" ? String(item.path).replace(/\\/g,"/").split("/").pop() : item.text
    }
    function showMessagePreview(cell) {
        var point=cell.mapToItem(Overlay.overlay,0,cell.height)
        messagePreview.text=cell.fullText
        messagePreview.heading=contactPrefix+(cell.rowData.name || "")+" · 消息"+(cell.column+1)
        messagePreview.x=Math.max(8,Math.min(point.x,Overlay.overlay.width-messagePreview.width-8))
        messagePreview.y=point.y+4
        if(messagePreview.y+messagePreview.height>Overlay.overlay.height-8) messagePreview.y=Math.max(8,point.y-cell.height-messagePreview.height-4)
        messagePreview.open()
    }
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
        if (!names.length) { actionNotice="没有可添加的姓名"; return 0 }
        return submitNames(names)
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
        return addNamesFromText(text)
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
                templateDialog.close()
                panel.loadDefaults(false)
            }
        }
        function onRowsChanged() {
            panel.rowsRevision++
            panel.restoreSelection()
            if(!defaults.dirty && defaults.editingIndex<0) panel.loadDefaults(true)
            Qt.callLater(panel.refreshListGeometry)
        }
    }
    Component.onCompleted: { currentListId=center.selected.id || 0; loadDefaults(false) }
    RowLayout {
        anchors.fill: parent; spacing: 10
        UiPanel {
            objectName: "groupRecipientsPanel"
            Layout.preferredWidth: panel.width<750 ? 150 : 216
            Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth
            Layout.fillHeight: true; padding: 10
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                ColumnLayout {
                    id: namesHeader; Layout.fillWidth: true; spacing: 6
                    Layout.preferredHeight: panel.sharedHeaderHeight
                    Layout.maximumHeight: Layout.preferredHeight
                    Label { objectName: "groupListTitle"; text: "群发名单"; font.bold: true; font.pixelSize: 15 }
                    UiTextField {
                        id: prefix; objectName: "groupContactPrefix"; Layout.fillWidth: true
                        enabled: !center.active && center.selectedIndex>=0
                        placeholderText: "姓名前缀（可选）"; Accessible.name: "姓名前缀"
                        onTextChanged: panel.prefixEdited()
                    }
                    Item { Layout.fillHeight: true }
                    TabBar {
                        id: tabs; objectName: "groupMessageTabs"; Layout.fillWidth: true
                        spacing: 8; padding: 0; implicitHeight: 36
                        background: Rectangle {
                            color: "transparent"
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: UiTheme.line; opacity: 0.55 }
                        }
                        onCurrentIndexChanged: { panel.selectedRow=({}); panel.clearPicked(); panel.actionNotice=""; Qt.callLater(panel.refreshListGeometry) }
                        TabButton {
                            id: pendingTab; objectName: "groupPendingTab"; text: "待处理 "+center.pendingCount; implicitHeight: 36; leftPadding: 0; rightPadding: 0
                            contentItem: Text { text: pendingTab.text; font.pixelSize: 12; font.weight: pendingTab.checked ? Font.DemiBold : Font.Normal; color: pendingTab.checked ? UiTheme.accent : UiTheme.muted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                            background: Rectangle {
                                color: pendingTab.hovered ? UiTheme.hover : "transparent"; radius: 4
                                border.width: pendingTab.visualFocus ? 1 : 0; border.color: UiTheme.focus
                                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; width: parent.width-16; height: 2; radius: 1; color: UiTheme.accentFill; visible: pendingTab.checked }
                            }
                        }
                        TabButton {
                            id: sentTab; objectName: "groupSentTab"; text: "已发送 "+center.sentCount; implicitHeight: 36; leftPadding: 0; rightPadding: 0
                            contentItem: Text { text: sentTab.text; font.pixelSize: 12; font.weight: sentTab.checked ? Font.DemiBold : Font.Normal; color: sentTab.checked ? UiTheme.accent : UiTheme.muted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                            background: Rectangle {
                                color: sentTab.hovered ? UiTheme.hover : "transparent"; radius: 4
                                border.width: sentTab.visualFocus ? 1 : 0; border.color: UiTheme.focus
                                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; width: parent.width-16; height: 2; radius: 1; color: UiTheme.accentFill; visible: sentTab.checked }
                            }
                        }
                    }
                }
                ListView {
                    id: namesTable; objectName: "groupNamesTable"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: panel.currentModel; clip: true; reuseItems: true; spacing: 0
                    boundsBehavior: panel.listMode ? Flickable.StopAtBounds : Flickable.DragAndOvershootBounds
                    onContentYChanged: panel.syncLists(namesTable,messageList)
                    onHeightChanged: Qt.callLater(panel.refreshListGeometry)
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    footer: Item {
                        id: addCell
                        width: namesTable.width
                        height: visible ? 44 : 0
                        visible: tabs.currentIndex===0 && center.selectedIndex>=0
                        Rectangle {
                            anchors.fill: parent; anchors.topMargin: 5; anchors.bottomMargin: 3
                            radius: 6; color: newName.activeFocus ? UiTheme.surface : UiTheme.input
                            border.color: newName.activeFocus ? UiTheme.accent : UiTheme.line
                        }
                        TextArea {
                            id: newName; objectName: "groupAddNameInput"
                            property bool submitting: false
                            property int draftListId: center.selected.id || 0
                            anchors.fill: parent; anchors.topMargin: 5; anchors.bottomMargin: 3
                            leftPadding: 12; rightPadding: 34; topPadding: 8; bottomPadding: 8; clip: true
                            font.pixelSize: 13; color: UiTheme.ink; placeholderTextColor: UiTheme.muted
                            selectionColor: UiTheme.accentFill; selectedTextColor: UiTheme.accentText
                            wrapMode: TextEdit.NoWrap; textFormat: TextEdit.PlainText; selectByMouse: true
                            placeholderText: "添加姓名"; enabled: !center.active; hoverEnabled: true
                            Accessible.name: "添加群发名单姓名"
                            Accessible.description: "单个姓名回车添加，多行姓名自动逐行加入"
                            ToolTip.visible: hovered
                            ToolTip.text: "单个姓名按回车添加；粘贴多行姓名自动逐行加入"
                            background: null
                            function submitInput() {
                                bulkNamesTimer.stop()
                                if (submitting || inputMethodComposing || !enabled || draftListId!==(center.selected.id || 0)) return
                                submitting=true
                                if (panel.addTypedName(text)>0) {
                                    text=""
                                    namesTable.forceLayout()
                                    namesTable.positionViewAtEnd()
                                    forceActiveFocus()
                                }
                                submitting=false
                            }
                            function queueMultiline() {
                                if (!submitting && !inputMethodComposing && /[\r\n]/.test(text)) bulkNamesTimer.restart()
                            }
                            onTextChanged: queueMultiline()
                            onInputMethodComposingChanged: if(!inputMethodComposing) queueMultiline()
                            onDraftListIdChanged: { bulkNamesTimer.stop(); text="" }
                            Keys.onPressed: function(event) {
                                if (event.key===Qt.Key_Return || event.key===Qt.Key_Enter) {
                                    if (!inputMethodComposing && !event.isAutoRepeat) submitInput()
                                    event.accepted=true
                                }
                            }
                            // 等本次粘贴结束后再改模型，避免在输入控件的 textChanged 中重入。
                            Timer { id: bulkNamesTimer; interval: 0; onTriggered: newName.submitInput() }
                        }
                        ToolButton {
                            id: addNamesButton; objectName: "groupAddNamesButton"
                            anchors.right: parent.right; anchors.rightMargin: 5; anchors.verticalCenter: newName.verticalCenter
                            width: 26; height: 26; enabled: newName.enabled; focusPolicy: Qt.NoFocus
                            Accessible.name: "添加填写的姓名"; ToolTip.visible: hovered; ToolTip.text: "添加姓名，也可按回车"
                            contentItem: Text { text: "+"; font.pixelSize: 20; font.weight: Font.Normal; color: addNamesButton.enabled ? UiTheme.accent : UiTheme.disabledText; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 4; color: addNamesButton.down ? UiTheme.pressed : addNamesButton.hovered ? UiTheme.hover : "transparent" }
                            onClicked: { if(newName.text.trim().length) newName.submitInput(); else newName.forceActiveFocus() }
                        }
                        MouseArea { anchors.fill: parent; acceptedButtons: Qt.NoButton; onWheel: function(wheel) { if(panel.listMode) panel.scrollRows(namesTable,wheel,false); else wheel.accepted=false } }
                    }
                    delegate: Rectangle {
                        id: nameCell
                        required property int index
                        required property string display
                        required property string recordKey
                        objectName: "groupName"+index
                        width: namesTable.width; height: 40; color: "transparent"
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: panel.contactPrefix+display
                        Accessible.description: "双击查看或编辑个人消息；Ctrl 或 Shift 可多选"
                        Rectangle {
                            anchors.fill: parent; anchors.topMargin: 2; anchors.bottomMargin: 2; radius: 6
                            color: panel.isPicked(nameCell.recordKey) ? UiTheme.selection : nameMouse.containsMouse ? UiTheme.hover : "transparent"
                            border.width: nameCell.activeFocus ? 1 : 0; border.color: UiTheme.focus
                        }
                        Rectangle {
                            anchors.left: parent.left; anchors.leftMargin: 2; anchors.verticalCenter: parent.verticalCenter
                            width: 2; height: 16; radius: 1; color: UiTheme.accent; visible: panel.isPicked(nameCell.recordKey)
                        }
                        Text {
                            objectName: "groupNameLabel"+nameCell.index
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                            text: panel.contactPrefix+nameCell.display; textFormat: Text.PlainText
                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: panel.isPicked(nameCell.recordKey) ? UiTheme.accent : UiTheme.ink; font.pixelSize: 14
                        }
                        // 保留表格式横线，缩进并降低视觉重量。
                        Rectangle { objectName: "groupNameSeparator"+nameCell.index; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.bottom: parent.bottom; height: 1; color: UiTheme.line; opacity: 0.45; visible: !panel.isPicked(nameCell.recordKey) }
                        MouseArea {
                            id: nameMouse
                            anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.LeftButton
                            onWheel: function(wheel) { if(panel.listMode) panel.scrollRows(namesTable,wheel,false); else wheel.accepted=false }
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
                    id: listNotice; objectName: "groupListNotice"
                    text: panel.actionNotice; visible: text.length>0
                    color: UiTheme.warning
                    font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                }
            }
        }
        UiPanel {
            id: templatePanel; objectName: "groupTemplatePanel"; Layout.fillWidth: true; Layout.fillHeight: true; padding: 10
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                ColumnLayout {
                    id: templateHeader; Layout.fillWidth: true; spacing: 6
                    Layout.preferredHeight: panel.sharedHeaderHeight
                    Layout.maximumHeight: Layout.preferredHeight
                    RowLayout {
                        Layout.fillWidth: true
                        Label { objectName: "groupTemplateTitle"; text: "消息模板"; font.bold: true; font.pixelSize: 17; Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                        ToolButton {
                            objectName: "groupToggleMessageView"; font.pixelSize: 12; implicitHeight: 28; leftPadding: 4; rightPadding: 4
                            text: panel.listMode ? (templatePanel.width<350 ? "聊天查看" : "切换为聊天查看") : (templatePanel.width<350 ? "表格查看" : "切换为表格查看")
                            Accessible.name: panel.listMode ? "切换为聊天查看" : "切换为表格查看"
                            onClicked: panel.setListMode(!panel.listMode)
                        }
                        UiButton { objectName: "groupResetDefaults"; text: "重载"; visible: defaults.dirty || (defaults.editingIndex>=0 && defaults.feedback.length>0); enabled: !center.active; implicitHeight: 28; onClicked: panel.loadDefaults(true) }
                        UiButton { objectName: "groupRetryDefaults"; text: panel.width<500 ? "重试" : "重试保存"; visible: defaults.dirty || (defaults.editingIndex>=0 && defaults.feedback.length>0); enabled: panel.canManage; implicitHeight: 28; onClicked: panel.saveDefaults() }
                        ToolButton {
                            text: "更多"; font.pixelSize: 12; enabled: panel.canManage; implicitHeight: 28
                            Accessible.name: "模板更多操作"; onClicked: templateMenu.popup()
                        }
                    }
                    Label {
                        objectName: "groupTemplateHint"
                        text: center.selectedIndex<0 ? "先新建或生成名单" : center.active ? "发送中，消息模板暂不可编辑" : "加入后自动保存 · 保留个人改动 · 预览后开始群发"
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12
                    }
                    Item { Layout.fillHeight: true }
                    Item {
                        Layout.fillWidth: true; Layout.preferredHeight: tabs.height; Layout.minimumHeight: tabs.height; Layout.maximumHeight: tabs.height
                        Flickable {
                            id: messageHeader; objectName: "groupMessageHeader"; anchors.fill: parent; visible: panel.listMode
                            contentWidth: panel.messageFieldCount*panel.messageColumnWidth; contentHeight: height
                            contentX: messageList.contentX; clip: true; interactive: false
                            Row {
                                Repeater {
                                    model: panel.messageFieldCount
                                    delegate: Rectangle {
                                        required property int index
                                        objectName: "groupMessageHeader"+index
                                        width: panel.messageColumnWidth; height: messageHeader.height; color: UiTheme.input
                                        enabled: center.selectedIndex>=0 && !center.active
                                        Accessible.role: Accessible.Button; Accessible.name: "配置消息"+(index+1)
                                        activeFocusOnTab: true
                                        Keys.onReturnPressed: templateDialog.open()
                                        Keys.onSpacePressed: templateDialog.open()
                                        Label { objectName: "groupMessageHeaderLabel"+parent.index; anchors.fill: parent; anchors.leftMargin: 12; verticalAlignment: Text.AlignVCenter; text: "消息"+(parent.index+1); color: UiTheme.ink; font.pixelSize: 13 }
                                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: UiTheme.line }
                                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: UiTheme.line }
                                        Rectangle { anchors.fill: parent; color: "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: UiTheme.focus }
                                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: templateDialog.open() }
                                    }
                                }
                            }
                        }
                    }
                }
                Item { id: chatHost; visible: !panel.listMode; Layout.fillWidth: true; Layout.fillHeight: true }
                MessageChatEditor {
                    id: defaults; objectName: "groupMessageChat"
                    parent: panel.listMode ? unifiedHost : chatHost
                    anchors.fill: parent
                    fileChooser: center; controlPrefix: "groupChat"; defaultTemplate: true; editable: panel.canManage
                    onCommitted: commitAccepted=panel.saveCommittedDefaults(false)
                    onEditCancelled: if(!dirty && panel.draftRevision!==center.contentRevision) panel.loadDefaults(true)
                }
                TableView {
                    id: messageList; objectName: "groupRecipientMessageList"; visible: panel.listMode
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0
                    model: tabs.currentIndex===0 ? center.pendingMessageModel : center.sentMessageModel
                    clip: true; reuseItems: true; rowSpacing: 0; columnSpacing: 0
                    boundsBehavior: Flickable.StopAtBounds
                    bottomMargin: namesTable.footerItem ? namesTable.footerItem.height : 0
                    rowHeightProvider: function(row) { return 40 }
                    columnWidthProvider: function(column) { return panel.messageColumnWidth }
                    onContentYChanged: panel.syncLists(messageList,namesTable)
                    onHeightChanged: Qt.callLater(panel.refreshListGeometry)
                    onWidthChanged: Qt.callLater(panel.refreshListGeometry)
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                    function positionViewAtBeginning() { cancelFlick(); contentY=originY }
                    function positionViewAtEnd() { cancelFlick(); contentY=originY+Math.max(0,contentHeight+bottomMargin-height) }
                    delegate: Rectangle {
                        id: messageCell
                        required property int row
                        required property int column
                        required property string display
                        required property string recordKey
                        property var rowData: { var revision=panel.rowsRevision; return panel.currentModel.get(row) }
                        readonly property string fullText: panel.cellText(rowData,column)
                        objectName: "groupMessageCell"+row+"_"+column
                        implicitWidth: panel.messageColumnWidth; implicitHeight: 40
                        color: panel.isPicked(recordKey) ? UiTheme.selection : messageMouse.containsMouse ? UiTheme.hover : "transparent"
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button; Accessible.name: (rowData.name || "")+"："+fullText
                        Accessible.description: "双击查看或编辑个人消息"
                        Keys.onReturnPressed: { panel.selectedRow=panel.currentModel.get(row); panel.openEditor() }
                        Keys.onEnterPressed: { panel.selectedRow=panel.currentModel.get(row); panel.openEditor() }
                        Text {
                            id: cellLabel; objectName: "groupMessageText"+messageCell.row+"_"+messageCell.column
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                            text: messageCell.fullText.replace(/[\r\n]+/g," "); textFormat: Text.PlainText; wrapMode: Text.NoWrap; elide: Text.ElideRight
                            font.pixelSize: 13; color: panel.isPicked(messageCell.recordKey) ? UiTheme.accent : UiTheme.ink; verticalAlignment: Text.AlignVCenter
                        }
                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: UiTheme.line }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: UiTheme.line; opacity: 0.65 }
                        Rectangle { anchors.fill: parent; color: "transparent"; border.width: messageCell.activeFocus ? 1 : 0; border.color: UiTheme.focus }
                        MouseArea {
                            id: messageMouse; anchors.fill: parent; hoverEnabled: true
                            onWheel: function(wheel) { panel.scrollRows(messageList,wheel,true) }
                            onEntered: if(cellLabel.truncated || messageCell.fullText.indexOf("\n")>=0) { closePreview.stop(); previewDelay.restart() }
                            onExited: { previewDelay.stop(); closePreview.restart() }
                            onClicked: function(mouse) { panel.selectedRow=panel.currentModel.get(messageCell.row); panel.pickIndex(messageCell.row,mouse.modifiers,messageCell.recordKey); messageCell.forceActiveFocus() }
                            onDoubleClicked: { messagePreview.close(); panel.selectedRow=panel.currentModel.get(messageCell.row); panel.openEditor() }
                        }
                        Timer { id: previewDelay; interval: 450; onTriggered: if(messageMouse.containsMouse) panel.showMessagePreview(messageCell) }
                    }
                }
                Item { visible: panel.listMode && listNotice.visible; Layout.fillWidth: true; Layout.preferredHeight: listNotice.height; Layout.minimumHeight: listNotice.height; Layout.maximumHeight: listNotice.height }
            }
        }
    }
    Timer { id: closePreview; interval: 200; onTriggered: if(!previewHover.hovered) messagePreview.close() }
    Popup {
        id: messagePreview; objectName: "groupMessagePreview"; parent: Overlay.overlay
        property string text: ""; property string heading: ""
        width: Math.min(parent.width-32,460); height: Math.min(parent.height-32,300)
        padding: 12; closePolicy: Popup.CloseOnEscape
        HoverHandler { id: previewHover; parent: messagePreview.contentItem; onHoveredChanged: if(hovered) closePreview.stop(); else closePreview.restart() }
        background: Rectangle { color: UiTheme.surface; border.color: UiTheme.line; radius: 6 }
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            Label { text: messagePreview.heading; font.pixelSize: 12; color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
            ScrollView {
                id: previewScroll; objectName: "groupMessagePreviewScroll"; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                TextArea { objectName: "groupMessagePreviewText"; width: previewScroll.availableWidth; text: messagePreview.text; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; readOnly: true; selectByMouse: true; color: UiTheme.ink; font.pixelSize: 14; background: null }
                MouseArea { parent: previewScroll; anchors.fill: parent; acceptedButtons: Qt.NoButton; onWheel: function(wheel) { panel.scrollRows(previewScroll.contentItem,wheel,false) } }
            }
        }
    }
    Dialog {
        id: templateDialog; objectName: "groupUnifiedTemplateDialog"; parent: Overlay.overlay
        anchors.centerIn: parent; modal: true; closePolicy: Popup.NoAutoClose; title: "统一配置消息模板"
        onOpened: messagePreview.close()
        width: Math.min(parent.width-32,760); height: Math.min(parent.height-32,650)
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            Label { text: "加入后自动保存 · 保留个人改动 · 预览后开始群发"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
            Item { id: unifiedHost; Layout.fillWidth: true; Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true; Item { Layout.fillWidth: true }
                UiButton { objectName: "groupCloseUnifiedTemplate"; text: "完成"; onClicked: if(panel.saveDefaults()) templateDialog.close() }
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
