import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property string label: ""
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    Layout.fillWidth: true
    spacing: 5
    Label { text: parent.label; color: "#667085"; font.pixelSize: 12 }
    TextField {
        id: input
        Layout.fillWidth: true
        implicitHeight: 36
        selectByMouse: true
        background: Rectangle {
            radius: 6
            color: input.enabled ? "#f9fafc" : "#f2f4f7"
            border.color: input.activeFocus ? "#335cff" : "#e4e7ec"
        }
    }
}
