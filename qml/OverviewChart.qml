import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var chart: ({labels: [], series: [], details: [], thresholds: [], suffix: "%"})
    property string title: ""
    property string categoryPrefix: "第"
    property string categorySuffix: "节"
    property int selectedKey: -1
    property int inspected: -1
    property int startIndex: 0
    property string previousLabels: ""
    property int endIndex: Math.max(0, chart.labels.length - 1)
    readonly property real minimum: {
        var low = 0
        if (chart.suffix === "pp") for (var s of chart.series) for (var v of s.values) if (v !== null && v !== undefined && isFinite(v)) low = Math.min(low, v)
        return Math.floor(low / 5) * 5
    }
    readonly property real maximum: {
        if (chart.suffix === "%") return 100
        var high = 20
        for (var s of chart.series) for (var v of s.values) if (v !== null && v !== undefined && isFinite(v)) high = Math.max(high, v)
        return Math.ceil(high / 5) * 5 + 5
    }
    readonly property int detailIndex: chart.labels.indexOf(selectedKey) >= 0 ? chart.labels.indexOf(selectedKey) : inspected
    signal pointSelected(int key)
    signal pointInspected(int key)
    color: UiTheme.surface; radius: 8; border.color: activeFocus ? UiTheme.accent : UiTheme.line
    implicitHeight: content.implicitHeight + 24
    activeFocusOnTab: true
    Accessible.role: Accessible.Chart
    Accessible.name: title + "。左右键查看数据，回车选择；下方滑块调整范围。"
    Accessible.description: inspected >= 0 ? chart.details[inspected] || "" : ""
    function doPaint() { paint.requestPaint() }
    function redraw() { Qt.callLater(doPaint) }
    function inspect(index) {
        inspected = Math.max(startIndex, Math.min(endIndex, index))
        if (chart.labels.length) pointInspected(chart.labels[inspected])
        redraw()
    }
    Keys.onLeftPressed: inspect(inspected < 0 ? endIndex : inspected - 1)
    Keys.onRightPressed: inspect(inspected < 0 ? startIndex : inspected + 1)
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Home) { inspect(startIndex); event.accepted=true }
        else if (event.key === Qt.Key_End) { inspect(endIndex); event.accepted=true }
    }
    Keys.onReturnPressed: if (inspected >= 0 && chart.labels.length) pointSelected(chart.labels[inspected])
    onChartChanged: {
        var labels = JSON.stringify(chart.labels)
        if (labels !== previousLabels) {
            startIndex = 0; endIndex = Math.max(0, chart.labels.length - 1); inspected = -1
            previousLabels = labels
        }
        redraw()
    }
    onSelectedKeyChanged: redraw()
    onStartIndexChanged: redraw()
    onEndIndexChanged: redraw()
    onMinimumChanged: redraw()
    onMaximumChanged: redraw()
    Connections {
        target: UiTheme
        function onDarkModeChanged() { root.redraw() }
    }
    ColumnLayout {
        id: content; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 8
        Label { text: root.title; font.bold: true; color: UiTheme.ink; Layout.fillWidth: true }
        Flow {
            Layout.fillWidth: true; spacing: 10
            Repeater {
                model: root.chart.series
                Row {
                    required property var modelData
                    spacing: 4
                    Label { text: modelData.dashed ? "┄┄" : "━━"; color: UiTheme.chartColor(modelData.color); font.bold: true }
                    Label { text: modelData.name; color: UiTheme.muted; font.pixelSize: 12 }
                }
            }
        }
        Canvas {
            id: paint; Layout.fillWidth: true; Layout.preferredHeight: 190
            property real leftEdge: 52
            property real rightEdge: width - 14
            property real topEdge: 12
            property real bottomEdge: height - 28
            function plotX(i) { return root.endIndex === root.startIndex ? (leftEdge + rightEdge)/2 : leftEdge+(rightEdge-leftEdge)*(i-root.startIndex)/(root.endIndex-root.startIndex) }
            function plotY(value) { return bottomEdge-(value-root.minimum)/(root.maximum-root.minimum)*(bottomEdge-topEdge) }
            onWidthChanged: root.redraw()
            onPaint: {
                var ctx = getContext("2d"); ctx.reset(); ctx.clearRect(0,0,width,height)
                ctx.font = "12px '" + Qt.application.font.family + "'"
                ctx.textAlign = "right"; ctx.fillStyle = UiTheme.muted
                for (var t = 0; t <= 4; ++t) {
                    var value = root.minimum + (root.maximum-root.minimum)*t/4
                    var yv = plotY(value)
                    ctx.beginPath(); ctx.strokeStyle = UiTheme.chartGrid; ctx.moveTo(leftEdge,yv); ctx.lineTo(rightEdge,yv); ctx.stroke()
                    ctx.fillText(Math.round(value) + root.chart.suffix, leftEdge-7, yv+4)
                }
                for (var threshold of root.chart.thresholds) {
                    ctx.beginPath(); ctx.strokeStyle = threshold <= 5 ? UiTheme.chartSuccess : threshold <= 10 ? UiTheme.accent : UiTheme.warning
                    ctx.setLineDash([4,4]); ctx.moveTo(leftEdge,plotY(threshold)); ctx.lineTo(rightEdge,plotY(threshold)); ctx.stroke(); ctx.setLineDash([])
                    ctx.textAlign = "left"; ctx.fillStyle=ctx.strokeStyle
                    if (root.chart.thresholds.length !== 3 || Math.abs(plotY(threshold)-plotY(threshold+5)) >= 14)
                        ctx.fillText((root.chart.thresholds.length === 3 ? (threshold===5 ? "优秀 " : threshold===10 ? "良好 " : "及格 ") : "目标 ")+threshold+root.chart.suffix, leftEdge+4, plotY(threshold)-3)
                }
                if (!root.chart.labels.length) return
                ctx.textAlign="center"; ctx.fillStyle=UiTheme.muted
                var stride = Math.max(1, Math.ceil((root.endIndex-root.startIndex+1)/Math.max(2,(rightEdge-leftEdge)/55)))
                for (var i=root.startIndex; i<=root.endIndex; ++i) {
                    if ((i-root.startIndex)%stride===0 || i===root.endIndex) ctx.fillText(root.categoryPrefix+root.chart.labels[i]+root.categorySuffix, plotX(i), height-8)
                }
                for (var series of root.chart.series) {
                    ctx.beginPath(); ctx.strokeStyle=UiTheme.chartColor(series.color); ctx.lineWidth=2; ctx.setLineDash(series.dashed ? [6,4] : [])
                    var move=true
                    for (var j=root.startIndex; j<=root.endIndex; ++j) {
                        var v=series.values[j]
                        if (v===null || v===undefined) { move=true; continue }
                        if (move) ctx.moveTo(plotX(j),plotY(v)); else ctx.lineTo(plotX(j),plotY(v))
                        move=false
                    }
                    ctx.stroke(); ctx.setLineDash([])
                    for (var k=root.startIndex; k<=root.endIndex; ++k) if (series.values[k]!==null && series.values[k]!==undefined) {
                        ctx.beginPath(); ctx.arc(plotX(k),plotY(series.values[k]),series.dashed ? 4 : 3,0,Math.PI*2)
                        ctx.fillStyle=series.dashed ? UiTheme.surface : UiTheme.chartColor(series.color); ctx.fill(); ctx.stroke()
                    }
                }
                var selected = root.chart.labels.indexOf(root.selectedKey)
                var cursor=selected >= 0 ? selected : root.inspected
                if (cursor>=root.startIndex && cursor<=root.endIndex) {
                    ctx.beginPath(); ctx.strokeStyle=UiTheme.muted; ctx.setLineDash([2,3]); ctx.moveTo(plotX(cursor),topEdge); ctx.lineTo(plotX(cursor),bottomEdge); ctx.stroke()
                }
            }
            MouseArea {
                anchors.fill: parent; hoverEnabled: true
                function indexAt(px) { return root.endIndex===root.startIndex ? root.startIndex : Math.round(root.startIndex+(Math.max(paint.leftEdge, Math.min(paint.rightEdge,px))-paint.leftEdge)/(paint.rightEdge-paint.leftEdge)*(root.endIndex-root.startIndex)) }
                onPositionChanged: function(mouse) { if (root.chart.labels.length) root.inspect(indexAt(mouse.x)) }
                onClicked: function(mouse) { root.forceActiveFocus(); if(root.chart.labels.length) { root.inspect(indexAt(mouse.x)); root.pointSelected(root.chart.labels[root.inspected]) } }
                ToolTip.visible: containsMouse && root.inspected >= 0 && root.chart.labels.length > 0
                ToolTip.text: root.chart.details[root.inspected] || ""
                ToolTip.delay: 100
            }
            Label { anchors.centerIn: parent; visible: root.chart.labels.length === 0; text: "暂无有效累计快照"; color: UiTheme.muted }
        }
        Flow {
            Layout.fillWidth: true; spacing: 12
            Repeater {
                model: root.chart.thresholds
                Label {
                    required property var modelData
                    font.pixelSize: 12
                    text: "┄ " + (root.chart.thresholds.length === 3 ? (modelData===5 ? "优秀 " : modelData===10 ? "良好 " : "及格 ") : "目标 ") + modelData + root.chart.suffix
                    color: modelData <= 5 ? UiTheme.chartSuccess : modelData <= 10 ? UiTheme.accent : UiTheme.warning
                }
            }
        }
        RangeSlider {
            objectName: root.objectName + "Range"
            Layout.fillWidth: true; from: 0; to: Math.max(1, root.chart.labels.length - 1); stepSize: 1; snapMode: RangeSlider.SnapAlways
            enabled: root.chart.labels.length > 1
            first.value: Math.min(second.value, root.startIndex); second.value: Math.min(to, root.endIndex)
            first.onMoved: root.startIndex = Math.round(first.value)
            second.onMoved: root.endIndex = Math.round(second.value)
            Accessible.name: "图表显示范围"
        }
        Label {
            Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: UiTheme.muted
            text: root.detailIndex >= 0 ? root.chart.details[root.detailIndex] || "" : "悬浮或点击查看同节次明细；左右键查看，回车选择。拖动滑块缩放范围。"
        }
    }
}
