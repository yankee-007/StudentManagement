import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: floating
    objectName: "campaignFloatingWindow"
    width: 410; height: 550; minimumWidth: 340; minimumHeight: 300
    title: "催办反馈 · 跟随聊天"; color: "#f5f7fb"
    property bool pinned: true
    property var companion: backend.campaignCompanion
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | (pinned ? Qt.WindowStaysOnTopHint : 0)
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
                text: "催办反馈  ⠿"; font.pixelSize: 18; font.bold: true; color: "#17213a"; Layout.fillWidth: true
                MouseArea { anchors.fill: parent; cursorShape: Qt.SizeAllCursor; onPressed: floating.startSystemMove() }
            }
            ToolButton {
                text: "锁定学员"; checkable: true; checked: companion.locked
                enabled: !!companion.selected.student_id
                onClicked: companion.setLocked(checked)
            }
            ToolButton { text: "置顶"; checkable: true; checked: floating.pinned; onClicked: floating.pinned=checked }
            ToolButton { text: "重试"; onClicked: companion.retryContact() }
        }
        Label { text: companion.notice; font.pixelSize: 11; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#e4e7ec" }
        CampaignDetail {
            visible: !!companion.selected.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            service: companion; workflow: backend.workflow
        }
        Label {
            visible: !companion.selected.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter
            text: "激活学员的企业微信独立聊天窗口\n按当前班期和姓名自动匹配"
            color: "#98a2b3"; wrapMode: Text.Wrap
        }
    }
}
