import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property var field: ({})
    property int position: 0
    property int fieldCount: 0
    property bool interactive: true
    property bool lifted: false
    property bool recent: false
    signal visibilityToggled(bool value)
    signal moveRequested(int offset)
    signal removeRequested()
    implicitHeight: 48
    radius: 6
    color: recent ? UiTheme.selection : UiTheme.surface
    border.color: lifted || recent ? UiTheme.accent : UiTheme.line
    border.width: lifted ? 2 : 1

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 6
        Item {
            Layout.preferredWidth: 28; Layout.preferredHeight: 36
            Grid {
                anchors.centerIn: parent; columns: 2; spacing: 4
                Repeater {
                    model: 6
                    Rectangle { width: 3; height: 3; radius: 1.5; color: card.lifted ? UiTheme.accent : UiTheme.muted }
                }
            }
        }
        Label {
            text: card.position + 1; color: UiTheme.muted; font.pixelSize: 12
            Layout.preferredWidth: 20; horizontalAlignment: Text.AlignHCenter
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 40; spacing: 2
            Label {
                Layout.fillWidth: true; text: card.field.name || ""
                font.pixelSize: 13; font.weight: Font.DemiBold
                color: UiTheme.ink; elide: Text.ElideRight
                ToolTip.visible: nameHover.hovered && truncated; ToolTip.text: text
                HoverHandler { id: nameHover }
            }
            Label {
                Layout.fillWidth: true
                text: card.field.locked ? (card.field.note || "固定显示") : !card.field.deletable ? "系统字段" : card.field.kind === "date" ? "日期" : card.field.kind === "choice" ? "下拉选项" : "文本"
                color: UiTheme.muted; font.pixelSize: 11; elide: Text.ElideRight
            }
        }
        CheckBox {
            objectName: "fieldVisibility"; text: card.field.locked ? "必显" : "显示"
            checked: !!card.field.show_column; enabled: card.interactive && !card.field.locked
            font.pixelSize: 12; Accessible.name: (card.field.name || "") + "显示设置"
            onToggled: card.visibilityToggled(checked)
        }
        RowLayout {
            spacing: 0
            ToolButton {
                objectName: "fieldMoveUp"; text: "↑"; implicitWidth: 26; implicitHeight: 32
                enabled: card.interactive && card.position > 0
                Accessible.name: "上移" + (card.field.name || "")
                ToolTip.visible: hovered; ToolTip.text: "上移"
                onClicked: card.moveRequested(-1)
            }
            ToolButton {
                objectName: "fieldMoveDown"; text: "↓"; implicitWidth: 26; implicitHeight: 32
                enabled: card.interactive && card.position < card.fieldCount - 1
                Accessible.name: "下移" + (card.field.name || "")
                ToolTip.visible: hovered; ToolTip.text: "下移"
                onClicked: card.moveRequested(1)
            }
        }
        ToolButton {
            objectName: "fieldRemove"; text: "删除"
            visible: !!card.field.deletable; enabled: card.interactive
            implicitWidth: 40; implicitHeight: 32; font.pixelSize: 12
            palette.buttonText: UiTheme.danger
            Accessible.name: "删除" + (card.field.name || "")
            onClicked: card.removeRequested()
        }
    }
}
