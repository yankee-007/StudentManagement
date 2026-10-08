import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: action
    required property var service
    property string contactKey: service.editorKey || ""
    property var opener: backend.contactOpener
    Layout.fillWidth: true; spacing: 4
    onContactKeyChanged: options.loadPrefix(opener.campaignPrefix(contactKey))
    Component.onCompleted: options.loadPrefix(opener.campaignPrefix(contactKey))
    Connections { target: action.opener; function onDefaultPrefixChanged() { options.loadPrefix(action.opener.campaignPrefix(action.contactKey)) } }
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        Label {
            objectName: "campaignContactName"
            text: action.service.selected.name || "请选择学员"
            font.pixelSize: 20; font.bold: true; color: UiTheme.ink
            Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight
            ToolTip.visible: nameHover.hovered; ToolTip.text: text
            HoverHandler { id: nameHover }
        }
        UiButton {
            objectName: "openCampaignContact"; font.pixelSize: 12
            text: action.opener.active ? "正在打开…" : "打开企微联系人"
            enabled: !!action.service.selected.name && !action.service.selected.is_placeholder && !action.opener.active && !backend.groupCenter.active && !backend.workflow.sender.active
            onClicked: action.opener.openCampaignContact(action.contactKey, options.effectivePrefix)
        }
        ContactOptions { id: options; objectName: "campaignContactOptions"; namePrefix: "campaign"; opener: action.opener }
    }
    Label { visible: action.opener.active || action.opener.notice !== "按姓名包含匹配，可选择是否保留企微浮窗"; text: action.opener.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
}
