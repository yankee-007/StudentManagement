import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: floating
    objectName: "campaignFloatingWindow"
    width: 246; height: 520; minimumWidth: 230; minimumHeight: 300
    title: "催办反馈 · 跟随聊天"; color: UiTheme.canvas
    palette: UiTheme.controlPalette
    transientParent: null
    property bool pinned: true
    property var companion: backend.campaignCompanion
    onClosing: function(close) { Qt.inputMethod.commit(); if (!backend.dailyWorkspace.flushEditor() || !backend.workflow.flushFeedback()) close.accepted=false }
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | (pinned ? Qt.WindowStaysOnTopHint : 0)
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
                text: companion.selected.name || "等待识别"; font.pixelSize: 16; font.bold: true; color: UiTheme.ink; Layout.fillWidth: true; elide: Text.ElideRight
                MouseArea { anchors.fill: parent; cursorShape: Qt.SizeAllCursor; onPressed: floating.startSystemMove() }
            }
            ToolButton { text: "置顶"; font.pixelSize: 12; checkable: true; checked: floating.pinned; onClicked: floating.pinned=checked }
            ToolButton { text: "重试"; font.pixelSize: 12; onClicked: companion.retryContact() }
        }
        Label { text: companion.notice; font.pixelSize: 13; color: UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: UiTheme.line }
        CampaignDetail {
            objectName: "floatingCampaignDetail"
            visible: !!companion.selected.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            service: companion; workflow: backend.workflow
            showContactAction: false
            showName: false; compact: true
        }
        Label {
            visible: !companion.selected.student_id
            Layout.fillWidth: true; Layout.fillHeight: true
            verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter
            text: "激活学员的企业微信独立聊天窗口\n按当前班期和姓名自动匹配"
            color: UiTheme.subtle; wrapMode: Text.Wrap
        }
    }
}
