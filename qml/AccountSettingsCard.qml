import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Frame {
    id: card
    required property string platform
    required property string title
    property var service: backend.settingsModule
    property var record: service.accounts[platform] || ({})
    property var verification: service.verification[platform] || ({})
    Layout.fillWidth: true
    padding: 16
    background: Rectangle { color: "white"; radius: 10; border.color: "#e4e7ec" }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: card.title; font.pixelSize: 17; font.bold: true; color: "#17213a"; Layout.fillWidth: true }
            Label { text: card.record.saved ? "密码已保存在凭据管理器" : "尚未保存密码"; color: card.record.saved ? "#027a48" : "#b54708"; font.pixelSize: 12 }
        }
        Label { text: card.platform === "completion" ? "追光鲸鱼后台账号" : "作业平台后台账号"; color: "#667085"; font.pixelSize: 12 }
        TextField {
            id: username; objectName: card.platform + "Username"
            Layout.fillWidth: true; text: card.record.username || ""
            placeholderText: "账号"; selectByMouse: true
            enabled: !card.service.busy
            onTextEdited: card.service.clearVerification(card.platform)
        }
        Label { text: "原始密码"; color: "#667085"; font.pixelSize: 12 }
        TextField {
            id: password; objectName: card.platform + "Password"
            Layout.fillWidth: true; placeholderText: card.record.saved ? "留空则保持现有密码" : "请输入原始密码"
            echoMode: TextInput.Password
            enabled: !card.service.busy
            onTextEdited: card.service.clearVerification(card.platform)
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "保存后不会在界面回显密码"; color: "#98a2b3"; font.pixelSize: 11; Layout.fillWidth: true }
            Button {
                objectName: card.platform + "VerifyLogin"
                text: card.service.verifyingPlatform === card.platform ? "验证中…" : "验证登录"
                enabled: !card.service.busy && !backend.busy && !backend.termsModule.busy
                onClicked: card.service.verifyLogin(card.platform, username.text, password.text)
            }
            Button {
                text: "保存"; highlighted: true
                enabled: !card.service.busy
                onClicked: {
                    if (card.service.saveAccount(card.platform, username.text, password.text)) password.text = ""
                }
            }
        }
        Label {
            visible: text.length > 0
            text: card.verification.message || ""
            color: card.verification.state === "success" ? "#027a48" : card.verification.state === "error" ? "#b42318" : "#667085"
            font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
        }
    }
}
