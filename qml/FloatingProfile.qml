import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: floating
    objectName: "profileFloatingWindow"
    width: 240; height: 490
    minimumWidth: 220; minimumHeight: 280
    title: "学员画像 · 跟随聊天"
    color: "#f5f7fb"
    transientParent: null
    property bool pinned: true
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | (pinned ? Qt.WindowStaysOnTopHint : 0)
    property var companion: backend.profileCompanion
    onActiveChanged: companion.setEditing(active && visible)
    onVisibleChanged: {
        if (visible) { companion.open(); companion.setEditing(active) }
        else { companion.close(); companion.setEditing(false) }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 7; spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: companion.student.name || "等待识别"; font.pixelSize: 16; font.bold: true; color: "#17213a"
                Layout.fillWidth: true; elide: Text.ElideRight
                MouseArea { anchors.fill: parent; cursorShape: Qt.SizeAllCursor; onPressed: floating.startSystemMove() }
            }
            ToolButton { text: "置顶"; font.pixelSize: 11; checkable: true; checked: floating.pinned; onClicked: floating.pinned=checked }
            ToolButton { text: "重试"; font.pixelSize: 11; onClicked: companion.retryContact(); ToolTip.visible: hovered; ToolTip.text: "重新识别最近激活的企微联系人" }
        }
        Label { text: companion.notice; font.pixelSize: 10; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#e4e7ec" }
        ProfileIdentity { visible: !!companion.student.student_id; student: companion.student; showName: false; compact: true }
        ProfileEditor {
            objectName: "floatingProfileEditor"
            visible: !!companion.student.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            fields: companion.fields; saveTarget: companion
            deferTextSave: true
            compact: true
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
