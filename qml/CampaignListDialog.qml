import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    required property var workflow
    required property var center
    property var ai: backend.aiCampaign
    property var recordKeys: []
    property var previewNames: []
    property string generationError: ""
    readonly property bool namesMode: namesOnly.checked
    readonly property bool aiModeSelected: aiMode.checked
    readonly property bool wide: width >= 780
    readonly property bool compact: height < 520
    signal created()
    objectName: "campaignListDialog"
    title: "生成群发名单"
    modal: true
    padding: compact ? 12 : 16
    width: Math.min(parent.width - 32, 900)
    height: Math.min(parent.height - 24, 680)
    closePolicy: ai.busy ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: UiTheme.surface; border.color: UiTheme.line; radius: 12 }
    onOpened: {
        Qt.inputMethod.commit()
        if (!workflow.flushFeedback()) { close(); return }
        recordKeys = workflow.recipientKeys.slice()
        generationError = ""
        var names = []
        for (var i = 0; i < workflow.visibleCount && names.length < 8; i++) {
            var row = workflow.tableModel.get(i)
            if (!row._filter_stale && row.name && !row.is_placeholder) names.push(row.name)
        }
        previewNames = names
        groupTitle.text = workflow.className + " · 催办筛选名单"
        messageFields.load([{type: "text", text: "{姓名}同学，你好！"}])
        messagesMode.checked = true
        aiPanel.reset()
        groupTitle.forceActiveFocus()
    }
    header: Item {
        implicitHeight: dialog.compact ? 60 : 76
        ColumnLayout {
            anchors.fill: parent; anchors.margins: dialog.compact ? 12 : 16; spacing: 5
            Label { text: "生成群发名单"; color: UiTheme.ink; font.pixelSize: dialog.compact ? 18 : 21; font.weight: Font.DemiBold }
            Label {
                text: dialog.recordKeys.length + " 位学员 · " + dialog.workflow.className + " · 保持当前筛选和排序"
                color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight
            }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: UiTheme.line }
    }
    contentItem: ColumnLayout {
        spacing: dialog.compact ? 8 : 12
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Label { text: "名单名称"; color: UiTheme.ink; font.weight: Font.DemiBold }
            UiTextField {
                id: groupTitle; objectName: "campaignListTitle"
                Layout.fillWidth: true; placeholderText: "例如：第 8 节课作业提醒"
                Accessible.name: "名单名称"; enabled: !dialog.ai.busy; selectByMouse: true
            }
        }
        ButtonGroup { id: modes }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            UiButton {
                id: messagesMode; objectName: "campaignMessagesMode"; text: "配置消息"
                checkable: true; checked: true; ButtonGroup.group: modes
                enabled: !dialog.ai.busy; Layout.fillWidth: true; implicitHeight: dialog.compact ? 34 : 40
            }
            UiButton {
                id: aiMode; objectName: "campaignAiMode"; text: "AI 话术"
                checkable: true; ButtonGroup.group: modes
                enabled: !dialog.ai.busy; Layout.fillWidth: true; implicitHeight: dialog.compact ? 34 : 40
            }
            UiButton {
                id: namesOnly; objectName: "campaignNamesOnly"; text: "仅姓名名单"
                checkable: true; ButtonGroup.group: modes
                enabled: !dialog.ai.busy; Layout.fillWidth: true; implicitHeight: dialog.compact ? 34 : 40
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            Rectangle {
                visible: dialog.wide
                Layout.preferredWidth: 190; Layout.fillHeight: true
                color: UiTheme.stripe; radius: 8; border.color: UiTheme.line
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 10
                    Label { text: "本次名单"; color: UiTheme.ink; font.weight: Font.DemiBold }
                    Label { text: dialog.recordKeys.length + " 位学员"; font.pixelSize: 24; font.weight: Font.DemiBold; color: UiTheme.accent }
                    Rectangle { Layout.fillWidth: true; height: 1; color: UiTheme.line }
                    Repeater {
                        model: dialog.previewNames
                        Label { required property string modelData; text: modelData; color: UiTheme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Label { visible: dialog.recordKeys.length > dialog.previewNames.length; text: "另有 " + (dialog.recordKeys.length - dialog.previewNames.length) + " 位学员"; color: UiTheme.muted }
                    Item { Layout.fillHeight: true }
                    Label { text: "创建后可在群发中心\n逐人检查和修改消息。"; color: UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12; lineHeight: 1.4 }
                }
            }
            ColumnLayout {
                visible: !dialog.namesMode && !dialog.aiModeSelected
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "按顺序配置消息"; color: UiTheme.ink; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    UiButton { id: variableButton; objectName: "campaignVariableButton"; text: "插入变量"; onClicked: variables.open() }
                }
                Label { visible: !dialog.compact; text: "每位学员使用同一模板，变量会替换为对应资料。"; color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                ScrollView {
                    id: messageScroll; objectName: "campaignMessageScroll"
                    Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                    MessageFields { id: messageFields; objectName: "campaignMessageFields"; width: messageScroll.availableWidth }
                }
            }
            AiCampaignPanel {
                id: aiPanel; objectName: "aiCampaignPanel"; ai: dialog.ai
                visible: dialog.aiModeSelected; recordKeys: dialog.recordKeys
                Layout.fillWidth: true; Layout.fillHeight: true
            }
            Rectangle {
                visible: dialog.namesMode
                Layout.fillWidth: true; Layout.fillHeight: true
                color: UiTheme.stripe; border.color: UiTheme.line; radius: 8
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 12
                    Label { text: "先建名单，稍后填写消息"; color: UiTheme.ink; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Label { text: "将当前筛选的 " + dialog.recordKeys.length + " 位学员加入独立群发名单。\n创建后可在群发中心统一套用模板，或为每位学员单独编辑。"; color: UiTheme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeight: 1.5 }
                    Flow {
                        visible: !dialog.wide && !dialog.compact; Layout.fillWidth: true; spacing: 8
                        Repeater {
                            model: dialog.previewNames
                            Label { required property string modelData; text: modelData; color: UiTheme.ink; padding: 6; background: Rectangle { color: UiTheme.surface; radius: 4 } }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Label { text: "发送前需要补齐消息。"; color: UiTheme.muted; font.pixelSize: 12 }
                }
            }
        }
    }
    footer: ColumnLayout {
        spacing: 0
        Rectangle { Layout.fillWidth: true; height: 1; color: UiTheme.line }
        Label {
            objectName: "campaignGenerationNotice"
            visible: !dialog.aiModeSelected && dialog.generationError.length > 0
            text: dialog.generationError; color: UiTheme.warning; wrapMode: Text.Wrap
            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.topMargin: visible ? 6 : 0
        }
        RowLayout {
            Layout.fillWidth: true; Layout.margins: dialog.compact ? 12 : 16; spacing: 8
            Label { text: "创建后尚未发送"; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; visible: dialog.width >= 560 }
            Item { Layout.fillWidth: true; visible: dialog.width < 560 }
            UiButton { text: "取消"; enabled: !dialog.ai.busy; onClicked: dialog.close() }
            UiButton {
                objectName: "createCampaignSelection"; text: "创建并打开群发中心"; highlighted: true
                enabled: groupTitle.text.trim().length > 0 && dialog.recordKeys.length > 0 && !dialog.ai.busy && (!dialog.aiModeSelected || dialog.ai.ready)
                onClicked: {
                    Qt.inputMethod.commit()
                    if (dialog.aiModeSelected ? dialog.ai.createList(groupTitle.text, dialog.recordKeys)
                        : dialog.center.createFromCampaignSelection(groupTitle.text, messageFields.values(), dialog.recordKeys, dialog.namesMode)) {
                        dialog.close(); dialog.created()
                    } else if (!dialog.aiModeSelected) dialog.generationError = dialog.center.status
                }
            }
        }
    }
    Menu {
        id: variables; objectName: "campaignVariables"
        parent: variableButton; y: variableButton.height
        title: "插入学员变量"
        Instantiator {
            model: ["姓名", "学号", "班期", "状态", "免催日期", "欠课", "欠作业"].concat(backend.profilesModule.messagePlaceholders)
            MenuItem {
                required property string modelData
                text: "{" + modelData + "}"
                onTriggered: messageFields.insertVariable(modelData)
            }
            onObjectAdded: function(index, object) { variables.insertItem(index, object) }
            onObjectRemoved: function(index, object) { variables.removeItem(object) }
        }
    }
}
