import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property string label: ""
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    Layout.fillWidth: true
    spacing: 5
    Label { text: parent.label; color: UiTheme.muted; font.pixelSize: 12 }
    UiTextField {
        id: input
        Layout.fillWidth: true
        implicitHeight: 36
        selectByMouse: true
        background: Rectangle {
            radius: 6
            color: input.enabled ? UiTheme.input : UiTheme.stripe
            border.color: input.activeFocus ? UiTheme.accent : UiTheme.line
        }
    }
}
