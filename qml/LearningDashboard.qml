import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

UiPanel {
    id: panel
    objectName: "learningDashboard"
    required property var stats
    property bool expanded: false
    property bool compact: false
    property int tab: 0
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
    // 完课次数分栏：stats.completion 由 app/dashboard.py 计算（快照口径），
    // 「可跟进人数」由 Workflow 按各批次独立人工标记补算（未填写、是、否，仅是计入）。
    property var completionRows: {
        if (tab !== 1) return []
        var buckets = (stats.completion && stats.completion.courses) || []
        return buckets.map(function(row) {
            return { count: String(row.count), people: String(row.people), ratio: row.ratio || "—",
                     followable: row.followable === undefined ? "—" : String(row.followable),
                     done: "", drop: "", finishRate: row.cumulativeRate || "—", finishCount: String(row.cumulative) }
        })
    }
    function cumulativeText(key) {
        if (!stats.available) return "—"
        var value = stats.cumulative ? stats.cumulative[key] : undefined
        return value === undefined ? "—" : String(value)
    }
    Layout.fillWidth: true
    padding: panel.compact ? 6 : 10
    background: Rectangle { color: UiTheme.surface; radius: 8; border.color: UiTheme.line }
    ColumnLayout {
        anchors.fill: parent
        spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Label { text: "学习概览"; font.bold: true; color: UiTheme.ink }
            RowLayout {
                Layout.fillWidth: true; spacing: panel.width < 700 ? 8 : 16
                Repeater {
                    model: [{key:"total",label:"在读",value:panel.stats.available ? String(panel.stats.total) : "—"},
                            {key:"courses",label:panel.width < 700 ? "完课" : "累计完课",value:panel.cumulativeText("courses")},
                            {key:"homework",label:panel.width < 700 ? "作业" : "累计作业",value:panel.cumulativeText("homework")}]
                    Label {
                        required property var modelData
                        objectName: "learningMetric-" + modelData.key
                        text: modelData.label + " " + modelData.value + " 人"
                        font.pixelSize: 13; color: UiTheme.muted
                        Accessible.name: text
                        ToolTip.visible: metricHover.hovered
                        ToolTip.text: "在读、累计完课与累计作业人数；完整获取 " + (panel.stats.matched || 0) + " 人"
                        HoverHandler { id: metricHover }
                    }
                }
                Item { Layout.fillWidth: true }
            }
            ToolButton {
                text: "计算说明"; hoverEnabled: true
                ToolTip.visible: hovered || down
                ToolTip.timeout: -1
                ToolTip.text: "分母：该看板数据对应的全部在读学员（含请假，不含退课、冻结、补位）；最新批次跟随最近一次获取刷新，历史批次为创建当时。\n第 N 节累计完课率＝第 1～N 节课程全部完成的人数 ÷ 在读人数 × 100%；累计作业率同理。\n差值＝累计完课率 − 累计作业率；负值表示作业率更高。\n累计完课人数／累计作业人数＝第 1～N 节（N＝已开课节次）全部完成课程／作业的人数。\n完课次数分栏：按每人在本批已开课节次中已完成课程的节数分桶（0 … N），人数＝该桶人数，所占比例＝人数 ÷ 在读人数，完课率＝完成节数不少于该行的累计人数 ÷ 在读人数，完课人数就是该累计人数；已完成节数超过已开课节次者并入 N 行。\n「可跟进人数」＝该桶中在读、非补位且「可跟进状态＝是」的学员（按本批人工标记统计）。\n无有效数据或旧版快照无法还原的指标显示 —；「完成人数」「本周是否有退课」暂无数据来源，暂不显示。"
            }
            ToolButton { text: panel.expanded ? "收起" : "展开"; onClicked: panel.expanded = !panel.expanded }
        }
        Label {
            visible: panel.expanded; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: UiTheme.muted
            text: panel.stats.notice
        }
        RowLayout {
            visible: panel.expanded; Layout.fillWidth: true; spacing: 6
            Repeater {
                model: ["现有表格 · 累计率", "完课次数"]
                UiButton {
                    required property var modelData
                    required property int index
                    text: modelData
                    checkable: true; checked: panel.tab === index
                    font.pixelSize: 12
                    onClicked: panel.tab = index
                }
            }
            Item { Layout.fillWidth: true }
        }
        RowLayout {
            visible: panel.expanded && panel.tab === 0; Layout.fillWidth: true; spacing: 0
            Repeater {
                model: ["节次","累计完课率","累计作业率","差值"]
                Label { required property string modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12; color: UiTheme.muted }
            }
        }
        ListView {
            id: list; objectName: "learningDashboardList"
            visible: panel.expanded && panel.tab === 0; Layout.fillWidth: true; Layout.preferredHeight: 96
            clip: true; model: panel.lessons
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: list.width; height: 24; color: index % 2 ? UiTheme.stripe : UiTheme.surface
                RowLayout {
                    anchors.fill: parent; spacing: 0
                    Repeater {
                        model: ["第" + modelData.lesson + "节",modelData.course,modelData.homework,modelData.difference]
                        Label { required property var modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12; color: UiTheme.ink }
                    }
                }
            }
            Label { anchors.centerIn: parent; visible: list.count === 0; text: !panel.stats.available ? "暂无看板快照" : panel.stats.total ? "创建该批次时暂无已开启节次的有效数据" : "该批次暂无在读学员"; color: UiTheme.subtle }
        }
        RowLayout {
            visible: panel.expanded && panel.tab === 1; Layout.fillWidth: true; spacing: 0
            Repeater {
                model: ["完课次数","人数","所占比例","可跟进人数","完成人数","本周是否有退课","完课率","完课人数"]
                Label { required property string modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12; color: UiTheme.muted }
            }
        }
        ListView {
            id: completionList; objectName: "learningDashboardCompletionList"
            visible: panel.expanded && panel.tab === 1; Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, 180)
            clip: true; model: panel.completionRows
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: completionList.width; height: 24; color: index % 2 ? UiTheme.stripe : UiTheme.surface
                RowLayout {
                    anchors.fill: parent; spacing: 0
                    Repeater {
                        model: [modelData.count,modelData.people,modelData.ratio,modelData.followable,modelData.done,modelData.drop,modelData.finishRate,modelData.finishCount]
                        Label { required property var modelData; text: modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 12; color: UiTheme.ink }
                    }
                }
            }
            Label {
                anchors.centerIn: parent; visible: completionList.count === 0; horizontalAlignment: Text.AlignHCenter; color: UiTheme.subtle
                text: !panel.stats.available ? "暂无看板快照" : panel.stats.total ? "创建该批次时暂无已开启节次的有效数据" : "该批次暂无在读学员"
            }
        }
    }
}
