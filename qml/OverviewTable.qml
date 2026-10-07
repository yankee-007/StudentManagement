import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property string title: ""
    property var headers: []
    property var rows: []
    property int selectedKey: -1
    property int minimumColumnWidth: headers.length > 8 ? 110 : 100
    signal rowSelected(int key)
    implicitHeight: column.implicitHeight + 24
    color: UiTheme.surface; radius: 8; border.color: UiTheme.line
    ColumnLayout {
        id: column; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 12; spacing: 8
        Label { text: root.title; color: UiTheme.ink; font.bold: true; Layout.fillWidth: true }
        Flickable {
            id: table; Layout.fillWidth: true; Layout.preferredHeight: Math.min(340, 48 + root.rows.length * 34)
            contentWidth: Math.max(width, root.headers.length * root.minimumColumnWidth)
            contentHeight: body.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.horizontal: ScrollBar { policy: table.contentWidth > table.width ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }
            ScrollBar.vertical: ScrollBar { }
            Column {
                id: body; width: table.contentWidth
                Rectangle {
                    width: parent.width; height: 48; color: UiTheme.stripe
                    Row {
                        anchors.fill: parent
                        Repeater {
                            model: root.headers
                            Label { required property var modelData; width: body.width / root.headers.length; height: 48; text: modelData; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap; font.pixelSize: 12; color: UiTheme.muted; padding: 4 }
                        }
                    }
                }
                Repeater {
                    model: root.rows
                    ItemDelegate {
                        required property var modelData
                        required property int index
                        width: body.width; height: 34; padding: 0
                        Accessible.name: modelData.cells.join("，")
                        background: Rectangle { color: root.selectedKey === parent.modelData.key ? UiTheme.selection : parent.hovered ? "#eef3fb" : parent.index % 2 ? UiTheme.stripe : UiTheme.surface; border.width: parent.visualFocus ? 1 : 0; border.color: UiTheme.accent }
                        contentItem: Row {
                            Repeater {
                                model: modelData.cells
                                Label { required property var modelData; width: body.width/root.headers.length; height: 34; text: modelData; color: UiTheme.ink; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
                            }
                        }
                        onClicked: root.rowSelected(modelData.key)
                    }
                }
                Label { width: body.width; height: 40; visible: root.rows.length === 0; text: "暂无有效快照，缺失数据不估算"; color: UiTheme.muted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
    }
}
