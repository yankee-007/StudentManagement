import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 单个平台的账号设置卡片：账号 / 原始密码 / 验证与保存 / 验证结果。
SettingsCard {
    id: card
    required property string platform
    property var service: backend.settingsModule
    property var record: service.accounts[platform] || ({})
    // 通用状态通知会重新求值 record；只有已保存账号真的变化才更新输入框。
    readonly property string savedUsername: record.username || ""
    property var verification: service.verification[platform] || ({})

    subtitle: platform === "completion" ? "追光鲸鱼后台账号" : "作业平台后台账号"
    tag: record.saved ? "密码已保存" : "尚未保存密码"
    tagColor: record.saved ? "#027a48" : UiTheme.warning
    tagBackground: record.saved ? "#ecfdf3" : "#fffaeb"

    headerRight: Rectangle {
        implicitWidth: tagLabel.implicitWidth + 16
        implicitHeight: 20
        radius: 10
        color: card.tagBackground
        Label { id: tagLabel; anchors.centerIn: parent; text: card.tag; font.pixelSize: 12; color: card.tagColor }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: 12
        rowSpacing: 10
        Label { text: "账号"; color: UiTheme.muted; font.pixelSize: 12; Layout.preferredWidth: 96; Layout.alignment: Qt.AlignVCenter }
        UiTextField {
            id: usernameField
            objectName: card.platform + "Username"
            Layout.fillWidth: true
            text: card.savedUsername
            placeholderText: "账号"; selectByMouse: true
            enabled: !card.service.busy
            onTextEdited: card.service.clearVerification(card.platform)
        }
        Label { text: "原始密码"; color: UiTheme.muted; font.pixelSize: 12; Layout.preferredWidth: 96; Layout.alignment: Qt.AlignVCenter }
        UiTextField {
            id: passwordField
            objectName: card.platform + "Password"
            Layout.fillWidth: true
            placeholderText: card.record.saved ? "留空则保持现有密码" : "请输入原始密码"
            echoMode: TextInput.Password
            enabled: !card.service.busy
            onTextEdited: card.service.clearVerification(card.platform)
        }
    }

    Label {
        text: card.verification.message || ""
        visible: text.length > 0
        color: card.verification.state === "success" ? "#027a48" : card.verification.state === "error" ? "#b42318" : UiTheme.muted
        font.pixelSize: 12; wrapMode: Text.Wrap
        Layout.fillWidth: true
    }

    footer: RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Label {
            text: card.record.saved ? "保存后不会在界面回显密码。" : "保存后不会在界面回显密码，下次获取数据时生效。"
            color: "#98a2b3"; font.pixelSize: 12
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        UiButton {
            objectName: card.platform + "VerifyLogin"
            text: card.service.verifyingPlatform === card.platform ? "验证中…" : "验证登录"
            enabled: !card.service.busy && !backend.busy && !backend.termsModule.busy
            onClicked: card.service.verifyLogin(card.platform, usernameField.text, passwordField.text)
        }
        UiButton {
            text: "保存"; highlighted: true
            enabled: !card.service.busy
            onClicked: {
                if (card.service.saveAccount(card.platform, usernameField.text, passwordField.text)) passwordField.text = ""
            }
        }
    }
}
