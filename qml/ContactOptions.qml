import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

UiButton {
    id: options
    property var opener: backend.contactOpener
    property alias prefixValue: prefixInput.text
    property bool usePrefix: true
    property string namePrefix: ""
    readonly property string effectivePrefix: usePrefix ? prefixValue : ""
    text: "选项"
    enabled: !opener.active
    Accessible.name: "联系人选项"
    Accessible.description: "选择前缀、验证联系人及保留浮窗"
    onClicked: menu.open()
    function loadPrefix(value) { prefixValue = value; usePrefix = true }
    Popup {
        id: menu
        objectName: options.namePrefix + "ContactOptionsPopup"
        y: options.height + 4
        x: options.width - width
        width: 278; padding: 12; margins: 8
        height: body.implicitHeight + 24
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { radius: 6; color: UiTheme.surface; border.color: UiTheme.line }
        ColumnLayout {
            id: body; anchors.fill: parent; spacing: 6
            Label { text: "联系人选项 · 可多选"; font.bold: true; color: UiTheme.ink }
            CheckBox {
                objectName: options.namePrefix + "UseContactPrefix"
                text: "使用前缀"; checked: options.usePrefix
                onToggled: options.usePrefix = checked
            }
            UiTextField {
                id: prefixInput
                objectName: options.namePrefix + "ContactPrefix"
                Layout.fillWidth: true
                enabled: options.usePrefix; placeholderText: "可留空，按姓名搜索"
                Accessible.name: "联系人前缀"
            }
            CheckBox {
                objectName: options.namePrefix === "profile" ? "verifyProfileContact" : "verifyCampaignContact"
                text: "使用浮窗验证联系人"; checked: options.opener.verifyContact
                onToggled: options.opener.setVerifyContact(checked)
            }
            CheckBox {
                objectName: options.namePrefix === "profile" ? "keepProfileContactFloat" : "keepCampaignContactFloat"
                text: "保留企微浮窗（Ctrl+O）"; checked: options.opener.keepFloat
                enabled: options.opener.verifyContact
                onToggled: options.opener.setKeepFloat(checked)
            }
            Label { text: "不验证时仅搜索联系人。默认前缀可在设置中配置。"; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12; color: UiTheme.muted }
            UiButton { objectName: options.namePrefix + "UseDefaultPrefix"; text: "使用设置中的默认前缀"; Layout.fillWidth: true; onClicked: options.loadPrefix(options.opener.defaultPrefix) }
        }
    }
}
