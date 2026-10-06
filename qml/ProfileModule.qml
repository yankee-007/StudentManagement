import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var profiles: backend.profilesModule
    property var student: profiles.selected
    property var openFloatingProfile: function() {}
    property bool cardExpanded: width >= 760
    signal openGroupCenter()
    ProfileFilterDialog { id: columnFilter; profiles: page.profiles }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "学员画像"; font.pixelSize: 21; font.bold: true; color: UiTheme.ink }
            Label { text: page.width>1100 ? "班期名单自动同步 · 人工资料独立保存" : ""; color: UiTheme.muted; Layout.fillWidth: true }
            UiButton { objectName: "profileDetailToggle"; text: page.cardExpanded ? "收起画像" : "查看画像"; onClicked: page.cardExpanded = !page.cardExpanded }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            CheckBox { text: "全部班级"; checked: profiles.allClasses; onToggled: profiles.setAllClasses(checked) }
            UiButton { text: "打开画像浮窗"; enabled: !profiles.allClasses; onClicked: page.openFloatingProfile() }
            UiButton { text: "刷新"; onClicked: profiles.refresh() }
            UiButton { text: "导出画像"; enabled: profiles.visibleCount > 0; onClicked: exportDialog.open() }
            UiButton { text: "管理字段"; enabled: !profiles.allClasses; onClicked: fieldManager.open() }
        }
        RowLayout {
            Layout.fillWidth: true
            UiTextField { id: searchInput; placeholderText: "搜索班期、学号、姓名"; Layout.fillWidth: true; onTextEdited: timer.restart(); Timer { id: timer; interval: 180; onTriggered: profiles.search(searchInput.text) } }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            UiButton { objectName: "profileReapplyFilter"; text: "重新应用筛选"; visible: profiles.hasStale; onClicked: profiles.reapplyFilters() }
            UiButton { text: "新建名单到群发中心"; enabled: profiles.recipientKeys.length > 0 && !backend.groupCenter.active; onClicked: profileGroupDialog.open() }
            UiButton { text: "清除筛选"; visible: profiles.filteredKeys.length > 0; onClicked: profiles.clearFilters() }
        }
        Label { text: "显示 " + profiles.visibleCount + " / " + profiles.total + " 人" + (profiles.hasStale ? "（" + profiles.staleCount + " 人已不符合当前筛选）" : "") + (profiles.cursorText.length > 0 ? " · " + profiles.cursorText : ""); color: profiles.hasStale ? UiTheme.warning : UiTheme.muted; elide: Text.ElideRight; Layout.fillWidth: true }
        Label { text: profiles.allClasses ? "全部班级为只读总览。需要编辑时，取消勾选并在顶部选择对应班级。" : profiles.notice; font.pixelSize: 12; color: UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            UiPanel {
                visible: page.width >= 760 || !page.cardExpanded
                Layout.fillWidth: true; Layout.fillHeight: true; padding: 10
                background: Rectangle { color: "white"; radius: 10; border.color: UiTheme.line }
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: "表头可筛选或排序。修改后保留当前学员；重新应用筛选时更新名单。"; font.pixelSize: 12; color: UiTheme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        HorizontalHeaderView {
                            id: header; syncView: table; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: UiTheme.headerHeight
                            delegate: Rectangle {
                                required property int column
                                required property var display
                                property bool filtered: { var f=profiles.columnFilterInfo(column); return profiles.filteredKeys.indexOf(f.key)>=0 }
                                implicitWidth: 115; implicitHeight: UiTheme.headerHeight; color: filtered ? "#e4ecff" : UiTheme.stripe
                                Text { anchors.fill: parent; anchors.margins: 6; anchors.rightMargin: 20; text: display + (parent.filtered ? " •" : ""); verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.pixelSize: 12; color: UiTheme.ink }
                                UiHeaderMarker { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; width: 10; height: 10 }
                                TapHandler { onTapped: columnFilter.openFor(column) }
                            }
                        }
                        TableView {
                            id: table; objectName: "profileTable"; model: profiles.tableModel
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: header.bottom; anchors.bottom: parent.bottom
                            clip: true; reuseItems: true; rowSpacing: 1; columnSpacing: 1
                            columnWidthProvider: function(c) { return profiles.columnLabels[c] === "学号" ? 135 : 115 }
                            rowHeightProvider: function() { return UiTheme.rowHeight }
                            ScrollBar.horizontal: ScrollBar { }
                            ScrollBar.vertical: ScrollBar { }
                            delegate: Rectangle {
                                required property int row
                                required property string display
                                required property string recordKey
                                required property bool expiredCell
                                required property bool staleRow
                                implicitHeight: UiTheme.rowHeight; implicitWidth: 115
                                color: recordKey === (page.student._record_key || "") ? UiTheme.selection : staleRow ? "#fff4e5" : row % 2 ? UiTheme.stripe : "white"
                                Text { anchors.fill: parent; anchors.leftMargin: 6; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; color: expiredCell ? "#98a2b3" : staleRow ? UiTheme.warning : UiTheme.ink }
                                TapHandler { onTapped: profiles.selectRow(row) }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: profiles.visibleCount === 0; text: profiles.total ? "没有匹配的学员" : "请在班期学员中获取名单，画像将自动同步"; color: "#98a2b3" }
                    }
                }
            }
            UiPanel {
                visible: page.cardExpanded
                Layout.preferredWidth: 340; Layout.minimumWidth: 260; Layout.fillWidth: page.width < 760; Layout.fillHeight: true; padding: 16
                background: Rectangle { color: "white"; radius: 10; border.color: UiTheme.line }
                ColumnLayout {
                    anchors.fill: parent; spacing: 8
                    Label { text: profiles.allClasses ? "只读总览" : "资料修改后自动保存"; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                    ProfileIdentity { student: page.student }
                    ProfileContactAction { student: page.student }
                    ProfileEditor { Layout.fillWidth: true; Layout.fillHeight: true; fields: profiles.fields; saveTarget: profiles }
                }
            }
            UiButton {
                visible: !page.cardExpanded && page.width >= 760
                Layout.preferredWidth: 40; Layout.fillHeight: true
                text: "展\n开\n学\n员\n画\n像\n卡\n片"
                onClicked: page.cardExpanded=true
            }
        }
    }
    Dialog {
        id: profileGroupDialog; objectName: "profileGroupDialog"
        anchors.centerIn: parent; modal: true; title: "从筛选结果新建群发名单"
        width: Math.min(page.width-30,650); height: Math.min(page.height-30,570)
        property var recordKeys: []
        onOpened: {
            recordKeys=profiles.recipientKeys.slice()
            groupTitle.text=(profiles.allClasses ? "全部班级" : backend.workflow.className) + " · 画像筛选名单"
            profileMessages.load([{type:"text",text:"{姓名}同学，你好！"}])
        }
        ColumnLayout {
            anchors.fill: parent
            UiTextField { id: groupTitle; placeholderText: "名单名称"; Layout.fillWidth: true }
            Label { text: "可在话术中使用画像字段变量：{" + profiles.messagePlaceholders.join("}、{") + "}。创建时会把每个人对应的字段值写入消息。将创建 " + profileGroupDialog.recordKeys.length + " 人的名单；无姓名及补位行跳过。仅创建，不会立即发送。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            ScrollView {
                id: profileMessageScroll; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                MessageFields { id: profileMessages; width: profileMessageScroll.availableWidth }
            }
            Label { text: backend.groupCenter.status; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                UiButton { text: "取消"; onClicked: profileGroupDialog.close() }
                UiButton { text: "创建并打开群发中心"; onClicked: {
                    if(backend.groupCenter.createFromProfiles(groupTitle.text,profileMessages.values(),profileGroupDialog.recordKeys)) {
                        profileGroupDialog.close(); page.openGroupCenter()
                    }
                } }
            }
        }
    }
    Dialog {
        id: exportDialog; objectName: "profileExportDialog"
        anchors.centerIn: parent; modal: true; title: "导出学员画像"
        width: Math.min(page.width - 30, 460); height: Math.min(page.height - 30, 560)
        property var selectedKeys: []
        function resetSelection(all) {
            selectedKeys=profiles.exportFields.filter(function(f) { return all || f.selected }).map(function(f) { return f.key })
        }
        onOpened: resetSelection(false)
        ColumnLayout {
            anchors.fill: parent
            Label { text: "导出当前筛选的 " + profiles.matchedCount + " 位学员，保持当前排序；已不符合当前筛选的行不计入。\n字段选择独立于表格显示设置。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                UiButton { text: "默认字段"; onClicked: exportDialog.resetSelection(false) }
                UiButton { text: "全选"; onClicked: exportDialog.resetSelection(true) }
                UiButton { text: "清空"; onClicked: exportDialog.selectedKeys=[] }
            }
            ScrollView {
                id: exportScroll; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: exportScroll.availableWidth
                    Repeater {
                        model: profiles.exportFields
                        CheckBox {
                            required property var modelData
                            text: modelData.name
                            checked: exportDialog.selectedKeys.indexOf(modelData.key) >= 0
                            onToggled: {
                                var keys=exportDialog.selectedKeys.slice()
                                var index=keys.indexOf(modelData.key)
                                if (checked && index < 0) keys.push(modelData.key)
                                if (!checked && index >= 0) keys.splice(index,1)
                                exportDialog.selectedKeys=keys
                            }
                        }
                    }
                }
            }
            Label { text: profiles.notice; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                UiButton { text: "取消"; onClicked: exportDialog.close() }
                UiButton {
                    text: "导出 XLSX"; enabled: exportDialog.selectedKeys.length > 0
                    onClicked: {
                        var keys=profiles.exportFields.filter(function(f) { return exportDialog.selectedKeys.indexOf(f.key) >= 0 }).map(function(f) { return f.key })
                        if (profiles.exportXlsx(keys)) exportDialog.close()
                    }
                }
            }
        }
    }
    Dialog {
        id: fieldManager; objectName: "profileFieldManager"; anchors.centerIn: parent; modal: true; title: "管理字段 · " + backend.workflow.className
        width: Math.min(page.width - 30, 540); height: Math.min(page.height - 30, 570)
        standardButtons: Dialog.Close
        ScrollView {
            id: fieldManagerScroll
            anchors.fill: parent; contentWidth: availableWidth
            ColumnLayout {
                width: fieldManagerScroll.availableWidth; spacing: 10
                Label { text: "仅管理当前班期，不影响其他班期。拖动手柄排序；勾选控制表格、画像填写和浮窗显示；学号、姓名始终显示。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                ProfileFieldOrder {
                    Layout.fillWidth: true; profiles: page.profiles
                    onRemoveField: function(fieldId,fieldName) { deleteFieldDialog.fieldId=fieldId; deleteFieldDialog.fieldName=fieldName; deleteFieldDialog.open() }
                }
                UiTextField { id: fieldName; placeholderText: "新字段名称"; Layout.fillWidth: true }
                UiComboBox { id: fieldType; model: ["文本","日期","下拉选项"]; Layout.fillWidth: true }
                TextArea { id: fieldOptions; visible: fieldType.currentIndex === 2; placeholderText: "下拉选项，每行一个"; Layout.fillWidth: true; implicitHeight: 90 }
                CheckBox { id: showColumn; text: "在表格和画像填写中显示"; checked: true }
                UiButton { text: "添加字段"; onClicked: { if (profiles.addField(fieldName.text,["text","date","choice"][fieldType.currentIndex],fieldOptions.text,showColumn.checked)) { fieldName.clear(); fieldOptions.clear() } } }
                Label { text: profiles.notice; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            }
        }
    }
    Dialog {
        id: deleteFieldDialog; objectName: "deleteProfileFieldDialog"
        property string fieldId: ""
        property string fieldName: ""
        anchors.centerIn: parent; modal: true; title: "删除额外字段"
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "删除当前班期「" + deleteFieldDialog.fieldName + "」及填写内容？\n其他班期不受影响。此操作不可撤销；只想隐藏请取消勾选。"; wrapMode: Text.Wrap }
        onAccepted: profiles.deleteField(fieldId)
    }
}
