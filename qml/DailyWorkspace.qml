import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    property var daily: backend.dailyWorkspace
    property bool detailOpen: width >= 860
    signal openGroupCenter()
    signal openCampaign()
    spacing: page.height < 560 ? 6 : 10
    onVisibleChanged: { daily.setActive(visible); if (!visible) { goalDialog.close(); listDialog.close() } }
    Component.onCompleted: daily.setActive(visible)
    RowLayout {
        Layout.fillWidth: true
        Label { text: "今日工作台"; font.pixelSize: 20; font.bold: true; color: UiTheme.ink }
        Label { text: daily.goal.id ? "第1～"+daily.goal.lesson+"节 · 考核 "+daily.goal.deadline : "尚未设置班级目标"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
        UiButton { objectName: "dailyEditGoal"; text: "设置目标"; onClicked: if (daily.flushEditor()) goalDialog.open() }
        UiButton { objectName: "dailyFetch"; text: backend.busy ? "刷新中…" : "刷新并核验"; enabled: !backend.busy && !backend.workflow.send_busy; onClicked: backend.fetchData() }
    }
    RowLayout {
        visible: page.height >= 560
        Layout.fillWidth: true
        Repeater {
            model: daily.summary.metrics || []
            UiPanel {
                required property var modelData
                Layout.fillWidth: true; implicitHeight: 104; padding: 10
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: modelData.title; color: UiTheme.muted }
                    Label { text: modelData.value; font.bold: true; font.pixelSize: 24; color: UiTheme.ink }
                    Label { text: "目标 "+modelData.target+" · "+(modelData.need ? "还需"+modelData.need+"人" : "已达到"); color: UiTheme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }
        }
    }
    Label {
        visible: page.height < 560 && daily.summary.valid
        text: (daily.summary.metrics || []).map(function(metric) { return metric.title+" "+metric.value+" / 目标 "+metric.target }).join(" · ")
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink
    }
    Label { objectName: "dailyStatus"; text: daily.summary.notice || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
    Label { text: daily.summary.valid ? "最新批次数据 "+daily.summary.time.replace("T"," ")+" · 在读"+daily.summary.total+"人 · "+(daily.summary.days >= 0 ? "距考核"+daily.summary.days+"天" : "考核已过"+(-daily.summary.days)+"天") : "需要有效累计批次才能计算目标；可继续查看已有承诺。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    UiButton { visible: !(daily.lessonOptions || []).length; text: "进入催办工作台建立首次批次"; onClicked: page.openCampaign() }
    RowLayout {
        Layout.fillWidth: true
        Repeater {
            model: ["达标推进", "承诺复查（"+(daily.summary.reviewCount || 0)+"）", "全部跟进"]
            UiButton {
                required property string modelData
                required property int index
                objectName: "dailyTab"+index
                text: modelData; highlighted: daily.tabIndex===index
                onClicked: daily.selectTab(index)
            }
        }
        Item { Layout.fillWidth: true }
        UiButton { visible: page.width < 860; text: page.detailOpen ? "学员列表" : "学员详情"; onClicked: page.detailOpen=!page.detailOpen }
    }
    RowLayout {
        Layout.fillWidth: true
        UiTextField { objectName: "dailySearch"; Layout.fillWidth: true; placeholderText: "搜索姓名或学号"; Accessible.name: "搜索今日学员"; onTextEdited: daily.search(text) }
        CheckBox { objectName: "dailyCheckAll"; text: "全选"; onClicked: daily.checkAll(checked) }
        UiButton { text: "重新筛选"; onClicked: daily.reapply() }
        UiButton { objectName: "dailyCreateList"; text: "生成群发名单"; enabled: daily.summary.selectedCount > 0; onClicked: if(daily.flushEditor()) listDialog.open() }
    }
    Label { text: daily.summary.cursor+" · 已选"+(daily.summary.selectedCount || 0)+"人"; color: UiTheme.muted }
    RowLayout {
        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
        UiPanel {
            visible: page.width >= 860 || !page.detailOpen
            Layout.fillWidth: true; Layout.fillHeight: true; padding: 8
            ColumnLayout {
                anchors.fill: parent
                HorizontalHeaderView { id: headings; syncView: dailyTable; Layout.fillWidth: true; implicitHeight: 36; clip: true; delegate: Rectangle {
                    required property string display; implicitWidth: 120; implicitHeight: 36; color: UiTheme.stripe
                    Label { anchors.fill: parent; anchors.margins: 6; text: display; color: UiTheme.ink; verticalAlignment: Text.AlignVCenter }
                } }
                TableView {
                    id: dailyTable; objectName: "dailyTable"; Layout.fillWidth: true; Layout.fillHeight: true
                    model: daily.tableModel; clip: true; reuseItems: true; rowSpacing: 1; columnSpacing: 1
                    columnWidthProvider: function(index) { return [145,160,85,290,220][index] }
                    rowHeightProvider: function() { return UiTheme.rowHeight }
                    ScrollBar.horizontal: ScrollBar {}
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        required property int row
                        required property int column
                        required property string display
                        required property string studentId
                        required property bool staleRow
                        implicitWidth: 100; implicitHeight: UiTheme.rowHeight
                        color: studentId===daily.selectedId ? UiTheme.selection : staleRow ? UiTheme.warningSurface : row%2 ? UiTheme.stripe : UiTheme.surface
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 5; anchors.rightMargin: 5; spacing: 4
                            CheckBox { visible: column===0; implicitWidth: 28; Layout.preferredWidth: 28; checked: daily.selectedIds.indexOf(studentId)>=0; Accessible.name: "选择"+display; onClicked: daily.check(studentId,checked) }
                            Label { text: display; Layout.fillWidth: true; elide: Text.ElideRight; color: staleRow ? UiTheme.warning : UiTheme.ink }
                        }
                        TapHandler { onTapped: daily.selectRow(row) }
                    }
                    Label { anchors.centerIn: parent; visible: daily.summary.visibleCount===0; text: "当前没有匹配人员"; color: UiTheme.muted }
                }
            }
        }
        UiPanel {
            visible: page.width >= 860 || page.detailOpen
            Layout.preferredWidth: 340; Layout.minimumWidth: 260; Layout.fillWidth: page.width < 860; Layout.fillHeight: true; padding: 12
            ScrollView { id: detailScroll; objectName: "dailyDetailScroll"; anchors.fill: parent; contentWidth: availableWidth; clip: true
                FollowupEditor { objectName: "dailyEditor"; width: detailScroll.availableWidth; studentId: daily.selectedId }
            }
        }
    }
    Dialog {
        id: goalDialog; objectName: "dailyGoalDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        modal: true; title: "班级累计目标"; width: Math.min(440, page.width-16)
        property string context: ""
        onOpened: {
            context=daily.goalContext
            var goal=daily.goal
            var index=daily.lessonOptions.findIndex(function(value) { return value.value===goal.lesson })
            goalLesson.currentIndex=index>=0 ? index : daily.lessonOptions.length-1
            courseTarget.text=goal.id ? goal.course.toString() : ""
            homeworkTarget.text=goal.id ? goal.homework.toString() : ""
            gapTarget.currentIndex=[5,10,15].indexOf(goal.gap || 5)
            deadline.text=goal.deadline || ""
        }
        contentItem: ColumnLayout {
            Label { text: "每班一个当前周期；改变累计节次会建立新周期，承诺继续保留。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            Label { text: "固定累计范围"; color: UiTheme.ink }
            UiComboBox { id: goalLesson; objectName: "dailyGoalLesson"; model: daily.lessonOptions; textRole: "label"; Layout.fillWidth: true }
            Label { text: "完课率目标（%）"; color: UiTheme.ink }
            UiTextField { id: courseTarget; objectName: "dailyGoalCourse"; placeholderText: "例如90"; Layout.fillWidth: true; selectByMouse: true }
            Label { text: "作业率目标（%）"; color: UiTheme.ink }
            UiTextField { id: homeworkTarget; objectName: "dailyGoalHomework"; placeholderText: "例如85"; Layout.fillWidth: true; selectByMouse: true }
            Label { text: "差值目标"; color: UiTheme.ink }
            UiComboBox { id: gapTarget; model: ["5pp", "10pp", "15pp"]; Layout.fillWidth: true }
            Label { text: "考核日期"; color: UiTheme.ink }
            RowLayout {
                Layout.fillWidth: true
                UiTextField { id: deadline; objectName: "dailyGoalDeadline"; placeholderText: "YYYY-MM-DD"; Layout.fillWidth: true; selectByMouse: true }
                UiButton { text: "日期"; onClicked: deadline.text=backend.chooseDate(deadline.text) }
            }
            Label { text: daily.summary.notice || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "dailySaveGoal"; text: "保存目标"; highlighted: true; enabled: goalLesson.currentIndex>=0; onClicked: {
                    if(daily.saveGoal({context:goalDialog.context,lesson:daily.lessonOptions[goalLesson.currentIndex].value,course:courseTarget.text,homework:homeworkTarget.text,gap:[5,10,15][gapTarget.currentIndex],deadline:deadline.text})) goalDialog.close()
                } }
                UiButton { text: "取消"; onClicked: goalDialog.close() }
            }
        }
    }
    Dialog {
        id: listDialog; objectName: "dailyListDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        modal: true; title: "从今日选择生成群发名单"; width: Math.min(600,page.width-16); height: Math.min(560,page.height+20)
        property var preview: ({keys:[],description:""})
        onOpened: {
            preview=daily.listPreview()
            listTitle.text=backend.workflow.className+" · 今日跟进"
            listFields.load([{type:"text",text:"{姓名}同学，你好！请安排完成：{承诺项目}。约定期限：{期限}。遇到困难请回复，我们一起安排。"}])
        }
        contentItem: ColumnLayout {
            UiTextField { id: listTitle; Layout.fillWidth: true; placeholderText: "名单名称" }
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 100; contentWidth: availableWidth; clip: true
                TextArea { text: listDialog.preview.description; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: UiTheme.ink }
            }
            Label { text: "变量：{姓名}、{学号}、{班期}、{承诺项目}、{期限}"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            ScrollView { id: listScroll; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                MessageFields { id: listFields; width: listScroll.availableWidth }
            }
            Label { text: backend.groupCenter.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "dailyConfirmList"; text: "创建并打开群发中心"; enabled: listDialog.preview.keys.length>0; onClicked: {
                    if(backend.groupCenter.createFromDailySelection(listTitle.text,listFields.values(),listDialog.preview.keys)) { listDialog.close(); page.openGroupCenter() }
                } }
                UiButton { text: "取消"; onClicked: listDialog.close() }
            }
        }
    }
}
