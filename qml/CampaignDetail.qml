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
    property bool hasStudent: !!service.selected.student_id
    property var fields: []
    spacing: 8

    function refreshFields() {
        var next = workflow.managedFields.filter(function(field) { return field.show_column })
            .map(function(field) { return {key:field.field_id,label:field.name} })
        if (JSON.stringify(next) !== JSON.stringify(fields)) fields = next
    }

    function loadSelection(force) {
        var key = service.editorKey || ""
        if (loadedKey === key && !force && draftEditor && draftEditor.activeFocus) return
        loadingDraft = true
        if (loadedKey !== key && draftEditor && draftEditor.activeFocus) Qt.inputMethod.reset()
        loadedKey = key
        if (draftEditor) draftEditor.text = service.selected.draft || ""
        loadingDraft = false
    }
    Component.onCompleted: { refreshFields(); loadSelection(true) }
    Connections {
        target: card.workflow
        function onChanged() { card.refreshFields() }
    }
    Connections {
        target: card.service
        function onSelectionChanged() { card.loadSelection(false) }
        function onChanged() { card.loadSelection(false) }
    }
    Label {
        text: card.service.selected.name || (card.hasStudent ? "姓名待补全" : "选择学员")
        font.pixelSize: 21; font.bold: true; color: "#17213a"
    }
    CampaignContactAction {
        visible: card.hasStudent && card.service.canEdit
        Layout.fillWidth: true; service: card.service
    }
    ScrollView {
        id: details; Layout.fillWidth: true; Layout.fillHeight: true
        contentWidth: availableWidth; clip: true
        ColumnLayout {
            width: details.availableWidth - 12; spacing: 10
            enabled: card.hasStudent
            Repeater {
                model: card.fields.filter(function(field) { return field.key !== "name" })
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 6
                    Label {
                        visible: modelData.key !== "feedback" && modelData.key !== "exemption_text"
                        text: modelData.label + "：" + (card.service.selected[modelData.key] || "—")
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#344054"
                    }
                    ColumnLayout {
                        visible: modelData.key === "feedback"
                        Layout.fillWidth: true; spacing: 6
                        Label { text: "本次反馈 · 粘贴聊天原文"; font.bold: true; color: "#344054" }
                        TextArea {
                            id: draft; objectName: modelData.key === "feedback" ? (card.service === card.workflow ? "feedbackDraft" : "floatingFeedbackDraft") : ""
                            Layout.fillWidth: true; implicitHeight: 100; padding: 10
                            wrapMode: TextEdit.Wrap; selectByMouse: true
                            enabled: card.service.canEdit && card.hasStudent && !!card.service.selected.name && !card.service.selected.is_placeholder
                            placeholderText: "例如：军训＋考试太忙了"
                            background: Rectangle { color: "#f9fafb"; radius: 6; border.color: draft.activeFocus ? "#809aff" : "#e4e7ec" }
                            Component.onCompleted: if (modelData.key === "feedback") { card.draftEditor = draft; card.loadSelection(true) }
                            Component.onDestruction: if (card.draftEditor === draft) card.draftEditor = null
                            function save() {
                                if (!card.loadingDraft && card.hasStudent && activeFocus && !inputMethodComposing)
                                    status.text = card.service.saveEditorValue(card.loadedKey,"draft",text) ? "草稿已保存" : "保存失败，请勿切换"
                            }
                            onTextChanged: save()
                            onInputMethodComposingChanged: save()
                        }
                        Label { id: status; text: "草稿自动保存，提交后计为已回复"; font.pixelSize: 11; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Button {
                            text: "记录反馈"; Layout.fillWidth: true; highlighted: true
                            enabled: draft.enabled && draft.text.trim().length > 0
                            onClicked: card.service.saveEditorValue(card.loadedKey,"submit",draft.text)
                        }
                        Label { text: "本批次已记录"; font.bold: true; color: "#344054" }
                        TextArea {
                            text: card.service.selected.feedback || "暂无反馈"; readOnly: true
                            selectByMouse: true; wrapMode: TextEdit.Wrap; Layout.fillWidth: true
                            font.pixelSize: 12; background: Rectangle { color: "#f9fafb"; radius: 6 }
                        }
                        CheckBox { id: historyToggle; text: "查看以往反馈（含迁移前记录）" }
                        TextArea {
                            visible: historyToggle.checked; text: card.service.previousFeedback
                            readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; Layout.fillWidth: true; font.pixelSize: 12
                        }
                    }
                    ColumnLayout {
                        visible: modelData.key === "exemption_text"
                        Layout.fillWidth: true; spacing: 6
                        Label { text: "免催日期：" + (card.service.selected.exemption_text || "无"); Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#344054" }
                        Label { text: card.service.leaveNote; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12; color: "#667085" }
                        RowLayout {
                            Button { text: "设置免催日期"; enabled: card.service.canSetExemption && card.hasStudent; onClicked: card.service.setLeave() }
                            Button { text: "清除免催"; enabled: card.service.canSetExemption && card.hasStudent; onClicked: card.service.clearLeave() }
                        }
                    }
                }
            }
        }
    }
}
