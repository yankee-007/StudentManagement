import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: card
    required property var service
    required property var workflow
    property string loadedKey: ""
    property bool loadingDraft: false
    property var draftEditor: null
    property string saveState: "修改后自动保存"
    property bool hasStudent: !!service.selected.student_id
    property bool showContactAction: true
    property bool showName: true
    property bool compact: false
    property var fields: []
    spacing: 8

    function refreshFields() {
        var next = workflow.managedFields.filter(function(field) { return field.show_column })
            .map(function(field) { return {key:field.field_id,label:field.name} })
        if (JSON.stringify(next) !== JSON.stringify(fields)) fields = next
    }

    function loadSelection(force) {
        var key = service.editorKey || ""
        if (loadedKey === key && !force && draftEditor && draftEditor.inputMethodComposing) return
        loadingDraft = true
        if (loadedKey !== key && draftEditor && draftEditor.activeFocus) Qt.inputMethod.reset()
        if (loadedKey !== key) saveState = service.canEdit ? "修改后自动保存" : "历史批次只读"
        loadedKey = key
        var value = workflow.feedbackValue(key)
        if (draftEditor && draftEditor.text !== value) draftEditor.text = value
        loadingDraft = false
    }
    Component.onCompleted: { refreshFields(); loadSelection(true) }
    Connections {
        target: card.workflow
        function onChanged() { card.refreshFields() }
        function onFeedbackSaved(key, saved) {
            if (key === card.loadedKey) card.saveState = saved ? "已自动保存" : "保存失败，内容已保留，请重新尝试"
        }
    }
    Connections {
        target: card.service
        function onSelectionChanged() { card.loadSelection(false) }
        function onChanged() { card.loadSelection(false) }
    }
    Label {
        visible: card.showName && !(card.showContactAction && card.hasStudent && card.service.canEdit)
        text: card.service.selected.name || (card.hasStudent ? "姓名待补全" : "选择学员")
        font.pixelSize: card.compact ? 16 : 21; font.bold: true; color: UiTheme.ink
    }
    CampaignContactAction {
        visible: card.showContactAction && card.hasStudent && card.service.canEdit
        Layout.fillWidth: true; service: card.service
    }
    ScrollView {
        id: details; Layout.fillWidth: true; Layout.fillHeight: true
        contentWidth: availableWidth; clip: true
        ColumnLayout {
            width: details.availableWidth - (card.compact ? 4 : 12); spacing: card.compact ? 6 : 10
            enabled: card.hasStudent
            Repeater {
                model: card.fields.filter(function(field) { return field.key !== "name" })
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: card.compact ? 4 : 6
                    Label {
                        visible: modelData.key !== "feedback" && modelData.key !== "exemption_text" && modelData.key !== "followup_status"
                        text: modelData.label + "：" + (card.service.selected[modelData.key] || "—")
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink; font.pixelSize: card.compact ? 11 : 12
                    }
                    ColumnLayout {
                        visible: modelData.key === "feedback"
                        Layout.fillWidth: true; spacing: 6
                        Label { text: "本次反馈"; font.bold: true; color: UiTheme.ink }
                        RowLayout {
                            id: feedbackRow
                            Layout.fillWidth: true; spacing: 4
                            UiTextField {
                                id: draft; objectName: modelData.key === "feedback" ? (card.service === card.workflow ? "feedbackDraft" : "floatingFeedbackDraft") : ""
                                Layout.fillWidth: true
                                implicitHeight: card.compact ? 27 : 32
                                text: ""
                                padding: card.compact ? 5 : 7
                                font.pixelSize: card.compact ? 11 : 13
                                selectByMouse: true
                                readOnly: !card.service.canEdit || !card.hasStudent || !card.service.selected.name || !!card.service.selected.is_placeholder
                                placeholderText: card.service.canEdit ? "填写反馈" : "暂无反馈"
                                property var menu: shortcutsMenu
                                Component.onCompleted: if (modelData.key === "feedback") { card.draftEditor = draft; card.loadSelection(true) }
                                Component.onDestruction: if (card.draftEditor === draft) card.draftEditor = null
                                function save() {
                                    if (!card.loadingDraft && !readOnly && activeFocus && !inputMethodComposing)
                                        card.saveState = card.service.queueFeedbackForSelection(card.loadedKey,text) ? "等待自动保存…" : "未保存，请检查当前学员和批次"
                                }
                                onTextChanged: save()
                                onInputMethodComposingChanged: save()
                                onTextEdited: shortcutsMenu.close()
                                onActiveFocusChanged: if (!activeFocus && !card.loadingDraft) card.workflow.flushFeedback()
                                onAccepted: card.workflow.flushFeedback()
                                background: Rectangle { color: "#f9fafb"; radius: 6; border.color: draft.activeFocus ? "#809aff" : UiTheme.line }
                                TapHandler {
                                    enabled: !draft.readOnly
                                    onTapped: { draft.forceActiveFocus(); shortcutsMenu.open() }
                                }
                            }
                            Menu {
                                id: shortcutsMenu
                                objectName: modelData.key === "feedback" ? (card.service === card.workflow ? "feedbackShortcutMenu" : "floatingFeedbackShortcutMenu") : ""
                                parent: Overlay.overlay
                                focus: false; modal: false
                                width: Math.min(feedbackRow.width, parent ? parent.width - 16 : feedbackRow.width)
                                // Focus can scroll the editor after the menu opens.
                                // Keep the popup attached to the current editor position.
                                property point editorPoint: Qt.point(0, 0)
                                function positionAtEditor() { editorPoint = feedbackRow.mapToItem(parent, 0, 0) }
                                property real bottomSpace: Math.max(0, parent.height - editorPoint.y - feedbackRow.height - 12)
                                property real availableSpace: Math.max(bottomSpace, editorPoint.y - 12)
                                property string capturedKey: ""
                                height: Math.min(implicitHeight, availableSpace)
                                x: Math.max(8, Math.min(editorPoint.x, parent.width - width - 8))
                                y: bottomSpace >= height ? editorPoint.y + feedbackRow.height + 4 : editorPoint.y - 4 - height
                                onAboutToShow: {
                                    capturedKey = card.loadedKey
                                    positionAtEditor()
                                }
                                onOpened: positionAtEditor()
                                Connections {
                                    target: details.contentItem
                                    function onContentYChanged() { if (shortcutsMenu.visible) Qt.callLater(shortcutsMenu.positionAtEditor) }
                                }
                                Instantiator {
                                    model: modelData.key === "feedback" ? card.workflow.feedbackShortcuts : []
                                    delegate: MenuItem {
                                        required property string modelData
                                        required property int index
                                        objectName: "feedbackShortcutOption" + index
                                        text: modelData
                                        onTriggered: {
                                            shortcutsMenu.close()
                                            if (draft.readOnly || shortcutsMenu.capturedKey !== card.loadedKey || card.loadedKey !== card.service.editorKey) return
                                            card.loadingDraft = true
                                            draft.text = draft.text.length ? draft.text + "；" + modelData : modelData
                                            card.loadingDraft = false
                                            card.saveState = card.service.queueFeedbackForSelection(card.loadedKey, draft.text) ? "等待自动保存…" : "未保存，请检查当前学员和批次"
                                            draft.forceActiveFocus(); draft.cursorPosition = draft.text.length
                                        }
                                    }
                                    onObjectAdded: function(index, object) { shortcutsMenu.insertItem(index, object) }
                                    onObjectRemoved: function(index, object) { shortcutsMenu.removeItem(object) }
                                }
                                MenuSeparator {}
                                MenuItem {
                                    objectName: "addFeedbackShortcutItem"
                                    text: "添加选项…"
                                    onTriggered: {
                                        shortcutsMenu.close()
                                        if (shortcutsMenu.capturedKey === card.loadedKey && card.loadedKey === card.service.editorKey) shortcutDialog.open()
                                    }
                                }
                            }
                        }
                        Label { text: card.saveState; font.pixelSize: 12; color: card.saveState.indexOf("失败") >= 0 ? "#b42318" : UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Label { text: card.service.canEdit ? "有内容即计为已回复；清空后恢复待反馈" : "历史反馈仅供查看"; font.pixelSize: 12; color: "#98a2b3"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        CheckBox { id: historyToggle; text: "查看以往反馈（含迁移前记录）" }
                        TextArea {
                            visible: historyToggle.checked; text: historyToggle.checked ? card.service.previousFeedback : ""
                            readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; Layout.fillWidth: true; font.pixelSize: 12
                        }
                    }
                    RowLayout {
                        visible: modelData.key === "followup_status"
                        Label { text: "可跟进状态："; color: UiTheme.ink }
                        UiComboBox {
                            objectName: modelData.key === "followup_status" ? (card.service === card.workflow ? "followupStatusSelector" : "floatingFollowupStatusSelector") : ""
                            model: ["否", "是"]
                            currentIndex: card.service.selected.followup_status === "是" ? 1 : 0
                            enabled: card.hasStudent && !!card.service.selected.name && !card.service.selected.is_placeholder && card.workflow.batchIndex >= 0
                            Accessible.name: "可跟进状态"
                            Layout.preferredWidth: 90
                            Layout.minimumWidth: 72
                            onActivated: card.service.setFollowupStatusForSelection(card.loadedKey, currentText)
                        }
                    }
                    ColumnLayout {
                        visible: modelData.key === "exemption_text"
                        Layout.fillWidth: true; spacing: 6
                        Label { text: "免催日期：" + (card.service.selected.exemption_text || "无"); Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                        Label { text: card.service.leaveNote; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12; color: UiTheme.muted }
                        RowLayout {
                            UiButton { text: "设置免催日期"; enabled: card.service.canSetExemption && card.hasStudent; onClicked: card.service.setLeave() }
                            UiButton { text: "清除免催"; enabled: card.service.canSetExemption && card.hasStudent; onClicked: card.service.clearLeave() }
                        }
                    }
                }
            }
        }
    }
    Dialog {
        id: shortcutDialog; objectName: "feedbackShortcutDialog"
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.max(220, Math.min(320, card.width))
        modal: true; title: "新增快捷填写选项"
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string capturedKey: ""
        onOpened: {
            capturedKey = card.loadedKey
            shortcutText.text = card.draftEditor ? card.draftEditor.text : ""
            shortcutText.forceActiveFocus(); shortcutText.selectAll()
        }
        onAccepted: {
            if (capturedKey !== card.service.editorKey || !card.workflow.addFeedbackShortcut(shortcutText.text))
                card.saveState = "快捷选项未添加，请检查内容或当前学员"
        }
        UiTextField {
            id: shortcutText; objectName: "feedbackShortcutInput"
            width: parent.width; placeholderText: "输入新的快捷反馈"
            selectByMouse: true
            onAccepted: shortcutDialog.accept()
        }
    }
}
