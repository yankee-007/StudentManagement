import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property var ai: backend.aiCampaign
    property var recordKeys: []
    property string selectedMode: ["person", "batch", "all"][mode.currentIndex] || "batch"
    property int selectedTemplate: templateChoice.currentIndex
    function reset() {
        ai.reset()
        templateChoice.currentIndex = 0
        mode.currentIndex = ["person", "batch", "all"].indexOf(ai.config.mode)
    }
    spacing: 8
    Label {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted
        text: "当前筛选 " + panel.recordKeys.length + " 人。模板按课程节次选；AI 会收到姓名、学号及当前欠账，不读取反馈历史。"
    }
    GridLayout {
        Layout.fillWidth: true; columns: 2; columnSpacing: 8
        enabled: !panel.ai.busy
        Label { text: "话术模板"; color: UiTheme.muted }
        UiComboBox {
            id: templateChoice; objectName: "aiTemplateSelector"; Layout.fillWidth: true
            Accessible.name: "AI 催交话术模板"
            model: {
                var items = ["自动 · 当前第 " + panel.ai.currentLesson + " 节课" + (panel.ai.currentLesson > 32 ? "（取第32份）" : "")]
                for(var i=1;i<=32;i++) items.push("第 " + i + " 份话术")
                return items
            }
            onActivated: panel.ai.reset()
        }
        Label { text: "生成方式"; color: UiTheme.muted }
        UiComboBox {
            id: mode; objectName: "aiGenerationMode"; Layout.fillWidth: true
            model: ["逐人", "分批（推荐）", "一次生成全部"]
            Accessible.name: "本次 AI 生成方式"
        }
    }
    Flow {
        Layout.fillWidth: true; spacing: 8
        UiButton { objectName: "generateAiCampaign"; text: panel.ai.ready ? "重新生成" : "生成 AI 话术"; highlighted: true; enabled: !panel.ai.busy && panel.recordKeys.length>0; onClicked: panel.ai.start(panel.recordKeys,panel.selectedTemplate,panel.selectedMode) }
        UiButton { objectName: "retryAiFailures"; text: "重试失败项（" + panel.ai.failureCount + "）"; visible: panel.ai.failureCount>0; enabled: !panel.ai.busy && panel.ai.ready; onClicked: panel.ai.retryFailed(panel.recordKeys,panel.selectedMode) }
        UiButton { objectName: "cancelAiCampaign"; text: "停止生成"; visible: panel.ai.busy; onClicked: panel.ai.cancel() }
    }
    ProgressBar { Layout.fillWidth: true; visible: panel.ai.busy; from: 0; to: Math.max(1,panel.ai.total); value: panel.ai.completed }
    Label { objectName: "aiCampaignNotice"; text: panel.ai.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    Label { text: "已处理 " + panel.ai.completed + " / " + panel.ai.total + " 人"; visible: panel.ai.busy; color: UiTheme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
    ListView {
        id: results; objectName: "aiCampaignResults"; Layout.fillWidth: true; Layout.fillHeight: true
        clip: true; spacing: 8; model: panel.ai.results
        ScrollBar.vertical: ScrollBar {}
        delegate: UiPanel {
            required property var modelData
            width: results.width; implicitHeight: rowContent.implicitHeight + 20
            ColumnLayout {
                id: rowContent; anchors.fill: parent; anchors.margins: 10; spacing: 4
                Label { text: modelData.name + " · " + modelData.studentId + " · " + modelData.kind; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                Label { text: modelData.error || "生成成功"; color: modelData.error ? UiTheme.warning : UiTheme.success; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { text: modelData.text; visible: !!modelData.text; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                UiButton { text: "查看／补写"; enabled: panel.ai.ready; onClicked: { editDialog.studentId=modelData.studentId; editDialog.studentName=modelData.name; draft.text=modelData.text; editDialog.open() } }
            }
        }
    }
    Dialog {
        id: editDialog; objectName: "aiEditResultDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        property string studentId: ""
        property string studentName: ""
        title: studentName + " · 话术"; modal: true
        width: Math.min(parent.width-40,560); height: Math.min(parent.height-40,350)
        ColumnLayout {
            anchors.fill: parent
            TextArea { id: draft; objectName: "aiResultDraft"; Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: TextEdit.Wrap; selectByMouse: true }
            Label { text: panel.ai.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            RowLayout {
                UiButton { objectName: "saveAiResultDraft"; text: "保存话术"; onClicked: if(panel.ai.editResult(editDialog.studentId,draft.text)) editDialog.close() }
                UiButton { text: "取消"; onClicked: editDialog.close() }
            }
        }
    }
}
