import QtQuick
import QtQuick.Controls

TextField {
    id: control
    implicitHeight: 34
    leftPadding: 9
    rightPadding: 9
    font.pixelSize: 13
    color: UiTheme.ink
    placeholderTextColor: UiTheme.muted
    selectionColor: UiTheme.accentFill
    selectedTextColor: UiTheme.accentText
    background: Rectangle {
        radius: 5
        color: control.enabled && !control.readOnly ? UiTheme.surface : UiTheme.stripe
        border.color: control.activeFocus ? UiTheme.accent : UiTheme.line
        border.width: control.activeFocus ? 2 : 1
    }
}
