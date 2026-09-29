import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: floating
    objectName: "profileFloatingWindow"
    width: 400; height: 520
    minimumWidth: 340; minimumHeight: 280
    title: "学员画像 · 跟随聊天"
    color: "#f5f7fb"
    property bool pinned: true
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | (pinned ? Qt.WindowStaysOnTopHint : 0)
    property var companion: backend.profileCompanion
    onActiveChanged: companion.setEditing(active && visible)
    onVisibleChanged: {
        if (visible) { companion.open(); companion.setEditing(active) }
        else { companion.close(); companion.setEditing(false) }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "学员画像  ⠿"; font.pixelSize: 18; font.bold: true; color: "#17213a"
                Layout.fillWidth: true
                MouseArea { anchors.fill: parent; cursorShape: Qt.SizeAllCursor; onPressed: floating.startSystemMove() }
            }
            ToolButton {
                text: "锁定学员"; checkable: true; checked: companion.locked
                enabled: !!companion.student.student_id
                onClicked: companion.setLocked(checked)
                ToolTip.visible: hovered; ToolTip.text: "锁定后保持当前学员"
            }
            ToolButton { text: "置顶"; checkable: true; checked: floating.pinned; onClicked: floating.pinned=checked }
            ToolButton { text: "重试"; onClicked: companion.retryContact(); ToolTip.visible: hovered; ToolTip.text: "重新识别最近激活的企微联系人" }
        }
        Label { text: companion.notice; font.pixelSize: 11; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#e4e7ec" }
        ProfileIdentity { visible: !!companion.student.student_id; student: companion.student }
        ProfileEditor {
            objectName: "floatingProfileEditor"
            visible: !!companion.student.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            fields: companion.fields; saveTarget: companion
        }
        Label {
            visible: !companion.student.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter
            text: "激活学员的企业微信独立聊天窗口\n按当前班期和姓名自动匹配"
            color: "#98a2b3"; wrapMode: Text.Wrap
        }
    }
}
