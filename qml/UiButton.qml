import QtQuick
import QtQuick.Controls

Button {
    id: control
    implicitHeight: 34
    implicitWidth: Math.max(64, contentItem.implicitWidth + leftPadding + rightPadding)
    leftPadding: 12
    rightPadding: 12
    topPadding: 7
    bottomPadding: 7
    font.pixelSize: 13
    hoverEnabled: true
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? UiTheme.disabledText : control.highlighted || control.checked ? UiTheme.accentText : UiTheme.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 5
        color: !control.enabled ? UiTheme.disabledSurface : control.highlighted || control.checked
            ? (control.down ? UiTheme.accentPressed : control.hovered ? UiTheme.accentHover : UiTheme.accentFill)
            : control.down ? UiTheme.pressed : control.hovered ? UiTheme.hover : UiTheme.surface
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? UiTheme.focus : control.highlighted || control.checked ? UiTheme.accentFill : UiTheme.line
    }
}
