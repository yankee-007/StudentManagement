import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    // Python positions this window using only the primary screen before showing it.
    visible: false
    title: "历史画像维护"
    color: "#f5f7fb"

    property color accent: "#335cff"
    property var selected: backend.selectedStudent
    property var hiddenColumns: backend.defaultHiddenColumns
    property var columnLabels: backend.columnLabels
    property string editorStudentId: ""
    property bool loadingEditor: false
    property var editorItems: []
    function loadEditor() {
        loadingEditor = true
        var changedStudent = editorStudentId !== (selected.student_id || "")
        editorStudentId = selected.student_id || ""
        feedbackInput.text = backend.feedbackDraft(editorStudentId)
        status.currentIndex = Math.max(0, status.indexOfValue(selected.status || "正常"))
        exemption.text = selected.exemption_end || ""
        nextDate.text = selected.next_followup_at || ""
        editorItems = backend.editorFields(detailTabs.currentIndex)
        loadingEditor = false
        if (changedStudent && detailScroll.contentItem) detailScroll.contentItem.contentY = 0
    }
    function saveStatus() {
        return backend.autoSaveStatus(editorStudentId, {status:status.currentText, exemption_end:exemption.text, next_followup_at:nextDate.text})
    }
    function setColumnHidden(index, hidden) {
        var columns = hiddenColumns.slice()
        var position = columns.indexOf(index)
        if (hidden && position < 0) columns.push(index)
        if (!hidden && position >= 0) columns.splice(position, 1)
        hiddenColumns = columns
    }
    onHiddenColumnsChanged: table.forceLayout()

    header: ToolBar {
        height: 64
        background: Rectangle { color: "white"; border.color: "#e5e9f2" }
        RowLayout {
            anchors.fill: parent; anchors.margins: 10; spacing: 12
            Label { text: "学员催办"; font.pixelSize: 21; font.bold: true; color: "#17213a" }
            Button { text: backend.busy ? "正在获取…" : "获取数据"; enabled: !backend.busy; onClicked: backend.fetchData() }
            Button { text: "导入画像表"; enabled: !backend.busy; onClicked: backend.importProfile() }
            BusyIndicator { running: backend.busy; visible: running; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
            Item { Layout.fillWidth: true }
            Label { text: backend.systemDate; color: "#475467"; font.pixelSize: 14; padding: 10; background: Rectangle { color: "#eef2ff"; radius: 8 } }
        }
    }

    RowLayout {
        anchors.fill: parent; anchors.margins: 12; spacing: 12

        Frame {
            Layout.preferredWidth: 138; Layout.minimumWidth: 120; Layout.fillHeight: true
            background: Rectangle { color: "white"; radius: 10; border.color: "#e5e9f2" }
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                Label { text: "视图"; font.bold: true; color: "#667085"; Layout.leftMargin: 8; Layout.bottomMargin: 6 }
                Repeater {
                    model: [
                        {label:"主名单", key:"all"}, {label:"完成统计", key:"statistics"}
                    ]
                    Button {
                        required property var modelData
                        text: modelData.label; Layout.fillWidth: true; flat: true
                        highlighted: (stack.currentIndex === 0) === (modelData.key === "all")
                        onClicked: {
                            stack.currentIndex = modelData.key === "statistics" ? 1 : 0
                            backend.setView("all")
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Label { text: "数据本地保存"; color: "#98a2b3"; font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
            }
        }

        Frame {
            Layout.fillWidth: true; Layout.fillHeight: true
            background: Rectangle { color: "white"; radius: 10; border.color: "#e5e9f2" }
            ColumnLayout {
                anchors.fill: parent; spacing: 10
                RowLayout {
                    visible: stack.currentIndex === 0
                    Layout.fillWidth: true
                    TextField {
                        id: searchInput; Layout.fillWidth: true; placeholderText: "搜索学号、姓名"
                        onTextEdited: searchDelay.restart()
                        Timer { id: searchDelay; interval: 200; onTriggered: backend.setSearch(searchInput.text) }
                    }
                    Button { text: "显示全部"; visible: stack.currentIndex === 0; onClicked: root.hiddenColumns = [] }
                    Button { text: "默认字段"; onClicked: root.hiddenColumns = backend.defaultHiddenColumns }
                    Button {
                        text: "隐藏字段"; visible: stack.currentIndex === 0
                        onClicked: fieldMenu.open()
                        Menu {
                            id: fieldMenu
                            Repeater {
                                model: root.columnLabels
                                MenuItem {
                                    required property int index
                                    required property string modelData
                                    text: modelData
                                    checkable: true
                                    checked: root.hiddenColumns.indexOf(index) < 0
                                    enabled: modelData !== "姓名"
                                    onTriggered: root.setColumnHidden(index, !checked)
                                }
                            }
                        }
                    }
                    Button { text: "刷新"; onClicked: backend.refresh() }
                    Button { text: "导出 XLSX"; enabled: !backend.busy; onClicked: backend.exportXlsx(root.hiddenColumns) }
                }
                StackLayout {
                    id: stack; Layout.fillWidth: true; Layout.fillHeight: true
                    Item {
                        clip: true
                        HorizontalHeaderView { id: studentHeader; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; syncView: table; height: 38 }
                        TableView {
                            id: table; objectName: "studentTable"; model: studentModel; anchors.left: parent.left; anchors.right: parent.right; anchors.top: studentHeader.bottom; anchors.bottom: parent.bottom
                            columnSpacing: 1; rowSpacing: 1; clip: true
                            reuseItems: true
                            columnWidthProvider: function(c) {
                                if (root.hiddenColumns.indexOf(c) >= 0) return 0
                                return root.columnLabels[c].indexOf("反馈") >= 0 ? 260 : 110
                            }
                            rowHeightProvider: function() { return 20 }
                            ScrollBar.horizontal: ScrollBar { }
                            ScrollBar.vertical: ScrollBar { }
                            delegate: Rectangle {
                                required property int row
                                required property int column
                                required property string display
                                required property string studentId
                                implicitWidth: table.columnWidthProvider(column); implicitHeight: 20
                                property bool isSelected: studentId === backend.selectedStudentId
                                color: isSelected ? "#dce6ff" : (row % 2 ? "#fafbff" : "white"); border.color: isSelected ? "#b3c7ff" : "#edf0f5"
                                Text { anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 2; anchors.bottomMargin: 2; font.pixelSize: 10; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; color: "#344054" }
                                TapHandler { onTapped: backend.selectRow(row) }
                            }
                        }
                    }
                    ScrollView {
                        id: statisticsScroll
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: statisticsScroll.availableWidth - 16
                            spacing: 18
                            Label { text: "完成统计"; font.pixelSize: 24; font.bold: true; color: "#17213a"; topPadding: 12 }
                            Label { text: "按最近获取的数据统计，有效请假学员不计入比例"; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Repeater {
                                model: backend.statistics.split("\n")
                                Frame {
                                    required property string modelData
                                    Layout.fillWidth: true
                                    padding: 20
                                    background: Rectangle { color: "#f5f7ff"; radius: 12; border.color: "#e4e9f5" }
                                    Label { width: parent.width; text: modelData; wrapMode: Text.Wrap; font.pixelSize: 16; lineHeight: 1.5; color: "#344054" }
                                }
                            }
                        }
                    }
                }
            }
        }

        Frame {
            id: studentCard
            visible: stack.currentIndex === 0
            Layout.preferredWidth: 350; Layout.minimumWidth: 280; Layout.fillHeight: true
            padding: 12
            background: Rectangle { color: "white"; radius: 10; border.color: "#e5e9f2" }
            ColumnLayout {
                id: cardHeader
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: selected.student_id ? (selected.name || "姓名待补全") : "选择一位学员"; font.pixelSize: 20; font.bold: true; color: "#17213a"; Layout.fillWidth: true; elide: Text.ElideRight }
                    Label { visible: !!selected.student_id; text: status.currentText; color: status.currentText === "请假" ? "#b54708" : "#027a48"; padding: 6; background: Rectangle { radius: 6; color: status.currentText === "请假" ? "#fffaeb" : "#ecfdf3" } }
                }
                RowLayout {
                    Label { text: selected.student_id || "点击左侧表格查看详情"; color: "#667085"; font.pixelSize: 12; Layout.fillWidth: true }
                    ToolButton { text: "‹"; implicitWidth: 30; implicitHeight: 28; enabled: backend.selectedRow > 0; onClicked: backend.moveStudent(-1); ToolTip.visible: hovered; ToolTip.text: "上一位学员" }
                    Label { text: backend.selectedRow >= 0 ? (backend.selectedRow + 1) + "/" + backend.visibleStudentCount : ""; color: "#667085"; font.pixelSize: 11 }
                    ToolButton { text: "›"; implicitWidth: 30; implicitHeight: 28; enabled: backend.selectedRow >= 0 && backend.selectedRow < backend.visibleStudentCount - 1; onClicked: backend.moveStudent(1); ToolTip.visible: hovered; ToolTip.text: "下一位学员" }
                }
                Rectangle {
                    visible: !!selected.profile_fields; Layout.fillWidth: true; implicitHeight: 64; color: "#f5f7ff"; radius: 8
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 10; spacing: 16
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Label { text: "合计完课"; color: "#667085"; font.pixelSize: 11 }
                            Label { text: String((selected.profile_fields || {})["合计完课"] ?? "—") + " 节"; font.pixelSize: 18; font.bold: true; color: "#344054" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Label { text: "合计作业"; color: "#667085"; font.pixelSize: 11 }
                            Label { text: String((selected.profile_fields || {})["合计作业"] ?? "—") + " 节"; font.pixelSize: 18; font.bold: true; color: "#344054" }
                        }
                    }
                }
                Label { visible: !!selected.student_id; text: backend.saveNotice; color: text.indexOf("失败") >= 0 ? "#b42318" : "#027a48"; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                TabBar {
                    id: detailTabs; objectName: "detailTabs"; Layout.fillWidth: true; enabled: !!selected.student_id
                    TabButton { text: "基本资料" }
                    TabButton { text: "学习安排" }
                    TabButton { text: "反馈" }
                    onCurrentIndexChanged: {
                        root.editorItems = backend.editorFields(currentIndex)
                        if (detailScroll.contentItem) detailScroll.contentItem.contentY = 0
                    }
                }
            }
            ScrollView {
                id: detailScroll
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: cardHeader.bottom; anchors.topMargin: 12; anchors.bottom: parent.bottom; clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: detailScroll.availableWidth - 12; spacing: 12
                    enabled: !!selected.student_id
                    Label { visible: detailTabs.currentIndex === 0; text: selected.sync_state || ""; wrapMode: Text.Wrap; Layout.fillWidth: true; color: "#667085"; font.pixelSize: 11 }
                    Label { visible: detailTabs.currentIndex === 2; text: "本次学习反馈"; font.bold: true; color: "#17213a" }
                    TextArea {
                        id: feedbackInput; visible: detailTabs.currentIndex === 2; Layout.fillWidth: true
                        placeholderText: "输入自动存草稿；点击追加形成带日期的正式记录"
                        wrapMode: TextEdit.Wrap; implicitHeight: 110; padding: 10; selectByMouse: true
                        background: Rectangle { radius: 6; color: "#f9fafb"; border.color: feedbackInput.activeFocus ? "#809aff" : "#e4e7ec" }
                        function persistDraft() { if (!root.loadingEditor && root.editorStudentId && activeFocus && !inputMethodComposing) backend.saveFeedbackDraft(root.editorStudentId, text) }
                        onTextChanged: persistDraft()
                        onInputMethodComposingChanged: persistDraft()
                    }
                    Button { visible: detailTabs.currentIndex === 2; text: "追加到今日反馈"; enabled: feedbackInput.text.trim().length > 0; highlighted: true; Layout.fillWidth: true; onClicked: {
                        if (backend.addFeedback(feedbackInput.text)) {
                            root.loadingEditor = true
                            feedbackInput.clear()
                            root.loadingEditor = false
                        }
                    } }
                    Label { visible: detailTabs.currentIndex === 2; text: "历史反馈"; font.bold: true; color: "#344054" }
                    TextArea { visible: detailTabs.currentIndex === 2; text: backend.feedbackHistory || "暂无新增反馈"; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; Layout.fillWidth: true; color: "#475467"; font.pixelSize: 12; padding: 10; background: Rectangle { color: "#f9fafb"; radius: 6 } }
                    Rectangle {
                        visible: !selected.profile_fields
                        Layout.fillWidth: true; implicitHeight: 68; radius: 8; color: "#f3f6fc"
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 12
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: "待催完课"; color: "#667085"; font.pixelSize: 12 }
                                Label { text: (selected.pending_courses || []).length + " 节"; font.pixelSize: 20; font.bold: true; color: "#17213a" }
                            }
                            Rectangle { width: 1; Layout.fillHeight: true; color: "#dde3ee" }
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.leftMargin: 12
                                Label { text: "待催作业"; color: "#667085"; font.pixelSize: 12 }
                                Label { text: (selected.pending_homework || []).length + " 节"; font.pixelSize: 20; font.bold: true; color: "#17213a" }
                            }
                        }
                    }
                    Rectangle { visible: detailTabs.currentIndex === 1; Layout.fillWidth: true; height: 1; color: "#edf0f5" }
                    Label { visible: detailTabs.currentIndex === 1; text: "催办安排"; font.bold: true; font.pixelSize: 15; color: "#17213a" }
                    ComboBox {
                        id: status; visible: detailTabs.currentIndex === 1; Layout.fillWidth: true
                        model: ["正常","请假"]
                        Component.onCompleted: currentIndex = Math.max(0, indexOfValue(selected.status || "正常"))
                        onActivated: {
                            if (currentText === "请假") {
                                var chosen = backend.chooseDate("")
                                if (!chosen) { root.loadEditor(); return }
                                exemption.text = chosen
                                nextDate.text = backend.dayAfter(chosen)
                            } else { exemption.text = ""; nextDate.text = "" }
                            if (!root.saveStatus()) root.loadEditor()
                        }
                    }
                    ColumnLayout {
                        id: exemption
                        property string text: selected.exemption_end || ""
                        visible: detailTabs.currentIndex === 1 && status.currentText === "请假"
                        Layout.fillWidth: true
                        Label { text: "免催结束 *"; color: "#667085"; font.pixelSize: 12 }
                        Button {
                            Layout.fillWidth: true
                            text: exemption.text || "点击选择日期"
                            onClicked: {
                                var chosen = backend.chooseDate(exemption.text)
                                if (chosen !== exemption.text) {
                                    exemption.text = chosen; nextDate.text = backend.dayAfter(chosen)
                                    if (!root.saveStatus()) root.loadEditor()
                                }
                            }
                        }
                        onTextChanged: { if (status.currentText === "请假") nextDate.text = backend.dayAfter(text) }
                    }
                    ColumnLayout {
                        id: nextDate
                        property string text: ""
                        visible: detailTabs.currentIndex === 1; Layout.fillWidth: true
                        Label { text: status.currentText === "请假" ? "下次跟进 · 自动设为结束后一天" : "下次跟进"; color: "#667085"; font.pixelSize: 12 }
                        Button {
                            Layout.fillWidth: true; text: nextDate.text || "选择日期（可选）"; enabled: status.currentText !== "请假"
                            onClicked: { var chosen = backend.chooseDate(nextDate.text); if (chosen !== nextDate.text) { nextDate.text = chosen; if (!root.saveStatus()) root.loadEditor() } }
                        }
                    }
                    Repeater {
                        model: root.editorItems
                        AutoProfileField {
                            required property var modelData
                            studentId: root.editorStudentId
                            caption: modelData.label
                            displayCaption: modelData.displayLabel
                            options: modelData.options
                            initialValue: modelData.value
                            editable: modelData.editable
                        }
                    }
                }
            }
        }
    }

    Snackbar { id: snack }
    Connections {
        target: backend
        function onToast(message) { snack.text = message; snack.open() }
        function onColumnsChanged() { table.forceLayout() }
        function onFeedbackColumnInserted(index) {
            var hidden = root.hiddenColumns.map(function(c) { return c >= index ? c + 1 : c })
            if (root.hiddenColumns.length > 0) hidden.push(index)
            root.hiddenColumns = hidden
        }
        function onSelectedStudentChanged() {
            root.loadEditor()
        }
    }
    Component.onCompleted: loadEditor()
}
