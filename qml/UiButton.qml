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
        color: !control.enabled ? "#8795a6" : control.highlighted || control.checked ? "white" : UiTheme.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 5
        color: !control.enabled ? "#f0f3f6" : control.highlighted || control.checked
            ? (control.down ? "#1c458b" : control.hovered ? "#214f9b" : UiTheme.accent)
            : control.down ? "#e5ebf3" : control.hovered ? "#edf3fc" : UiTheme.surface
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? UiTheme.accent : control.highlighted || control.checked ? UiTheme.accent : UiTheme.line
    }
}
