import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Popup {
    id: loading
    objectName: "classSwitchOverlay"
    parent: Overlay.overlay
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    width: Math.min(420, parent ? parent.width - 32 : 420)
    height: contentItem.implicitHeight + topPadding + bottomPadding
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? (parent.height - height) / 2 : 0
    padding: 24
    enter: Transition {}
    exit: Transition {}
    property var hostWindow: parent ? parent.Window.window : null
    property var pendingAction: null
    property bool waitingForFrame: false
    property bool largeRoster: false
    property string targetName: ""
    property double startedAt: 0

    function begin(name, action, large) {
        if (visible || pendingAction !== null) return
        Qt.inputMethod.commit()
        targetName = name
        pendingAction = action
        largeRoster = !!large
        startedAt = Date.now()
        open()
    }
    function cancel() {
        pendingAction = null
        waitingForFrame = false
        frameTimer.stop()
        finishTimer.stop()
        close()
    }
    function executePending() {
        if (!visible || pendingAction === null) return
        frameTimer.stop()
        var action = pendingAction
        pendingAction = null
        try {
            action()
        } finally {
            // Keep fast switches readable without delaying slower switches.
            finishTimer.interval = Math.max(1, 140 - (Date.now() - startedAt))
            finishTimer.start()
        }
    }
    onOpened: {
        waitingForFrame = true
        if (hostWindow) hostWindow.update()
        // Renderer stalled (window covered or not exposed): act anyway instead of
        // leaving the selected class unapplied behind a loading overlay.
        frameTimer.restart()
    }
    Connections {
        target: loading.hostWindow
        function onFrameSwapped() {
            if (!loading.waitingForFrame) return
            frameTimer.stop()
            loading.waitingForFrame = false
            Qt.callLater(loading.executePending)
        }
        function onVisibleChanged() {
            if (!loading.hostWindow.visible) loading.cancel()
        }
    }
    Timer { id: frameTimer; interval: 250; onTriggered: loading.executePending() }
    Timer { id: finishTimer; onTriggered: loading.close() }
    background: Rectangle { color: "white"; radius: 12; border.color: "#e4e7ec" }
    Overlay.modal: Rectangle { color: "#660f172a" }
    contentItem: ColumnLayout {
        spacing: 12
        BusyIndicator { running: loading.visible; Layout.alignment: Qt.AlignHCenter }
        Label {
            objectName: "classSwitchTitle"
            text: "正在切换 " + loading.targetName
            font.pixelSize: 17; font.bold: true; color: "#17213a"
            wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
        Label {
            objectName: "classSwitchHint"
            text: loading.largeRoster ? "数据较多，加载时间稍长，请稍候…" : "加载数据中，请稍候…"
            color: "#667085"; Layout.alignment: Qt.AlignHCenter
        }
    }
}
