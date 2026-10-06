import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    visible: false
    title: "学员管理 · 催办与画像"
    color: "#f5f7fb"
    property var wf: backend.workflow
    property var sender: backend.groupCenter
    property var restartService: typeof restartController !== "undefined" ? restartController : null
    onClosing: function(close) {
        if (root.moduleIndex === 4 && !backend.groupCenter.active) groupCenterPage.saveSettings()
        if (root.moduleIndex === 5 && !backend.remarkRenamer.active) remarkRenamerPage.saveOptions()
        if (backend.contactOpener.active) { close.accepted=false; snack.text="正在打开联系人，请等待完成后关闭"; snack.open() }
        else if (sender.active) { close.accepted=false; sender.stop(); snack.text="正在结束发送，请等待当前联系人处理完成后再关闭"; snack.open() }
        else if (backend.remarkRenamer.active) { close.accepted=false; backend.remarkRenamer.stop(); snack.text="正在结束备注批改，请等待当前联系人处理完成后再关闭"; snack.open() }
        else { profileFloat.close(); campaignFloat.close() }
    }
    property int moduleIndex: 0
    function switchModule(index) {
        moduleIndex = index
        if (index === 1) backend.profilesModule.activate()
        else if (index === 0) wf.activate()
        else if (index === 2) backend.termsModule.activate()
        else if (index === 3) backend.settingsModule.refresh()
        else if (index === 4) backend.groupCenter.refresh()
        else if (index === 5) backend.remarkRenamer.reload()
    }
    CampaignExportDialog { id: batchExportDialog; workflow: root.wf }
    CampaignFieldDialog { id: fieldDialog; workflow: root.wf }
    FloatingCampaign { id: campaignFloat }
    function openColumn(index) { columnDialog.openFor(index) }
    function applyFilter() { wf.filterRows(viewBox.currentValue || "all", search.text) }
    ClassSwitchOverlay { id: classSwitch }
    header: ToolBar {
        background: Rectangle { color: "white"; border.color: "#e4e7ec" }
        RowLayout {
            anchors.fill: parent; anchors.margins: 8
            Button { text: "催办工作台"; highlighted: root.moduleIndex === 0; onClicked: root.switchModule(0) }
            Button { text: "学员画像"; highlighted: root.moduleIndex === 1; onClicked: root.switchModule(1) }
            Button { text: "班期学员"; highlighted: root.moduleIndex === 2; onClicked: root.switchModule(2) }
            Button { text: "设置"; highlighted: root.moduleIndex === 3; onClicked: root.switchModule(3) }
            Button { text: "群发中心"; highlighted: root.moduleIndex === 4; onClicked: root.switchModule(4) }
            Button { text: "备注批改"; highlighted: root.moduleIndex === 5; onClicked: root.switchModule(5) }
            ComboBox {
                objectName: "classSelector"
                popup.objectName: "classSelectorPopup"
                visible: root.moduleIndex === 0 || root.moduleIndex === 1 || root.moduleIndex === 5
                model: wf.classes; currentIndex: wf.classIndex
                enabled: !backend.busy && !backend.termsModule.busy && !sender.active && !wf.sender.active && !backend.contactOpener.active && !backend.remarkRenamer.active
                Layout.preferredWidth: 125
                onActivated: function(index) {
                    popup.close()
                    if (index === wf.classIndex) return
                    var name = wf.classes[index]
                    var size = wf.classRosterSize(index)
                    classSwitch.begin(name, function() { wf.selectClass(index) }, size < 0 || size >= 300)
                }
            }
            Item { Layout.fillWidth: true }
            Button {
                objectName: "debugRestartButton"
                text: "调试重启"
                visible: root.restartService !== null
                enabled: !backend.busy && !backend.termsModule.busy && !backend.settingsModule.busy && !sender.active && !wf.sender.active && !backend.contactOpener.active && !backend.remarkRenamer.active
                ToolTip.visible: hovered
                ToolTip.text: "退出后重新启动整个程序，加载已保存的代码修改"
                onClicked: {
                    Qt.inputMethod.commit()
                    root.restartService.requestRestart()
                }
            }
            Label { text: backend.systemDate; color: "#667085"; font.pixelSize: 12 }
        }
    }
    ColumnLayout {
        visible: root.moduleIndex === 0
        anchors.fill: parent; anchors.margins: 12; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: wf.dataNote; color: "#667085"; Layout.fillWidth: true; elide: Text.ElideRight }
            Button { text: "采集异常明细"; visible: backend.fetchIssues.length > 0; onClicked: fetchIssuesDialog.open() }
            Button { objectName: "fetchLearningButton"; visible: root.moduleIndex === 0 && (wf.batchIndex < 0 || wf.canEdit); text: backend.busy ? "刷新中…" : "刷新数据"; enabled: !backend.busy && !backend.termsModule.busy && !sender.active; onClicked: backend.fetchData() }
            Button { objectName: "createCampaignButton"; text: backend.busy ? "正在获取最新数据…" : "新建催办"; highlighted: true; enabled: !backend.busy && !backend.termsModule.busy && !sender.active; onClicked: createDialog.open() }
        }
        LearningDashboard { stats: wf.dashboard }
        Frame {
            Layout.fillWidth: true; padding: 10
            background: Rectangle { color: "white"; radius: 8; border.color: "#e4e7ec" }
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "催办批次"; color: "#475467" }
                    ComboBox { model: wf.batches; textRole: "label"; currentIndex: wf.batchIndex; displayText: wf.batchIndex < 0 ? "当前全班名单（尚未建立批次）" : currentText; Layout.fillWidth: true; enabled: !backend.busy && wf.batchIndex >= 0 && !sender.active; onActivated: wf.selectBatch(currentIndex) }
                    Button { text: "导出全班 XLSX"; enabled: wf.batchIndex >= 0; onClicked: batchExportDialog.open() }
                }
                Label { text: wf.summary; color: "#344054"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Label { visible: wf.batchIndex >= 0 && !wf.canEdit; text: "历史批次只读：学习数据保持当时快照，不受后续获取影响。"; color: "#b54708"; font.pixelSize: 12 }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            Frame {
                Layout.fillWidth: true; Layout.fillHeight: true; padding: 10
                background: Rectangle { color: "white"; radius: 10; border.color: "#e4e7ec" }
                ColumnLayout {
                    anchors.fill: parent; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        ComboBox {
                            id: viewBox; objectName: "campaignViewSelector"; textRole: "label"; valueRole: "key"; Layout.preferredWidth: 125
                            displayText: currentText
                            model: [{label:"全班快照",key:"all"},{label:"本次催办",key:"targets"},{label:"待反馈",key:"pending"}]
                            onActivated: root.applyFilter()
                        }
                        TextField { id: search; placeholderText: "学号、姓名、备注"; Layout.fillWidth: true; onTextEdited: searchTimer.restart(); Timer { id: searchTimer; interval: 180; onTriggered: root.applyFilter() } }
                        Button { objectName: "createCampaignList"; text: "生成群发名单"; enabled: wf.canEdit && !sender.active && !backend.busy && wf.recipientKeys.length > 0; onClicked: templateDialog.open() }
                        Button { objectName: "markUnrepliedButton"; text: "批量未回复"; visible: viewBox.currentValue === "targets" || viewBox.currentValue === "pending"; enabled: wf.canEdit && wf.visibleCount > 0; onClicked: noReplyDialog.open() }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "当前显示 " + wf.visibleCount + " 人" + (wf.hasStale ? " · " + wf.staleCount + " 人已不符合当前筛选" : " · 点击表头筛选或排序；修改数据不会自动移出行") + (wf.cursorText.length > 0 ? " · " + wf.cursorText : ""); color: wf.hasStale ? "#b54708" : "#667085"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                        Button { objectName: "campaignReapplyFilter"; text: "重新应用筛选"; visible: wf.hasStale; onClicked: wf.reapplyFilters() }
                        Button { text: "管理字段"; onClicked: fieldDialog.open() }
                        Button { text: "聊天跟随浮窗"; enabled: wf.canEdit; onClicked: campaignFloat.show() }
                        Button { text: "清除列筛选／排序"; visible: wf.hasColumnQuery; onClicked: wf.clearColumnQuery() }
                    }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        HorizontalHeaderView {
                            id: header; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 34; syncView: table
                            delegate: Rectangle {
                                required property int column
                                required property var display
                                implicitHeight: 34; implicitWidth: 90
                                property bool filtered: wf.filteredColumns.indexOf(column) >= 0
                                color: filtered ? "#e4ecff" : "#f2f4f7"
                                Text {
                                    anchors.fill: parent; anchors.margins: 6; verticalAlignment: Text.AlignVCenter
                                    text: display + (wf.sortColumnIndex === column ? (wf.sortDescending ? " ↓" : " ↑") : " ▾") + (parent.filtered ? " •" : "")
                                    elide: Text.ElideRight; font.pixelSize: 11; color: "#344054"
                                }
                                TapHandler { onTapped: root.openColumn(column) }
                            }
                        }
                        TableView {
                            id: table; objectName: "studentTable"; model: wf.tableModel
                            anchors.top: header.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                            clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                            columnWidthProvider: function(c) {
                                var fields = wf.managedFields
                                if (c < 0 || c >= fields.length || !fields[c].show_column) return 0
                                var key = fields[c].field_id
                                return key === "student_id" ? 120 : (key === "feedback" || key === "courses" || key === "homework") ? 180 : 100
                            }
                            rowHeightProvider: function() { return 20 }
                            ScrollBar.horizontal: ScrollBar { }
                            ScrollBar.vertical: ScrollBar { }
                            delegate: Rectangle {
                                required property int row
                                required property int column
                                required property string display
                                required property string studentId
                                required property bool expiredCell
                                required property bool staleRow
                                implicitHeight: 20; implicitWidth: 90
                                color: studentId === wf.selected.student_id ? "#dce6ff" : staleRow ? "#fff4e5" : row % 2 ? "#f8faff" : "white"
                                Text { anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 6; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 10; color: expiredCell ? "#98a2b3" : staleRow ? "#b54708" : "#344054" }
                                TapHandler { onTapped: wf.selectRow(row) }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: wf.visibleCount === 0; text: search.text.length > 0 || wf.hasColumnQuery ? "没有匹配的学员，请调整搜索或列筛选" : wf.batchIndex < 0 ? "暂无符合条件的学员；班期名单获取后自动同步" : "当前筛选下没有学员"; horizontalAlignment: Text.AlignHCenter; color: "#98a2b3"; lineHeight: 1.6 }
                    }
                }
            }
            Frame {
                Layout.preferredWidth: 330; Layout.minimumWidth: 260; Layout.fillHeight: true; padding: 12
                background: Rectangle { color: "white"; radius: 10; border.color: "#e4e7ec" }
                CampaignDetail { objectName: "mainCampaignDetail"; anchors.fill: parent; service: wf; workflow: wf }
            }
        }
    }
    ProfileModule { objectName: "profileModule"; visible: root.moduleIndex === 1; anchors.fill: parent; anchors.margins: 12; openFloatingProfile: function() { profileFloat.show() }; onOpenGroupCenter: root.switchModule(4) }
    TermModule { visible: root.moduleIndex === 2; anchors.fill: parent; anchors.margins: 12 }
    SettingsModule { visible: root.moduleIndex === 3; anchors.fill: parent; anchors.margins: 12 }
    GroupCenter { id: groupCenterPage; visible: root.moduleIndex === 4; anchors.fill: parent; anchors.margins: 12 }
    RemarkRenamer { id: remarkRenamerPage; visible: root.moduleIndex === 5; anchors.fill: parent; anchors.margins: 12 }
    ProfileFilterDialog { id: columnDialog; filterObjectName: "campaignColumnFilter"; profiles: root.wf }
    Dialog {
        id: createDialog; anchors.centerIn: parent; modal: true; title: "建立新的催办批次"; standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "将从两个平台获取当前班期的最新学习数据，核对全部在读学员后创建批次。\n有学员数据缺失或姓名不符时暂停建批，可查看采集异常明细。"; lineHeight: 1.5 }
        onAccepted: backend.createCampaign()
    }
    Dialog {
        id: fetchIssuesDialog; anchors.centerIn: parent; modal: true
        title: "当前班期 · 最近一次采集异常"; standardButtons: Dialog.Close
        width: Math.min(root.width - 40, 680); height: Math.min(root.height - 40, 440)
        ScrollView {
            anchors.fill: parent
            TextArea { text: backend.fetchIssues; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap }
        }
    }
    Dialog {
        id: templateDialog; objectName: "campaignListDialog"; anchors.centerIn: parent; modal: true
        title: "从当前筛选生成群发名单"; width: Math.min(root.width-40,650); height: Math.min(root.height-40,590)
        property var recordKeys: []
        onOpened: {
            recordKeys=wf.recipientKeys.slice()
            groupTitle.text=wf.className + " · 催办筛选名单"
            messageFields.load([{type:"text",text:"{姓名}同学，你好！"}])
            namesOnly.checked=false
        }
        ColumnLayout {
            anchors.fill: parent
            TextField { id: groupTitle; objectName: "campaignListTitle"; placeholderText: "名单名称"; Layout.fillWidth: true }
            Label { text: "当前筛选中 " + templateDialog.recordKeys.length + " 位有姓名的学员。可添加多条文字或文件；创建后在群发中心检查名单。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#667085" }
            Label { text: "可用变量：{姓名}、{学号}、{班期}、{状态}、{免催日期}、{欠课}、{欠作业}、{" + backend.profilesModule.messagePlaceholders.join("}、{") + "}"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#667085" }
            CheckBox { id: namesOnly; objectName: "campaignNamesOnly"; text: "只生成姓名名单，稍后配置消息" }
            ScrollView {
                id: messageScroll
                visible: !namesOnly.checked; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                MessageFields { id: messageFields; objectName: "campaignMessageFields"; width: messageScroll.availableWidth }
            }
            Label { text: sender.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#b54708" }
            RowLayout {
                Button { objectName: "createCampaignSelection"; text: "创建并打开群发中心"; enabled: templateDialog.recordKeys.length > 0; onClicked: {
                    if(sender.createFromCampaignSelection(groupTitle.text,messageFields.values(),templateDialog.recordKeys,namesOnly.checked)) {
                        templateDialog.close(); root.switchModule(4)
                    }
                } }
                Button { text: "取消"; onClicked: templateDialog.close() }
            }
        }
    }
    Dialog {
        id: noReplyDialog; anchors.centerIn: parent; modal: true; title: "确认批量标记未回复"; standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "仅处理当前筛选结果中尚无本批次反馈、且草稿为空的学员。\n名单变化后请重新确认当前范围。"; lineHeight: 1.5 }
        onAccepted: wf.markUnreplied()
    }
    Snackbar { id: snack }
    FloatingProfile { id: profileFloat }
    Connections { target: backend; function onToast(message) { snack.text=message; snack.open() } }
    Connections { target: wf; function onChanged() { table.forceLayout() } }
}
