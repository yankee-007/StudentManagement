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
    color: UiTheme.canvas
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
                text: companion.displayName; font.pixelSize: 16; font.bold: true; color: UiTheme.ink
                Layout.fillWidth: true; elide: Text.ElideRight
            }
            ToolButton { text: "置顶"; font.pixelSize: 12; checkable: true; checked: floating.pinned; onClicked: floating.pinned=checked }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "班级"; color: UiTheme.muted; font.pixelSize: 13 }
            ComboBox {
                objectName: "profileCompanionClassSelector"
                Layout.fillWidth: true
                wheelEnabled: false
                model: companion.classOptions
                currentIndex: companion.classIndex
                Accessible.name: "画像浮窗班级"
                onActivated: companion.selectClass(index)
            }
        }
        Label { text: companion.notice; font.pixelSize: 13; color: UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: UiTheme.line }
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
            text: "激活学员的企业微信独立聊天窗口\n按备注前缀或姓名跨班识别\n重名时请选择班级"
            color: "#98a2b3"; wrapMode: Text.Wrap
        }
    }
}
