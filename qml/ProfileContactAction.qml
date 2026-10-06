import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: action
    property var student: ({})
    property var opener: backend.contactOpener
    Layout.fillWidth: true
    spacing: 4
    onStudentChanged: prefixInput.text = opener.prefix(student._record_key || "")
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        Label { text: "前缀"; font.pixelSize: 12; color: UiTheme.muted }
        UiTextField {
            id: prefixInput; objectName: "profileContactPrefix"
            Layout.fillWidth: true; Layout.minimumWidth: 45
            placeholderText: "可留空"; font.pixelSize: 12
            enabled: !opener.active
            selectByMouse: true
            ToolTip.visible: hovered; ToolTip.text: "例如 py169；留空时按姓名搜索，打开后记住当前班期的前缀"
        }
        UiButton {
            objectName: "openProfileContact"
            text: opener.active ? "正在打开…" : "打开企微联系人"
            enabled: !!action.student.name && !action.student.is_placeholder && !opener.active && !backend.groupCenter.active && !backend.workflow.sender.active
            onClicked: opener.openContact(action.student._record_key || "",prefixInput.text)
        }
    }
    CheckBox {
        objectName: "verifyProfileContact"
        text: "使用企微浮窗验证联系人"
        checked: opener.verifyContact
        enabled: !opener.active
        onToggled: opener.setVerifyContact(checked)
        ToolTip.visible: hovered
        ToolTip.text: "未勾选时仅搜索联系人，不打开企微浮窗"
    }
    CheckBox {
        objectName: "keepProfileContactFloat"
        text: "保留企微浮窗（Ctrl+O）"
        checked: opener.keepFloat
        enabled: !opener.active && opener.verifyContact
        onToggled: opener.setKeepFloat(checked)
        ToolTip.visible: hovered
        ToolTip.text: "未勾选时，核对联系人后关闭企微浮窗，回到主界面聊天"
    }
    Label { text: opener.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
}
