import QtQuick
import QtQuick.Controls

Popup {
    id: root
    property alias text: label.text
    x: (parent.width - width) / 2
    y: parent.height - height - 24
    width: Math.min(parent.width - 48, Math.max(320, label.implicitWidth + 40))
    height: 52
    modal: false
    closePolicy: Popup.NoAutoClose
    background: Rectangle { color: UiTheme.ink; radius: 8 }
    contentItem: Label { id: label; color: "white"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    onOpened: timer.restart()
    Timer { id: timer; interval: 3500; onTriggered: root.close() }
}
