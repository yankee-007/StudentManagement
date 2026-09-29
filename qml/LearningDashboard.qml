import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Frame {
    id: panel
    objectName: "learningDashboard"
    required property var stats
    property bool expanded: false
    property var lessons: {
        var result = ({})
        ;(stats.courses || []).forEach(function(row) { result[row.lesson] = { lesson:row.lesson, course:row.completedRate || "—", homework:"—", difference:row.difference || "—" } })
        ;(stats.homework || []).forEach(function(row) {
            if (!result[row.lesson]) result[row.lesson] = { lesson:row.lesson, course:"—", homework:"—", difference:"—" }
            result[row.lesson].homework = row.completedRate || "—"
            result[row.lesson].difference = row.difference || result[row.lesson].difference
        })
        return Object.keys(result).sort(function(a,b) { return Number(a)-Number(b) }).map(function(key) { return result[key] })
    }
    Layout.fillWidth: true
    padding: 10
    background: Rectangle { color: "white"; radius: 8; border.color: "#e4e7ec" }
    ColumnLayout {
        anchors.fill: parent
        spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Label { text: "本次催办-学习数据看板"; font.bold: true; color: "#17213a" }
            Label { text: panel.stats.available ? "在读 " + panel.stats.total + " 人 · 完整获取 " + panel.stats.matched + " 人" : "暂无快照"; color: "#667085"; Layout.fillWidth: true }
            ToolButton {
                text: "计算说明"; hoverEnabled: true
                ToolTip.visible: hovered || down
                ToolTip.timeout: -1
                ToolTip.text: "分母：创建该批次时的全部在读学员（含请假，不含退课、冻结、补位）。\n第 N 节累计完课率＝第 1～N 节课程全部完成的人数 ÷ 在读人数 × 100%；累计作业率同理。\n差值＝累计完课率 − 累计作业率；负值表示作业率更高。\n无有效数据或旧版快照无法还原的指标显示 —。"
            }
            ToolButton { text: panel.expanded ? "收起" : "展开"; onClicked: panel.expanded = !panel.expanded }
        }
        Label {
            visible: panel.expanded; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 11; color: "#667085"
            text: panel.stats.notice
        }
        RowLayout {
            visible: panel.expanded; Layout.fillWidth: true; spacing: 0
            Repeater {
                model: ["节次","累计完课率","累计作业率","差值"]
                Label { required property string modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 11; color: "#475467" }
            }
        }
        ListView {
            id: list; objectName: "learningDashboardList"
            visible: panel.expanded; Layout.fillWidth: true; Layout.preferredHeight: 96
            clip: true; model: panel.lessons
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: list.width; height: 24; color: index % 2 ? "#f8faff" : "#ffffff"
                RowLayout {
                    anchors.fill: parent; spacing: 0
                    Repeater {
                        model: ["第" + modelData.lesson + "节",modelData.course,modelData.homework,modelData.difference]
                        Label { required property var modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12; color: "#344054" }
                    }
                }
            }
            Label { anchors.centerIn: parent; visible: list.count === 0; text: !panel.stats.available ? "暂无看板快照" : panel.stats.total ? "创建该批次时暂无已开启节次的有效数据" : "该批次暂无在读学员"; color: "#98a2b3" }
        }
    }
}
