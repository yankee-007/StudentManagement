import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    visible: false
    width: 1280
    height: 800
    title: "学员管理 · 催办与画像"
    color: UiTheme.canvas
    font.pixelSize: 13
    property bool campaignDetailOpen: width >= 1000
    readonly property var moduleNames: ["催办工作台", "学员画像", "班期学员", "设置", "群发中心", "备注批改", "未进直播间"]
    property var wf: backend.workflow
    property var sender: backend.groupCenter
    property var restartService: typeof restartController !== "undefined" ? restartController : null
    onClosing: function(close) {
        if (!wf.flushFeedback()) { close.accepted=false; return }
        if (root.moduleIndex === 4 && !backend.groupCenter.active) groupCenterPage.saveSettings()
        if (root.moduleIndex === 5 && !backend.remarkRenamer.active) remarkRenamerPage.saveOptions()
        if (backend.contactOpener.active) { close.accepted=false; snack.text="正在打开联系人，请等待完成后关闭"; snack.open() }
        else if (sender.active) { close.accepted=false; sender.stop(); snack.text="正在结束发送，请等待当前联系人处理完成后再关闭"; snack.open() }
        else if (backend.remarkRenamer.active) { close.accepted=false; backend.remarkRenamer.stop(); snack.text="正在结束备注批改，请等待当前联系人处理完成后再关闭"; snack.open() }
        else { profileFloat.close(); campaignFloat.close() }
    }
    property int moduleIndex: 0
    function switchModule(index) {
        if (!wf.flushFeedback()) return
        moduleIndex = index
        if (index === 1) backend.profilesModule.activate()
        else if (index === 0) wf.activate()
        else if (index === 2) backend.termsModule.activate()
        else if (index === 3) backend.settingsModule.refresh()
        else if (index === 4) backend.groupCenter.refresh()
        else if (index === 5) backend.remarkRenamer.reload()
        else if (index === 6) backend.liveAbsence.activate()
    }
    CampaignExportDialog { id: batchExportDialog; workflow: root.wf }
    CampaignFieldDialog { id: fieldDialog; workflow: root.wf }
    FloatingCampaign { id: campaignFloat }
    function openColumn(index) { columnDialog.openFor(index) }
    function applyFilter() { wf.filterRows(viewBox.currentValue || "all", search.text) }
    ClassSwitchOverlay { id: classSwitch }
    header: ToolBar {
        implicitHeight: 60
        background: Rectangle { color: UiTheme.surface; border.color: UiTheme.line }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 14
            Label { text: "学员管理"; font.pixelSize: 18; font.bold: true; color: UiTheme.ink; Layout.preferredWidth: navigation.width - 18 }
            UiComboBox {
                id: classBox
                objectName: "classSelector"
                popup.objectName: "classSelectorPopup"
                visible: root.moduleIndex === 0 || root.moduleIndex === 1 || root.moduleIndex === 2 || root.moduleIndex === 5 || root.moduleIndex === 6
                model: wf.classes; currentIndex: wf.classIndex
                enabled: !backend.busy && !backend.termsModule.busy && !sender.active && !wf.sender.active && !backend.contactOpener.active && !backend.remarkRenamer.active && !backend.liveAbsence.busy
                Layout.preferredWidth: 100
                popupTextAlignment: Text.AlignHCenter
                Accessible.name: "班期"
                contentItem: Text {
                    text: classBox.displayText; font: classBox.font; color: UiTheme.ink
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                ToolTip.visible: hovered && contentItem.truncated
                ToolTip.text: currentText
                onActivated: function(index) {
                    popup.close()
                    if (index === wf.classIndex) return
                    var name = wf.classes[index]
                    var size = wf.classRosterSize(index)
                    classSwitch.begin(name, function() {
                        wf.selectClass(index)
                        if (root.moduleIndex === 2) backend.termsModule.activate()
                    }, size < 0 || size >= 300)
                }
            }
            Item { Layout.fillWidth: true }
            UiButton {
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
            Label { text: backend.systemDate; color: UiTheme.muted; font.pixelSize: 12; visible: root.width >= 1000 }
        }
    }
    Rectangle {
        id: navigation
        objectName: "moduleNavigation"
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        width: root.width >= 1180 ? 156 : 100
        color: "#203047"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 10; spacing: 6
            Repeater {
                model: [0, 1, 2, 6, 5]
                UiButton {
                    required property int modelData
                    objectName: "moduleButton" + modelData
                    text: root.moduleNames[modelData]
                    Layout.fillWidth: true; implicitHeight: root.height < 620 ? 38 : 44
                    hoverEnabled: true
                    Accessible.name: text
                    Accessible.role: Accessible.PageTab
                    Accessible.selected: root.moduleIndex === modelData
                    onClicked: root.switchModule(modelData)
                    contentItem: Text { text: parent.text; color: "#f2f6fc"; font.pixelSize: navigation.width > 100 ? 14 : 12; verticalAlignment: Text.AlignVCenter; horizontalAlignment: navigation.width > 100 ? Text.AlignLeft : Text.AlignHCenter }
                    background: Rectangle { radius: 5; color: root.moduleIndex === parent.modelData ? UiTheme.accent : parent.hovered ? "#304660" : "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: "#bcd3fa" }
                }
            }
            Item { Layout.fillHeight: true }
            Label { text: "工具与配置"; color: "#b8c9df"; font.pixelSize: 12; Layout.leftMargin: 8 }
            UiButton {
                objectName: "moduleButton3"; text: "设置"; Layout.fillWidth: true; implicitHeight: root.height < 620 ? 38 : 44; hoverEnabled: true
                onClicked: root.switchModule(3)
                Accessible.role: Accessible.PageTab
                Accessible.selected: root.moduleIndex === 3
                contentItem: Text { text: parent.text; color: "#f2f6fc"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 5; color: root.moduleIndex === 3 ? UiTheme.accent : parent.hovered ? "#304660" : "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: "#bcd3fa" }
            }
            UiButton {
                objectName: "moduleButton4"; text: "群发中心"; Layout.fillWidth: true; implicitHeight: root.height < 620 ? 38 : 44; hoverEnabled: true
                onClicked: root.switchModule(4)
                Accessible.role: Accessible.PageTab
                Accessible.selected: root.moduleIndex === 4
                contentItem: Text { text: parent.text; color: "#f2f6fc"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 5; color: root.moduleIndex === 4 ? UiTheme.accent : parent.hovered ? "#304660" : "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: "#bcd3fa" }
            }
        }
    }
    ColumnLayout {
        objectName: "workbenchPage"
        visible: root.moduleIndex === 0
        anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16; spacing: root.height < 620 ? 6 : 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: wf.dataNote; color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
            UiButton { text: "采集异常明细"; visible: backend.fetchIssues.length > 0; onClicked: fetchIssuesDialog.open() }
            UiComboBox { objectName: "campaignBatchSelector"; model: wf.batches; textRole: "label"; currentIndex: wf.batchIndex; displayText: wf.batchIndex < 0 ? "当前全班名单（尚未建立批次）" : currentText; Layout.preferredWidth: 280; enabled: !backend.busy && wf.batchIndex >= 0 && !sender.active; onActivated: wf.selectBatch(currentIndex) }
            UiButton { objectName: "fetchLearningButton"; visible: root.moduleIndex === 0 && (wf.batchIndex < 0 || wf.canEdit); text: backend.busy ? "刷新中…" : "刷新数据"; enabled: !backend.busy && !backend.termsModule.busy && !sender.active; onClicked: backend.fetchData() }
            UiButton { objectName: "createCampaignButton"; text: backend.busy ? "正在获取最新数据…" : "新建催办"; highlighted: true; enabled: !backend.busy && !backend.termsModule.busy && !sender.active; onClicked: createDialog.open() }
            UiButton { text: "导出全班 XLSX"; enabled: wf.batchIndex >= 0; onClicked: batchExportDialog.open() }
        }
        LearningDashboard { stats: wf.dashboard; compact: root.height < 620 }
        UiPanel {
            visible: root.width < 1000 || (wf.batchIndex >= 0 && !wf.canEdit)
            Layout.fillWidth: true; padding: 10
            background: Rectangle { color: "white"; radius: 8; border.color: UiTheme.line }
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    visible: root.width < 1000
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    UiButton { objectName: "campaignDetailToggle"; text: root.campaignDetailOpen ? "学员列表" : "学员详情"; visible: root.width < 1000; onClicked: root.campaignDetailOpen = !root.campaignDetailOpen }
                }
                Label { visible: wf.batchIndex >= 0 && !wf.canEdit; text: "历史批次只读：学习数据保持当时快照，不受后续获取影响。"; color: UiTheme.warning; font.pixelSize: 12 }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            UiPanel {
                visible: root.width >= 1000 || !root.campaignDetailOpen
                Layout.fillWidth: true; Layout.fillHeight: true; padding: 10
                background: Rectangle { color: "white"; radius: 10; border.color: UiTheme.line }
                ColumnLayout {
                    anchors.fill: parent; spacing: root.height < 620 ? 4 : 8
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: (wf.cursorText.length > 0 ? wf.cursorText + " · " : "") + "显示 " + wf.visibleCount + " 人" + (wf.hasStale ? " · " + wf.staleCount + " 人已不符合当前筛选" : ""); color: wf.hasStale ? UiTheme.warning : UiTheme.muted; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        UiComboBox {
                            id: viewBox; objectName: "campaignViewSelector"; textRole: "label"; valueRole: "key"; width: 105
                            displayText: currentText
                            model: [{label:"全班快照",key:"all"},{label:"本次催办",key:"targets"}]
                            onActivated: root.applyFilter()
                        }
                        UiButton { objectName: "createCampaignList"; text: "生成群发名单"; highlighted: true; enabled: wf.canEdit && !sender.active && !backend.busy && wf.recipientKeys.length > 0; onClicked: templateDialog.open() }
                        UiButton { text: "管理字段"; onClicked: fieldDialog.open() }
                        UiButton { text: "聊天跟随浮窗"; enabled: wf.canEdit; onClicked: campaignFloat.show() }
                        UiTextField { id: search; objectName: "campaignSearchInput"; placeholderText: "搜索学号、姓名、备注"; width: 150; onTextEdited: searchTimer.restart(); Timer { id: searchTimer; interval: 180; onTriggered: root.applyFilter() } }
                        UiButton { objectName: "markUnrepliedButton"; text: "批量未回复"; visible: viewBox.currentValue === "targets"; enabled: wf.canEdit && wf.visibleCount > 0; onClicked: noReplyDialog.open() }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        UiButton { objectName: "campaignReapplyFilter"; text: "重新应用筛选"; visible: wf.hasStale; onClicked: wf.reapplyFilters() }
                        UiButton { text: "清除列筛选／排序"; visible: wf.hasColumnQuery; onClicked: wf.clearColumnQuery() }
                    }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        HorizontalHeaderView {
                            id: header; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: UiTheme.headerHeight; syncView: table
                            delegate: Rectangle {
                                required property int column
                                required property var display
                                implicitHeight: UiTheme.headerHeight; implicitWidth: 90
                                property bool filtered: wf.filteredColumns.indexOf(column) >= 0
                                color: filtered ? "#e4ecff" : UiTheme.stripe
                                Text {
                                    anchors.fill: parent; anchors.margins: 6; anchors.rightMargin: 20; verticalAlignment: Text.AlignVCenter
                                    text: display + (parent.filtered ? " •" : "")
                                    elide: Text.ElideRight; font.pixelSize: 12; font.bold: wf.sortColumnIndex === column; color: UiTheme.ink
                                }
                                UiHeaderMarker { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; width: 10; height: 10; descending: wf.sortColumnIndex !== column || wf.sortDescending; markerColor: wf.sortColumnIndex === column ? UiTheme.accent : UiTheme.muted }
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
                            rowHeightProvider: function() { return UiTheme.rowHeight }
                            ScrollBar.horizontal: ScrollBar { }
                            ScrollBar.vertical: ScrollBar { }
                            delegate: Rectangle {
                                required property int row
                                required property int column
                                required property string display
                                required property string studentId
                                required property bool expiredCell
                                required property bool staleRow
                                implicitHeight: UiTheme.rowHeight; implicitWidth: 90
                                color: studentId === wf.selected.student_id ? UiTheme.selection : staleRow ? "#fff4e5" : row % 2 ? UiTheme.stripe : "white"
                                Text { anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 6; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; color: expiredCell ? "#98a2b3" : staleRow ? UiTheme.warning : UiTheme.ink }
                                TapHandler { onTapped: wf.selectRow(row) }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: wf.visibleCount === 0; text: search.text.length > 0 || wf.hasColumnQuery ? "没有匹配的学员，请调整搜索或列筛选" : wf.batchIndex < 0 ? "暂无符合条件的学员；班期名单获取后自动同步" : "当前筛选下没有学员"; horizontalAlignment: Text.AlignHCenter; color: "#98a2b3"; lineHeight: 1.6 }
                    }
                }
            }
            UiPanel {
                visible: root.width >= 1000 || root.campaignDetailOpen
                Layout.preferredWidth: 340; Layout.minimumWidth: 260; Layout.fillWidth: root.width < 1000; Layout.fillHeight: true; padding: 16
                background: Rectangle { color: "white"; radius: 10; border.color: UiTheme.line }
                CampaignDetail { objectName: "mainCampaignDetail"; anchors.fill: parent; service: wf; workflow: wf }
            }
        }
    }
    ProfileModule { objectName: "profileModule"; visible: root.moduleIndex === 1; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16; openFloatingProfile: function() { profileFloat.show() }; onOpenGroupCenter: root.switchModule(4) }
    TermModule { visible: root.moduleIndex === 2; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16 }
    SettingsModule { visible: root.moduleIndex === 3; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16 }
    GroupCenter { id: groupCenterPage; visible: root.moduleIndex === 4; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16 }
    RemarkRenamer { id: remarkRenamerPage; visible: root.moduleIndex === 5; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16 }
    LiveAbsence { id: liveAbsencePage; visible: root.moduleIndex === 6; anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: navigation.width + 16; onOpenGroupCenter: root.switchModule(4) }
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
            UiTextField { id: groupTitle; objectName: "campaignListTitle"; placeholderText: "名单名称"; Layout.fillWidth: true }
            Label { text: "当前筛选中 " + templateDialog.recordKeys.length + " 位有姓名的学员。可添加多条文字或文件；创建后在群发中心检查名单。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            Label { text: "可用变量：{姓名}、{学号}、{班期}、{状态}、{免催日期}、{欠课}、{欠作业}、{" + backend.profilesModule.messagePlaceholders.join("}、{") + "}"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
            CheckBox { id: namesOnly; objectName: "campaignNamesOnly"; text: "只生成姓名名单，稍后配置消息" }
            ScrollView {
                id: messageScroll
                visible: !namesOnly.checked; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                MessageFields { id: messageFields; objectName: "campaignMessageFields"; width: messageScroll.availableWidth }
            }
            Label { text: sender.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "createCampaignSelection"; text: "创建并打开群发中心"; enabled: templateDialog.recordKeys.length > 0; onClicked: {
                    if(sender.createFromCampaignSelection(groupTitle.text,messageFields.values(),templateDialog.recordKeys,namesOnly.checked)) {
                        templateDialog.close(); root.switchModule(4)
                    }
                } }
                UiButton { text: "取消"; onClicked: templateDialog.close() }
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
