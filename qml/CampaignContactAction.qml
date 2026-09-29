import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: action
    required property var service
    property var opener: backend.contactOpener
    property string contactKey: service.editorKey || ""
    spacing: 4
    onContactKeyChanged: prefixInput.text = opener.campaignPrefix(contactKey)
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        Label { text: "前缀"; font.pixelSize: 12; color: "#667085" }
        TextField {
            id: prefixInput; objectName: "campaignContactPrefix"
            Layout.fillWidth: true; placeholderText: "可留空"; font.pixelSize: 12
            enabled: !action.opener.active; selectByMouse: true
        }
        Button {
            objectName: "openCampaignContact"
            text: action.opener.active ? "正在打开…" : "打开企微联系人"
            enabled: !!action.service.selected.name && !action.service.selected.is_placeholder && !action.opener.active && !backend.groupCenter.active
            onClicked: action.opener.openCampaignContact(action.contactKey,prefixInput.text)
        }
    }
    CheckBox {
        text: "使用企微浮窗验证联系人"
        checked: action.opener.verifyContact; enabled: !action.opener.active
        onToggled: action.opener.setVerifyContact(checked)
    }
    CheckBox {
        text: "保留企微浮窗（Ctrl+O）"
        checked: action.opener.keepFloat; enabled: !action.opener.active && action.opener.verifyContact
        onToggled: action.opener.setKeepFloat(checked)
    }
    Label { text: action.opener.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#667085"; font.pixelSize: 11 }
}
