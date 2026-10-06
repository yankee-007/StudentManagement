import QtQuick

Canvas {
    implicitWidth: 10
    implicitHeight: 10
    property bool descending: true
    property color markerColor: UiTheme.muted
    onMarkerColorChanged: requestPaint()
    rotation: descending ? 0 : 180
    onPaint: {
        var context = getContext("2d")
        context.clearRect(0, 0, width, height)
        context.fillStyle = markerColor
        context.beginPath()
        context.moveTo(1, 3)
        context.lineTo(9, 3)
        context.lineTo(5, 7)
        context.closePath()
        context.fill()
    }
}
