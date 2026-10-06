import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: action
    property var student: ({})
    property string contactKey: student._record_key || ""
    property var opener: backend.contactOpener
    Layout.fillWidth: true; spacing: 4
    onContactKeyChanged: options.loadPrefix(opener.prefix(contactKey))
    Component.onCompleted: options.loadPrefix(opener.prefix(student._record_key || ""))
    Connections { target: action.opener; function onDefaultPrefixChanged() { options.loadPrefix(action.opener.prefix(action.student._record_key || "")) } }
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        Label {
            objectName: "profileContactName"
            text: action.student.name || "请选择学员"
            font.pixelSize: 20; font.bold: true; color: UiTheme.ink
            Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight
            ToolTip.visible: nameHover.hovered; ToolTip.text: text
            HoverHandler { id: nameHover }
        }
        UiButton {
            objectName: "openProfileContact"; font.pixelSize: 12
            text: action.opener.active ? "正在打开…" : "打开企微联系人"
            enabled: !!action.student.name && !action.student.is_placeholder && !action.opener.active && !backend.groupCenter.active && !backend.workflow.sender.active
            onClicked: action.opener.openContact(action.student._record_key || "", options.effectivePrefix)
        }
        ContactOptions { id: options; objectName: "profileContactOptions"; namePrefix: "profile"; opener: action.opener }
    }
    Label { visible: action.opener.active || action.opener.notice !== "按姓名包含匹配，可选择是否保留企微浮窗"; text: action.opener.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
}
