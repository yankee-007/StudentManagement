import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ListView {
    id: list
    objectName: "profileFieldOrder"
    property var profiles
    property int dropIndex: -1
    property string draggingId: ""
    signal removeField(string fieldId, string fieldName)
    model: profiles.managedFields
    implicitHeight: Math.min(count * 42, 294)
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar {}
    delegate: Rectangle {
        id: row
        required property var modelData
        required property int index
        width: list.width; height: 42
        radius: 5
        color: list.dropIndex === index ? "#e9efff" : index % 2 ? "#f9fafb" : "white"
        border.color: list.dropIndex === index ? "#809aff" : "transparent"
        RowLayout {
            anchors.fill: parent; anchors.margins: 3; spacing: 6
            Label {
                text: "⠿"; font.pixelSize: 22; color: "#667085"
                Layout.preferredWidth: 28; horizontalAlignment: Text.AlignHCenter
                MouseArea {
                    objectName: "fieldDragHandle"
                    anchors.fill: parent; cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    preventStealing: true
                    onPressed: { list.draggingId = row.modelData.field_id; list.dropIndex = row.index }
                    onPositionChanged: function(mouse) {
                        if (!pressed) return
                        var p = mapToItem(list.contentItem, mouse.x, mouse.y)
                        var viewportY = p.y - list.contentY
                        if (viewportY < 18) list.contentY = Math.max(0,list.contentY-12)
                        if (viewportY > list.height-18) list.contentY = Math.min(Math.max(0,list.contentHeight-list.height),list.contentY+12)
                        list.dropIndex = Math.max(0,Math.min(list.count-1,Math.floor(p.y / 42)))
                    }
                    onReleased: {
                        var key = list.draggingId; var target = list.dropIndex
                        list.draggingId = ""; list.dropIndex = -1
                        if (target >= 0) list.profiles.moveField(key,target)
                    }
                    onCanceled: { list.draggingId=""; list.dropIndex=-1 }
                }
            }
            CheckBox {
                text: row.modelData.name + (row.modelData.locked ? "（固定显示）" : "")
                checked: !!row.modelData.show_column; enabled: !row.modelData.locked
                Layout.fillWidth: true
                onToggled: list.profiles.setFieldVisible(row.modelData.field_id,checked)
            }
            ToolButton { text: "删除"; visible: row.modelData.deletable; onClicked: list.removeField(row.modelData.field_id,row.modelData.name) }
        }
    }
}
