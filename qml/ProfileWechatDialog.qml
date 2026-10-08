import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "profileWechatDialog"
    required property var verifier
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    width: Math.min(900, parent.width - 32)
    height: Math.min(590, parent.height - 32)
    title: "批量验证微信 · " + verifier.className
    closePolicy: Popup.CloseOnEscape
    contentItem: ColumnLayout {
        spacing: 10
        Label {
            text: "按当前班期完整名单逐人搜索企业微信，排除已退课与补位学员。确认匹配后将微信改为「是」，未找到或待确认时保留原值。重名与非标准备注请人工确认。"
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted
        }
        Label {
            objectName: "profileWechatNotice"
            text: dialog.verifier.notice
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink
        }
        ProgressBar {
            objectName: "profileWechatProgress"
            Layout.fillWidth: true
            from: 0; to: Math.max(1, dialog.verifier.total); value: dialog.verifier.completed
            visible: dialog.verifier.active
            Accessible.name: "微信验证进度"
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            HorizontalHeaderView {
                id: header
                syncView: table
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: UiTheme.headerHeight
                delegate: Rectangle {
                    required property var display
                    implicitWidth: 110; implicitHeight: UiTheme.headerHeight
                    color: UiTheme.stripe
                    Text { anchors.fill: parent; anchors.margins: 6; text: display; color: UiTheme.ink; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                }
            }
            TableView {
                id: table
                objectName: "profileWechatTable"
                model: dialog.verifier.tableModel
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: header.bottom; anchors.bottom: parent.bottom
                clip: true; reuseItems: true; rowSpacing: 1; columnSpacing: 1
                columnWidthProvider: function(c) { return [135, 90, 80, 155, 300][c] }
                rowHeightProvider: function() { return UiTheme.rowHeight }
                ScrollBar.horizontal: ScrollBar {}
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property int row
                    required property string display
                    implicitWidth: 110; implicitHeight: UiTheme.rowHeight
                    color: row % 2 ? UiTheme.stripe : UiTheme.surface
                    Text { anchors.fill: parent; anchors.margins: 6; text: display; color: UiTheme.ink; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.pixelSize: 12 }
                    HoverHandler { id: hover }
                    ToolTip.visible: hover.hovered && display.length > 0
                    ToolTip.text: display
                }
            }
            Label { anchors.centerIn: parent; visible: dialog.verifier.total === 0; text: "当前班期没有可验证的学员"; color: UiTheme.muted }
        }
        Flow {
            Layout.fillWidth: true; spacing: 8
            UiButton { objectName: "profileWechatStart"; text: dialog.verifier.completed > 0 ? "重新验证" : "开始验证"; highlighted: true; enabled: !dialog.verifier.active && dialog.verifier.total > 0; onClicked: dialog.verifier.start() }
            UiButton { objectName: "profileWechatPause"; text: dialog.verifier.isPaused ? "继续验证" : dialog.verifier.pauseRequested ? "等待暂停" : "暂停验证"; visible: dialog.verifier.active; enabled: !dialog.verifier.stopping && (!dialog.verifier.pauseRequested || dialog.verifier.isPaused); onClicked: dialog.verifier.togglePause() }
            UiButton { objectName: "profileWechatStop"; text: dialog.verifier.stopping ? "正在结束" : "结束本轮"; visible: dialog.verifier.active; enabled: !dialog.verifier.stopping; onClicked: dialog.verifier.stop() }
            UiButton { text: dialog.verifier.active ? "收起" : "关闭"; onClicked: dialog.close() }
        }
    }
}
