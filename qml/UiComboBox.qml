import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    implicitHeight: 34
    font.pixelSize: 13
    leftPadding: 9
    palette.text: UiTheme.ink
    palette.buttonText: UiTheme.ink
    background: Rectangle {
        radius: 5
        color: !control.enabled ? UiTheme.stripe : control.down ? UiTheme.selection : UiTheme.surface
        border.color: control.visualFocus ? UiTheme.accent : UiTheme.line
        border.width: control.visualFocus ? 2 : 1
    }
}
