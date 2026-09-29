import QtQuick

// ComboBox 在 Qt 6 的 wheelEvent 里无条件 accept 滚轮事件，鼠标停在它上面时
// 外层 Flickable 收不到滚动，页面就滚不动。这里把滚轮接管过来，直接滚动外层页面。
// 点击、拖动仍然落到下面的控件；选项弹层是独立窗口，展开后照常滚动选项。
MouseArea {
    id: guard
    // 不使用 anchors：本组件可能被放进 Layout，用显式宽高覆盖所在区域。
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0
    acceptedButtons: Qt.NoButton
    property Flickable view: null
    // 一格滚轮（angleDelta 通常为 ±120）滚动约 60 像素。
    readonly property real step: 60
    onWheel: function(wheel) {
        if (!guard.view) { wheel.accepted = false; return }
        var delta = wheel.angleDelta.y !== 0 ? wheel.angleDelta.y : wheel.angleDelta.x
        if (delta === 0) { wheel.accepted = false; return }
        var limit = Math.max(0, guard.view.contentHeight - guard.view.height)
        guard.view.contentY = Math.max(0, Math.min(guard.view.contentY - delta / 120 * guard.step, limit))
        wheel.accepted = true
    }
}
