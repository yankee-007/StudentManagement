import QtQuick
import QtQuick.Controls
import QtQuick.Window

ComboBox {
    id: control
    implicitHeight: 34
    font.pixelSize: 13
    leftPadding: 9
    property real popupMinimumWidth: width
    property int popupTextAlignment: Text.AlignLeft
    palette.text: UiTheme.ink
    palette.buttonText: UiTheme.ink
    delegate: ItemDelegate {
        required property int index
        width: ListView.view ? ListView.view.width : control.width
        height: 36
        text: control.textAt(index)
        font: control.font
        hoverEnabled: true
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: parent.text; font: control.font; color: UiTheme.ink
            elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
            horizontalAlignment: control.popupTextAlignment
        }
        background: Rectangle {
            radius: 4
            color: parent.highlighted || parent.hovered ? UiTheme.selection : "transparent"
            border.width: parent.visualFocus ? 2 : 0; border.color: UiTheme.accent
        }
        ToolTip.visible: hovered && contentItem.truncated
        ToolTip.text: text
    }
    popup: Popup {
        y: control.height + 4
        width: Math.min(Math.max(control.width, control.popupMinimumWidth), control.Window.window ? control.Window.window.width - 24 : 480)
        height: Math.min(contentItem.implicitHeight + 12, control.Window.window ? Math.max(120, Math.min(300, control.Window.window.height - 100)) : 300)
        padding: 6; margins: 8
        contentItem: ListView {
            clip: true; implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar { }
        }
        background: Rectangle { radius: 6; color: UiTheme.surface; border.color: UiTheme.line }
    }
    background: Rectangle {
        radius: 5
        color: !control.enabled ? UiTheme.stripe : control.down ? UiTheme.selection : UiTheme.surface
        border.color: control.visualFocus ? UiTheme.accent : UiTheme.line
        border.width: control.visualFocus ? 2 : 1
    }
}
