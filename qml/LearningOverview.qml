import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var service: backend.learningOverview
    readonly property var overview: service.view
    readonly property int tab: service.tabIndex
    readonly property var tabOrder: [0, 3, 1, 2]
    function inspectLessonLater(key) {
        var inspectedTab = service.tabIndex
        Qt.callLater(function() {
            if (service.tabIndex === inspectedTab) service.inspectLesson(key)
        })
    }
    onVisibleChanged: { service.setActive(visible); if (!visible) homeworkDialog.close() }
    Component.onCompleted: service.setActive(visible)
    Dialog {
        id: homeworkDialog; objectName: "overviewHomeworkDialog"
        parent: Overlay.overlay; anchors.centerIn: parent; modal: true
        title: "可跟进学员 · 补作业名单"; standardButtons: Dialog.Close
        width: Math.min(root.width - 24, 820); height: Math.min(root.height - 24, 560)
        readonly property var candidates: root.overview.homeworkCandidates || ({rows: [], notice: "", title: ""})
        contentItem: ScrollView {
            id: candidateScroll; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: candidateScroll.availableWidth; spacing: 12
                Label { text: homeworkDialog.candidates.title || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: true; color: UiTheme.ink }
                Label { text: "范围：本批可跟进状态为是、所选累计节次有欠交作业的在读非补位学员。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
                Label { objectName: "overviewHomeworkNotice"; text: homeworkDialog.candidates.notice || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                OverviewTable {
                    objectName: "overviewHomeworkTable"; Layout.fillWidth: true; title: "补齐以下欠交节次"
                    headers: ["序号", "姓名", "学号", "欠交作业节次"]; rows: homeworkDialog.candidates.rows || []
                    emptyMessage: "本批暂无可跟进状态为是、且所选节次有欠交作业的学员。"
                }
            }
        }
    }
    Connections {
        target: service
        function onChanged() {
            if (service.tabIndex !== 3 || !(root.overview.homeworkCandidates || {}).available) homeworkDialog.close()
        }
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Label { text: "学习概览"; font.pixelSize: 22; font.bold: true; color: UiTheme.ink }
            Label { text: backend.workflow.className; color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
            UiButton { objectName: "overviewReload"; text: "重读快照"; onClicked: service.reload(); ToolTip.visible: hovered; ToolTip.text: "读取本地保存的批次与标记，不联网采集" }
        }
        TabBar {
            id: tabs; objectName: "overviewTabs"; Layout.fillWidth: true; currentIndex: root.tabOrder.indexOf(service.tabIndex)
            Repeater {
                model: ["最新数据", "目标追踪", "历史批次", "批次对比"]
                TabButton {
                    required property string modelData; required property int index
                    objectName: "overviewTab" + root.tabOrder[index]; text: modelData; implicitHeight: 36; onClicked: service.selectTab(root.tabOrder[index])
                    Keys.onLeftPressed: { service.selectTab(root.tabOrder[Math.max(0,index-1)]); tabs.itemAt(tabs.currentIndex).forceActiveFocus() }
                    Keys.onRightPressed: { service.selectTab(root.tabOrder[Math.min(3,index+1)]); tabs.itemAt(tabs.currentIndex).forceActiveFocus() }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Home) { service.selectTab(0); tabs.itemAt(0).forceActiveFocus(); event.accepted=true }
                        else if (event.key === Qt.Key_End) { service.selectTab(root.tabOrder[3]); tabs.itemAt(3).forceActiveFocus(); event.accepted=true }
                    }
                }
            }
        }
        Flow {
            visible: root.overview.available && root.tab > 0
            Layout.fillWidth: true; spacing: 10
            Row {
                visible: root.tab===1; spacing: 8
                Label { text: "历史批次"; height: 36; verticalAlignment: Text.AlignVCenter; color: UiTheme.muted }
                UiComboBox { objectName: "overviewHistoryBatch"; width: 265; model: service.batches; textRole: "label"; currentIndex: service.historyIndex; onActivated: service.selectBatch("history", currentIndex); Accessible.name: "历史批次" }
            }
            Row {
                visible: root.tab===2; spacing: 8
                Label { text: "查看批次"; height: 36; verticalAlignment: Text.AlignVCenter; color: UiTheme.muted }
                UiComboBox { objectName: "overviewCompareBatch"; width: 265; model: service.batches; textRole: "label"; currentIndex: service.compareIndex; onActivated: service.selectBatch("compare", currentIndex); Accessible.name: "查看批次" }
            }
            Row {
                visible: root.tab===2; spacing: 8
                Label { text: "对比批次"; height: 36; verticalAlignment: Text.AlignVCenter; color: UiTheme.muted }
                UiComboBox { objectName: "overviewBaselineBatch"; width: 265; model: service.batches; textRole: "label"; currentIndex: service.baselineIndex; onActivated: service.selectBatch("baseline", currentIndex); Accessible.name: "对比批次" }
            }
            Row {
                visible: root.tab===3; spacing: 8
                Label { text: "评估批次"; height: 36; verticalAlignment: Text.AlignVCenter; color: UiTheme.muted }
                UiComboBox { objectName: "overviewGoalBatch"; width: 265; model: service.batches; textRole: "label"; currentIndex: service.goalIndex; onActivated: service.selectBatch("goal", currentIndex); Accessible.name: "评估批次" }
            }
            Row {
                spacing: 8
                Label { text: "评估节次"; height: 36; verticalAlignment: Text.AlignVCenter; color: UiTheme.muted }
                UiComboBox { objectName: "overviewLesson"; width: 178; model: service.lessonOptions; textRole: "label"; currentIndex: service.lessonIndex; displayText: currentIndex<0 ? "暂无有效节次" : currentText; enabled: count>0; onActivated: service.selectLesson(service.lessonOptions[currentIndex].id); Accessible.name: "评估累计节次" }
            }
        }
        ScrollView {
            id: scroll; objectName: "overviewScroll"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: scroll.availableWidth; spacing: 12
                Label { visible: !root.overview.available; text: root.overview.notice; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; padding: 20 }
                ColumnLayout {
                    visible: root.overview.available; Layout.fillWidth: true; spacing: 12
                    Label { text: (root.tab===0 ? "实际最新批次 · " : "")+(root.overview.title || ""); Layout.fillWidth: true; color: UiTheme.ink; font.bold: true; wrapMode: Text.Wrap }
                    Label { text: (root.overview.grade || "")+" · 差值≤5pp优秀 / ≤10pp良好 / ≤15pp及格 / >15pp不合格"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
                    GridLayout {
                        columns: root.width >= 900 ? 4 : 2; Layout.fillWidth: true; columnSpacing: 10; rowSpacing: 10
                        Repeater {
                            model: root.overview.metrics || []
                            Rectangle {
                                required property var modelData; Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: metric.implicitHeight+24
                                color: UiTheme.surface; radius: 8; border.color: UiTheme.line
                                ColumnLayout {
                                    id: metric; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 6
                                    Label { text: modelData.title; color: UiTheme.muted }
                                    Label { text: modelData.value; color: UiTheme.ink; font.pixelSize: 24; font.bold: true }
                                    Label { text: modelData.note; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: UiTheme.muted }
                                }
                            }
                        }
                    }
                    Label { text: root.overview.notice || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
                    ColumnLayout {
                        visible: root.tab===3; Layout.fillWidth: true; spacing: 10
                        Label { text: "目标仅作本次试算，不保存。默认85%是示例；差值试算假设完课人数不变，通过补齐作业降低差值。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
                        Repeater {
                            model: 3
                            RowLayout {
                                required property int index
                                readonly property var goalCard: (root.overview.goalCards || [])[index] || ({title: "", message: ""})
                                Layout.fillWidth: true
                                Label { text: goalCard.title; color: UiTheme.ink; Layout.preferredWidth: 92 }
                                TextField {
                                    objectName: "overviewTarget" + index; visible: index<2; Layout.preferredWidth: 90
                                    text: service.targets[index]; selectByMouse: true; Accessible.name: goalCard.title + "百分比"
                                    onTextEdited: service.setTarget(index,text)
                                }
                                UiComboBox {
                                    objectName: "overviewGapTarget"; visible: index===2; Layout.preferredWidth: 130
                                    model: ["15pp及格", "10pp良好", "5pp优秀"]; currentIndex: ["15","10","5"].indexOf(service.targets[2])
                                    onActivated: service.setTarget(2,["15","10","5"][currentIndex]); Accessible.name: "差值目标"
                                }
                                Label { text: index<2 ? "%" : ""; visible: index<2; color: UiTheme.muted }
                                Label { text: goalCard.message; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                                UiButton {
                                    objectName: index===2 ? "overviewHomeworkCandidatesButton" : ""; visible: index===2; text: "查看补作业名单"
                                    enabled: (root.overview.homeworkCandidates || {}).available === true
                                    onClicked: homeworkDialog.open()
                                }
                            }
                        }
                        Label { text: "固定所选累计节次，观察截至评估批次最近至多5批；缺失快照留空。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
                        Repeater {
                            model: root.overview.trends || []
                            OverviewChart { required property var modelData; required property int index; objectName: "overviewTrend"+index; Layout.fillWidth: true; title: ["累计完课率走势", "累计作业率走势", "累计差值走势"][index]; chart: modelData; categorySuffix: "次" }
                        }
                        OverviewTable { objectName: "overviewTrendTable"; Layout.fillWidth: true; title: "固定节次 · 最近批次走势明细"; headers: ["批次", "累计节次", "在读人数", "完课率", "作业率", "差值", "考核"]; rows: root.overview.trendRows || [] }
                    }
                    GridLayout {
                        visible: root.tab!==3; columns: root.width>=900 ? 2 : 1; Layout.fillWidth: true; columnSpacing: 12; rowSpacing: 12
                        OverviewChart { objectName: "overviewRateChart"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "累计完课率与作业率"; chart: root.overview.rateChart || ({labels:[],series:[],details:[],thresholds:[],suffix:"%"}); selectedKey: root.overview.detailLesson || -1; onPointSelected: function(key) { service.selectLesson(key) }; onPointInspected: function(key) { root.inspectLessonLater(key) } }
                        OverviewChart { objectName: "overviewGapChart"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "累计差值与考核线"; chart: root.overview.gapChart || ({labels:[],series:[],details:[],thresholds:[],suffix:"pp"}); selectedKey: root.overview.detailLesson || -1; onPointSelected: function(key) { service.selectLesson(key) }; onPointInspected: function(key) { root.inspectLessonLater(key) } }
                    }
                    OverviewTable { objectName: "overviewLessonTable"; visible: root.tab!==3; Layout.fillWidth: true; title: "逐节累计明细 · 变化＝查看批次－对比批次"; headers: root.overview.lessonHeaders || []; rows: root.overview.lessonRows || []; selectedKey: root.overview.detailLesson || -1; onRowSelected: function(key) { service.selectLesson(key) } }
                    Label { visible: root.tab!==3; text: root.overview.followup || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink }
                    Label { visible: root.tab!==3; text: (root.overview.completionNotice || "")+" 完成人数、本周是否有退课暂无数据源，留空。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
                    OverviewTable { objectName: "overviewCompletionTable"; visible: root.tab!==3; Layout.fillWidth: true; title: "完课次数 · 各行独立，可跟进不累加低次数"; headers: ["完课次数", "人数", "所占比例", "可跟进人数", "完成人数", "本周是否有退课", "完课率", "完课人数"]; rows: root.overview.completionRows || [] }
                    OverviewTable { objectName: "overviewDistributionTable"; visible: root.tab===2; Layout.fillWidth: true; title: "两批完课次数分布与变化"; headers: root.overview.distributionHeaders || []; rows: root.overview.distributionRows || [] }
                }
            }
        }
    }
}
