import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "groupCenterPage"
    property var center: backend.groupCenter
    property bool loadingOptions: false
    property int renamePlanId: 0
    property string renamePlanText: ""
    property string renamePlanFeedback: ""
    property bool optionsDirty: recipientPanel.contactPrefix !== (center.selected.prefix || "")
        || Number(searchWait.text) !== center.selected.options.wait || Number(timeout.text) !== center.selected.options.timeout
        || Number(focusDelay.text) !== center.selected.options.focus_delay || Number(pasteDelay.text) !== center.selected.options.paste_delay
        || Number(gap.text) !== center.selected.options.interval || (match.currentIndex===1) !== center.selected.options.substring_mode
        || doSend.checked !== center.selected.options.confirm_send || verifyContact.checked !== center.selected.options.verify_contact
        || singleSend.checked !== center.selected.options.single_send
    function loadOptions() {
        settingsTimer.stop()
        loadingOptions=true
        var s=center.selected
        settingsPanel.listId=s.id || 0
        recipientPanel.contactPrefix=s.prefix || ""
        var o=s.options
        searchWait.text=String(o.wait); timeout.text=String(o.timeout)
        focusDelay.text=String(o.focus_delay); pasteDelay.text=String(o.paste_delay); gap.text=String(o.interval)
        match.currentIndex=o.substring_mode ? 1 : 0
        doSend.checked=o.confirm_send; verifyContact.checked=o.verify_contact; singleSend.checked=o.single_send
        loadingOptions=false
    }
    function scheduleSave() {
        if (!loadingOptions && !center.active && settingsPanel.listId === (center.selected.id || 0) && center.selectedIndex >= 0)
            settingsTimer.restart()
    }
    function saveSettings() {
        if (!recipientPanel.saveDefaults()) return false
        return saveOptions()
    }
    function saveOptions() {
        settingsTimer.stop()
        if (loadingOptions || !optionsDirty) return true
        if (center.active || settingsPanel.listId !== (center.selected.id || 0) || center.selectedIndex < 0) return false
        return center.saveOptions(settingsPanel.listId,recipientPanel.contactPrefix,{wait:Number(searchWait.text),timeout:Number(timeout.text),focus_delay:Number(focusDelay.text),paste_delay:Number(pasteDelay.text),interval:Number(gap.text),substring_mode:match.currentIndex===1,verify_contact:verifyContact.checked,single_send:singleSend.checked,confirm_send:doSend.checked})
    }
    Timer { id: settingsTimer; interval: 600; repeat: false; onTriggered: page.saveOptions() }
    Connections {
        target: center
        function onSelectionChanged() {
            if(settingsPanel.listId !== (center.selected.id || 0)) page.loadOptions()
        }
    }
    Component.onCompleted: loadOptions()
    function previewMessages() {
        if (!saveSettings()) return
        // 只提醒，不强制：前缀为空时确认后再继续预览。
        if (!recipientPanel.contactPrefix.trim()) { prefixReminder.open(); return }
        openPreview()
    }
    function openPreview() {
        if(center.prepare(center.selected.prefix || "",center.selected.options)) {
            acceptRisk.checked=false
            previewList.currentIndex=0
            previewDialog.open()
        }
    }
    function selectList(index) {
        cancelPlanRename()
        if (saveSettings()) center.selectList(index)
        listSelector.currentIndex=Qt.binding(function() { return center.selectedIndex })
    }
    function cancelPlanRename() {
        renamePlanId=0; renamePlanText=""; renamePlanFeedback=""
    }
    function focusPlanRename(selectText) {
        var index=center.lists.findIndex(function(plan) { return plan.id===page.renamePlanId })
        if(index<0 || !listSelector.popup.visible) return
        var view=listSelector.popup.contentItem
        view.forceLayout()
        view.positionViewAtIndex(index,ListView.Contain)
        Qt.callLater(function() {
            view.forceLayout()
            var option=view.itemAtIndex(index)
            if(option && option.renaming) option.focusRename(selectText)
        })
    }
    function beginPlanRename(listId,title) {
        renamePlanText=title; renamePlanFeedback=""; renamePlanId=listId
        listSelector.popup.open()
        Qt.callLater(function() { page.focusPlanRename(true) })
    }
    function commitPlanRename(text) {
        if(!renamePlanId) return
        renamePlanText=text
        if(center.renameList(renamePlanId,text)) {
            cancelPlanRename()
            listSelector.forceActiveFocus()
        } else {
            renamePlanFeedback=center.status
            focusPlanRename(false)
        }
    }
    function openPlanMenu(plan,anchor,x,y) {
        if(center.active || !plan || !plan.id) return
        var point=anchor.mapToItem(page,x,y)
        cancelPlanRename()
        planMenu.listId=plan.id; planMenu.listTitle=plan.title
        // Move focus into the list before the menu takes it, so ComboBox keeps its popup open.
        if(listSelector.popup.visible) listSelector.popup.contentItem.forceActiveFocus()
        planMenu.x=point.x; planMenu.y=point.y
        planMenu.open()
    }
    Connections {
        target: listSelector.popup
        function onOpened() { page.focusPlanRename(true) }
        function onClosed() { page.cancelPlanRename(); planMenu.close() }
    }
    Connections {
        target: center
        function onListsChanged() {
            if(page.renamePlanId) Qt.callLater(function() { page.focusPlanRename(false) })
        }
        function onActivityChanged() { if(center.active) listSelector.popup.close() }
    }
    onVisibleChanged: if(!visible) { listSelector.popup.close(); planMenu.close() }
    ColumnLayout {
        anchors.fill: parent; spacing: page.height<600 ? 6 : 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "群发中心"; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
            Label { text: "配置默认消息 → 核对预览 → 开始发送"; visible: page.width>900; color: UiTheme.muted }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            RowLayout {
                // 方案管理收进下拉框右键菜单，名单级操作统一右对齐。
                Layout.fillWidth: true; spacing: 6
                UiComboBox {
                    id: listSelector; objectName: "groupListSelector"; Layout.fillWidth: true
                    model: center.lists; textRole: "label"; currentIndex: center.selectedIndex
                    displayText: currentIndex<0 ? "暂无名单，请从催办生成或新建自定义名单" : currentText
                    enabled: !center.active; onActivated: page.selectList(currentIndex)
                    popup.objectName: "groupPlanPopup"
                    popup.closePolicy: planMenu.visible ? Popup.NoAutoClose
                        : page.renamePlanId ? Popup.CloseOnPressOutsideParent
                        : Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                    Accessible.name: "选择群发方案"; Accessible.description: "右键重命名或删除方案"
                    ToolTip.visible: hovered && !popup.visible; ToolTip.text: "右键重命名或删除；展开后可右键任一方案"
                    MouseArea {
                        anchors.fill: parent; acceptedButtons: Qt.RightButton
                        onClicked: function(mouse) { page.openPlanMenu(center.selected,listSelector,mouse.x,mouse.y) }
                    }
                    Keys.onPressed: function(event) {
                        if(event.key===Qt.Key_Menu || (event.key===Qt.Key_F10 && event.modifiers & Qt.ShiftModifier)) {
                            page.openPlanMenu(center.selected,listSelector,0,listSelector.height); event.accepted=true
                        }
                    }
                    delegate: ItemDelegate {
                        id: planOption; required property int index
                        property var plan: center.lists[index]
                        property bool renaming: !!plan && plan.id===page.renamePlanId
                        function focusRename(selectText) {
                            planTitleInput.forceActiveFocus()
                            if(selectText) planTitleInput.selectAll()
                        }
                        objectName: "groupPlanOption"+index
                        width: ListView.view ? ListView.view.width : listSelector.width
                        height: Math.max(36,implicitContentHeight+topPadding+bottomPadding)
                        topPadding: 2; bottomPadding: 2; leftPadding: 6; rightPadding: 6
                        text: listSelector.textAt(index); font: listSelector.font; hoverEnabled: page.renamePlanId===0
                        highlighted: listSelector.highlightedIndex===index
                        contentItem: ColumnLayout {
                            spacing: 3
                            Text {
                                id: planLabel; visible: !planOption.renaming; Layout.fillWidth: true
                                text: planOption.text; font: listSelector.font; color: UiTheme.ink
                                elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                            }
                            UiTextField {
                                id: planTitleInput; objectName: planOption.renaming ? "groupRenameInput" : ""
                                visible: planOption.renaming; Layout.fillWidth: true; Layout.preferredHeight: 30
                                text: page.renamePlanText; selectByMouse: true
                                property bool acceptOnRelease: false
                                Accessible.name: "群发方案名称"; Accessible.description: "回车保存，Esc 取消"
                                onTextChanged: if(planOption.renaming) page.renamePlanText=text
                                Keys.priority: Keys.BeforeItem
                                Keys.onPressed: function(event) {
                                    if(event.key===Qt.Key_Return || event.key===Qt.Key_Enter) {
                                        event.accepted=true
                                        if(!event.isAutoRepeat) acceptOnRelease=!inputMethodComposing
                                    } else if(event.key===Qt.Key_Escape) {
                                        event.accepted=true
                                    }
                                }
                                // Finish on release so the ComboBox cannot reuse the editor's key to select/close.
                                Keys.onReleased: function(event) {
                                    if(event.key===Qt.Key_Return || event.key===Qt.Key_Enter) {
                                        event.accepted=true
                                        if(event.isAutoRepeat) return
                                        var accept=acceptOnRelease; acceptOnRelease=false
                                        if(accept && !inputMethodComposing) page.commitPlanRename(text)
                                    } else if(event.key===Qt.Key_Escape) {
                                        event.accepted=true
                                        if(!event.isAutoRepeat) { page.cancelPlanRename(); listSelector.forceActiveFocus() }
                                    }
                                }
                                ToolTip.visible: hovered; ToolTip.text: "回车保存 · Esc 取消"
                            }
                            Label {
                                objectName: planOption.renaming ? "groupRenameFeedback" : ""
                                visible: planOption.renaming && page.renamePlanFeedback.length>0
                                Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12
                                text: page.renamePlanFeedback; color: UiTheme.warning
                            }
                        }
                        background: Rectangle {
                            radius: 4; color: planOption.highlighted || planOption.hovered ? UiTheme.selection : "transparent"
                            border.width: planOption.visualFocus ? 2 : 0; border.color: UiTheme.accent
                        }
                        ToolTip.visible: !renaming && hovered && planLabel.truncated; ToolTip.text: text
                        MouseArea {
                            anchors.fill: parent; acceptedButtons: Qt.RightButton; enabled: !planOption.renaming
                            onClicked: function(mouse) { page.openPlanMenu(center.lists[planOption.index],planOption,mouse.x,mouse.y) }
                        }
                    }
                }
            }
            UiButton { objectName: "groupCopyList"; text: page.width<650 ? "复制名单" : "复制为新名单"; enabled: !center.active && center.selectedIndex>=0; onClicked: if(page.saveSettings()) copyDialog.open() }
            UiButton { objectName: "groupCreateList"; text: "新建群发"; enabled: !center.active; onClicked: if(page.saveSettings()) customDialog.open() }
        }
        RowLayout {
            Layout.fillWidth: true; visible: backend.aiCampaign.listFailureCount>0 || backend.aiCampaign.busy
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: backend.aiCampaign.busy ? backend.aiCampaign.notice : "AI 话术留空 " + backend.aiCampaign.listFailureCount + " 人，可双击姓名补写或重试。"; color: UiTheme.warning }
            UiButton { objectName: "groupRetryAiFailures"; text: "重试失败项"; enabled: !backend.aiCampaign.busy && !center.active && backend.aiCampaign.listFailureCount>0; onClicked: if(page.saveSettings()) backend.aiCampaign.retryList(center.selected.id) }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
            RecipientMessages {
                id: recipientPanel; Layout.fillWidth: true; Layout.fillHeight: true; center: page.center
                onPrefixEdited: page.scheduleSave()
                onResolveRequested: function(recipientId,wasSent) {
                    resolveDialog.listId=center.selected.id; resolveDialog.recipientId=recipientId
                    resolveDialog.wasSent=wasSent; resolveDialog.open()
                }
            }
            UiPanel {
                id: settingsPanel; objectName: "groupSettingsPanel"; property int listId: 0
                Layout.preferredWidth: page.width<750 ? 170 : 238
                Layout.minimumWidth: Layout.preferredWidth; Layout.maximumWidth: Layout.preferredWidth
                Layout.fillHeight: true; padding: 10
                ScrollView {
                    id: optionsScroll; anchors.fill: parent; contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: optionsScroll.availableWidth; enabled: !center.active && center.selectedIndex>=0; spacing: 6
                        Label { text: "发送配置"; font.bold: true; font.pixelSize: 15 }
                        Label { text: "当前名单自动保存"; color: UiTheme.muted; font.pixelSize: 11; Layout.fillWidth: true }
                        Label { text: "联系人匹配"; font.pixelSize: 12 }
                        UiComboBox { id: match; model: ["完整匹配（推荐）","包含匹配"]; Layout.fillWidth: true; onActivated: page.scheduleSave() }
                        CheckBox { id: verifyContact; text: "使用浮窗验证联系人"; font.pixelSize: 12; Layout.fillWidth: true; onToggled: page.scheduleSave() }
                        CheckBox { id: doSend; objectName: "groupConfirmSend"; text: "粘贴后回车发送"; font.pixelSize: 12; Layout.fillWidth: true; onToggled: page.scheduleSave() }
                        CheckBox {
                            id: singleSend; objectName: "groupSingleSend"; text: "每条消息单独发送"
                            font.pixelSize: 12; Layout.fillWidth: true; enabled: doSend.checked; opacity: enabled ? 1 : 0.45
                            onToggled: page.scheduleSave()
                        }
                        Label { text: doSend.checked ? "预览确认后才开始发送" : "仅粘贴，不发送"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
                        CheckBox { id: advanced; objectName: "groupAdvancedOptions"; text: "高级等待设置"; font.pixelSize: 12; checked: false }
                        ColumnLayout {
                            visible: advanced.checked; Layout.fillWidth: true; spacing: 5
                            Label { text: "搜索等待（秒）"; font.pixelSize: 12 }
                            UiTextField { id: searchWait; Layout.fillWidth: true; onTextChanged: page.scheduleSave() }
                            Label { text: "浮窗超时（秒）"; font.pixelSize: 12 }
                            UiTextField { id: timeout; Layout.fillWidth: true; onTextChanged: page.scheduleSave() }
                            Label { text: "输入前等待（秒）"; font.pixelSize: 12 }
                            UiTextField { id: focusDelay; Layout.fillWidth: true; onTextChanged: page.scheduleSave() }
                            Label { text: "粘贴后等待（秒）"; font.pixelSize: 12 }
                            UiTextField { id: pasteDelay; objectName: "groupPasteDelay"; Layout.fillWidth: true; onTextChanged: page.scheduleSave() }
                            Label { text: "联系人间隔（秒）"; font.pixelSize: 12 }
                            UiTextField { id: gap; Layout.fillWidth: true; onTextChanged: page.scheduleSave() }
                            UiButton { objectName: "groupResetWaits"; text: "恢复默认等待"; Layout.fillWidth: true; onClicked: { searchWait.text="0.5"; timeout.text="3"; focusDelay.text="0.5"; pasteDelay.text="0.5"; gap.text="0" } }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: center.status; color: UiTheme.warning; Layout.fillWidth: true; elide: Text.ElideRight; ToolTip.visible: statusHover.hovered; ToolTip.text: text; HoverHandler { id: statusHover } }
            UiButton { visible: center.active; text: center.pauseRequested ? "等待暂停…" : "暂停（F11）"; enabled: !center.pauseRequested && !center.isPaused; onClicked: center.pause() }
            UiButton { visible: center.active; text: "继续"; enabled: center.isPaused; onClicked: center.resume() }
            UiButton { visible: center.active; text: "结束本轮"; onClicked: center.stop() }
            UiButton { objectName: "groupPreviewButton"; visible: !center.active; text: "预览并发送"; highlighted: true; enabled: !center.active && center.selectedIndex>=0 && center.editableCount>0; onClicked: page.previewMessages() }
        }
    }
    Menu {
        id: planMenu; objectName: "groupPlanMenu"; parent: page
        popupType: Popup.Item
        property int listId: 0
        property string listTitle: ""
        onClosed: if(page.renamePlanId) page.focusPlanRename(true)
        MenuItem {
            objectName: "groupRenamePlanAction"; text: "重命名"; enabled: !center.active
            onTriggered: if(page.saveSettings()) page.beginPlanRename(planMenu.listId,planMenu.listTitle)
        }
        MenuItem {
            objectName: "groupDeletePlanAction"; text: "删除…"; enabled: !center.active
            onTriggered: if(page.saveSettings()) { deleteDialog.listId=planMenu.listId; deleteDialog.listTitle=planMenu.listTitle; listSelector.popup.close(); deleteDialog.open() }
        }
    }
    Dialog {
        id: deleteDialog; objectName: "groupDeletePlanDialog"; anchors.centerIn: parent; modal: true; title: "删除群发方案"
        property int listId: 0
        property string listTitle: ""
        property string feedback: ""
        onOpened: feedback=""
        width: Math.min(page.width-30,480)
        ColumnLayout {
            anchors.fill: parent
            Label { text: "删除群发方案「"+deleteDialog.listTitle+"」？"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "该方案的人员名单、消息和本地发送记录将一并删除，无法撤销。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            Label { visible: deleteDialog.feedback.length>0; text: deleteDialog.feedback; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "cancelDeletePlan"; text: "取消"; onClicked: deleteDialog.reject() }
                Item { Layout.fillWidth: true }
                UiButton { objectName: "confirmDeletePlan"; text: "删除方案"; highlighted: true; enabled: !center.active; onClicked: { if(center.deleteList(deleteDialog.listId)) deleteDialog.close(); else deleteDialog.feedback=center.status } }
            }
        }
    }
    Dialog {
        id: copyDialog; objectName: "groupCopyBatchDialog"; anchors.centerIn: parent; modal: true; title: "复制批次名单并新建"
        width: Math.min(page.width-30,520)
        onOpened: { copyTitle.text=(center.selected.title || "群发名单")+" - 副本"; copyMessages.checked=true }
        ColumnLayout {
            anchors.fill: parent
            Label { text: "来源：" + (center.selected.title || ""); wrapMode: Text.Wrap; Layout.fillWidth: true }
            UiTextField { id: copyTitle; objectName: "groupCopyTitleInput"; placeholderText: "新批次名称"; Layout.fillWidth: true }
            CheckBox { id: copyMessages; text: "同时复制消息内容（按原始模板，以当前画像重新替换变量）"; checked: true; Layout.fillWidth: true }
            Label { text: "人员名单会复制为新批次，所有人重置为待发送；原批次及其发送记录不变。无法匹配学员或变量时会阻止创建。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            Label { text: center.status; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "confirmCopyBatch"; text: "复制并新建"; highlighted: true; enabled: !center.active; onClicked: if(center.copyList(copyTitle.text,copyMessages.checked)) copyDialog.close() }
                UiButton { text: "取消"; onClicked: copyDialog.close() }
            }
        }
    }
    Dialog {
        id: customDialog; objectName: "customGroupDialog"; anchors.centerIn: parent; modal: true; title: "新建群发方案"
        width: Math.min(page.width-30,520)
        ColumnLayout {
            anchors.fill: parent
            UiTextField { id: customTitle; objectName: "groupCustomTitle"; placeholderText: "群发方案名称"; Layout.fillWidth: true }
            Label {
                text: "只创建空的群发方案；创建后在左侧「群发名单」逐个填写姓名（也可用 Ctrl+V 粘贴多个），再到「消息模板」配置消息。"
                wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted
            }
            Label { text: center.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton {
                    objectName: "createGroupPlan"; text: "创建方案"; highlighted: true
                    onClicked: if(center.createEmptyList(customTitle.text)) { customDialog.close(); customTitle.text="" }
                }
                UiButton { text: "取消"; onClicked: customDialog.close() }
            }
        }
    }
    Dialog {
        id: prefixReminder; objectName: "groupEmptyPrefixReminder"; anchors.centerIn: parent; modal: true; title: "联系人前缀为空"
        width: Math.min(page.width-30,520)
        ColumnLayout {
            anchors.fill: parent
            Label { text: "当前名单的联系人前缀为空，将直接使用名单中的姓名作为企业微信联系人备注。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "若企业微信备注带有班级等前缀，或名单中存在同名联系人，可能匹配到错误的人。这里只提醒、不强制填写：可以返回补充前缀，也可以继续预览逐人核对。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.warning }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                UiButton { objectName: "groupEmptyPrefixBack"; text: "返回填写"; highlighted: true; onClicked: prefixReminder.close() }
                UiButton { objectName: "groupEmptyPrefixContinue"; text: "继续预览"; onClicked: { prefixReminder.close(); page.openPreview() } }
            }
        }
    }
    Dialog {
        id: previewDialog; objectName: "groupSendPreview"; anchors.centerIn: parent; modal: true; title: center.selected.options.confirm_send ? "确认真实群发" : "确认仅粘贴（不发送）"
        width: Math.min(page.width-24,960); height: Math.min(page.height-24,660)
        property var currentRecipient: previewList.currentIndex>=0 && previewList.currentIndex<center.preview.length ? center.preview[previewList.currentIndex] : ({})
        ColumnLayout {
            anchors.fill: parent
            Label { text: "本轮处理 " + center.preview.length + " 人 · 其余 " + Math.max(0,center.pendingCount+center.sentCount-center.preview.length) + " 人跳过（已发送、待核实或不符合条件）"; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { objectName: "groupPreviewSummary"; text: (center.selected.options.confirm_send ? "回车发送" : "仅粘贴，不发送") + " · " + (center.selected.options.confirm_send && center.selected.options.single_send ? "按下列顺序逐条处理" : "按下列顺序粘贴"+(center.selected.options.confirm_send ? "后统一发送" : "")) + " · " + (center.selected.options.substring_mode ? "包含匹配" : "完整匹配") + " · " + (center.selected.options.verify_contact ? "验证联系人" : "不验证联系人"); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                UiPanel {
                    Layout.preferredWidth: Math.min(210,previewDialog.width*0.3); Layout.fillHeight: true
                    ListView {
                        id: previewList; objectName: "groupPreviewRecipients"; anchors.fill: parent; clip: true; spacing: 3
                        model: center.preview; ScrollBar.vertical: ScrollBar {}
                        onCurrentIndexChanged: if(previewContent.contentItem) previewContent.contentItem.contentY=0
                        delegate: ItemDelegate {
                            required property var modelData
                            required property int index
                            width: previewList.width; highlighted: previewList.currentIndex===index
                            text: modelData.contact || modelData.name
                            onClicked: previewList.currentIndex=index
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Label { objectName: "groupPreviewContact"; text: "联系人："+(previewDialog.currentRecipient.contact || ""); font.bold: true; textFormat: Text.PlainText; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    ScrollView {
                        id: previewContent; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                        ColumnLayout {
                            width: previewContent.availableWidth; spacing: 10
                            Repeater {
                                model: previewDialog.currentRecipient.content || []
                                UiPanel {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        anchors.fill: parent
                                        Label { text: "消息 "+(index+1)+(modelData.type==="file" ? " · 文件" : " · 文字"); color: UiTheme.muted }
                                        TextArea { visible: modelData.type!=="file"; text: modelData.text || ""; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; Layout.fillWidth: true; background: null }
                                        MessageAttachment {
                                            objectName: "groupPreviewAttachment"+index
                                            visible: modelData.type==="file"
                                            fileChooser: center; path: modelData.type==="file" ? modelData.path : ""
                                            availableWidth: parent.width
                                            Layout.preferredWidth: implicitWidth; Layout.preferredHeight: implicitHeight
                                            Layout.maximumWidth: parent.width
                                        }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        UiButton { text: "上一人"; enabled: previewList.currentIndex>0; onClicked: previewList.currentIndex-- }
                        Label { text: (previewList.currentIndex+1)+" / "+center.preview.length; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                        UiButton { objectName: "groupPreviewNext"; text: "下一人"; enabled: previewList.currentIndex<center.preview.length-1; onClicked: previewList.currentIndex++ }
                    }
                }
            }
            Label { text: "请登录企业微信并保持空输入框。处理期间不要操作电脑；F11 会在当前联系人完成后暂停。单个联系人失败不会中止本轮：未粘贴的记为「未发送失败」并留在待处理，粘贴后异常记为「结果待确认」，需核对后重试。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            CheckBox { id: acceptRisk; objectName: "groupAcceptRisk"; visible: center.selected.options.substring_mode || !center.selected.options.verify_contact; text: "已核对联系人，了解包含匹配或不验证联系人可能导致误发"; Layout.fillWidth: true }
            Label { text: center.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "groupPreviewBack"; text: "返回编辑"; onClicked: previewDialog.close() }
                UiButton { objectName: "groupPreviewEditPerson"; text: "修改此人消息"; enabled: !center.active && !!previewDialog.currentRecipient.student_id; onClicked: { var recipientId=Number(previewDialog.currentRecipient.student_id); previewDialog.close(); recipientPanel.editRecipient(recipientId) } }
                Item { Layout.fillWidth: true }
                UiButton { objectName: "groupStartButton"; text: (center.selected.options.confirm_send ? "开始发送 · " : "开始粘贴 · ")+center.preview.length+" 人"; highlighted: true; enabled: !center.active && center.preview.length>0 && ((!center.selected.options.substring_mode && center.selected.options.verify_contact) || acceptRisk.checked); onClicked: { if(center.start()) previewDialog.close() } }
            }
        }
    }
    Dialog {
        id: resolveDialog; anchors.centerIn: parent; modal: true; title: "人工核实"; standardButtons: Dialog.Ok | Dialog.Cancel
        property int listId: 0
        property int recipientId: 0
        property bool wasSent: false
        Label { text: resolveDialog.wasSent ? "请先核实聊天记录。确认已发送后，不会再次发送。" : "请先确认消息确实未发送，并清理输入框中的草稿。\n确认后可再次预览发送，错误确认可能造成重复发送。" }
        onAccepted: center.resolve(listId,recipientId,wasSent)
    }
}
