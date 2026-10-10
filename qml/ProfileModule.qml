import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var profiles: backend.profilesModule
    property var wechatVerifier: profiles.wechatVerifier
    property var student: profiles.selected
    property var openFloatingProfile: function() {}
    property bool cardExpanded: width >= 760
    signal openGroupCenter()
    ProfileFilterDialog { id: columnFilter; profiles: page.profiles }
    ProfileWechatDialog { id: wechatDialog; verifier: page.wechatVerifier }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "学员画像"; font.pixelSize: 21; font.bold: true; color: UiTheme.ink }
            Label { text: page.width>1100 ? "班期名单自动同步 · 人工资料独立保存" : ""; color: UiTheme.muted; Layout.fillWidth: true }
            UiButton { text: "刷新数据"; onClicked: profiles.refresh() }
            UiButton { text: "导出画像 XLSX"; enabled: profiles.visibleCount > 0; onClicked: exportDialog.open() }
            UiButton { objectName: "profileDetailToggle"; text: page.cardExpanded ? "收起画像" : "查看画像"; onClicked: page.cardExpanded = !page.cardExpanded }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            UiPanel {
                id: profileListPanel
                visible: page.width >= 760 || !page.cardExpanded
                Layout.fillWidth: true; Layout.fillHeight: true; padding: 10
                background: Rectangle { color: UiTheme.surface; radius: 10; border.color: UiTheme.line }
                ColumnLayout {
                    anchors.fill: parent
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: (profiles.cursorText.length > 0 ? profiles.cursorText + " · " : "") + "显示 " + profiles.visibleCount + " / " + profiles.total + " 人" + (profiles.hasStale ? " · " + profiles.staleCount + " 人已不符合当前筛选" : ""); color: profiles.hasStale ? UiTheme.warning : UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                        UiTextField { id: searchInput; objectName: "profileSearchInput"; placeholderText: "搜索班期、学号、姓名、备注"; Layout.preferredWidth: Math.min(280, Math.max(0, profileListPanel.availableWidth * 0.5)); onTextEdited: timer.restart(); Timer { id: timer; interval: 180; onTriggered: profiles.search(searchInput.text) } }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        UiButton { objectName: "createProfileList"; text: "生成群发名单"; highlighted: true; enabled: profiles.recipientKeys.length > 0 && !backend.groupCenter.active; onClicked: profileGroupDialog.open() }
                        UiButton { objectName: "manageProfileFields"; text: "管理字段"; enabled: !profiles.allClasses; onClicked: fieldManager.open() }
                        UiButton { objectName: "verifyProfileWechat"; text: wechatVerifier.active ? "查看微信验证进度" : "批量验证微信"; enabled: wechatVerifier.active || !profiles.allClasses; onClicked: { if (wechatVerifier.active || wechatVerifier.prepare()) wechatDialog.open() } }
                        UiButton { text: "聊天跟随浮窗"; enabled: !profiles.allClasses; onClicked: page.openFloatingProfile() }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        CheckBox { text: "全部班级"; checked: profiles.allClasses; enabled: !wechatVerifier.active; onToggled: profiles.setAllClasses(checked) }
                        UiButton { objectName: "profileReapplyFilter"; text: "重新应用筛选"; visible: profiles.hasStale; onClicked: profiles.reapplyFilters() }
                        UiButton { text: "清除列筛选"; visible: profiles.filteredKeys.length > 0; onClicked: profiles.clearFilters() }
                    }
                    Label { text: profiles.allClasses ? "全部班级为只读总览，取消勾选后可填写资料。" : profiles.notice; font.pixelSize: 12; color: UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; visible: text.length > 0 }
                    Label { text: wechatVerifier.notice; visible: wechatVerifier.active; font.pixelSize: 12; color: UiTheme.accent; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        HorizontalHeaderView {
                            id: header; syncView: table; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: UiTheme.headerHeight
                            delegate: Rectangle {
                                required property int column
                                required property var display
                                property bool filtered: profiles.filteredKeys.indexOf(profiles.columnKeys[column]) >= 0
                                implicitWidth: 115; implicitHeight: UiTheme.headerHeight; color: filtered ? UiTheme.selection : UiTheme.stripe
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
                                color: recordKey === (page.student._record_key || "") ? UiTheme.selection : staleRow ? UiTheme.warningSurface : row % 2 ? UiTheme.stripe : UiTheme.surface
                                Text { anchors.fill: parent; anchors.leftMargin: 6; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; color: expiredCell ? UiTheme.subtle : staleRow ? UiTheme.warning : UiTheme.ink }
                                TapHandler { onTapped: profiles.selectRow(row) }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: profiles.visibleCount === 0; text: profiles.total ? "没有匹配的学员" : "请在班期学员中获取名单，画像将自动同步"; color: UiTheme.subtle }
                    }
                }
            }
            UiPanel {
                visible: page.cardExpanded
                Layout.preferredWidth: 340; Layout.minimumWidth: 260; Layout.fillWidth: page.width < 760; Layout.fillHeight: true; padding: 16
                background: Rectangle { color: UiTheme.surface; radius: 10; border.color: UiTheme.line }
                ColumnLayout {
                    anchors.fill: parent; spacing: 8
                    Label { text: profiles.allClasses ? "只读总览" : "资料修改后自动保存"; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                    ProfileContactAction { student: page.student }
                    ProfileIdentity { student: page.student; showName: false }
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
        width: Math.min(page.width - 24, 900); height: Math.min(page.height - 24, 660)
        padding: 12
        property bool wideLayout: width >= 780
        property bool addingField: false
        onClosed: { fieldOrder.cancelDrag(); profiles.flushFieldOrder() }
        background: Rectangle { radius: 12; color: UiTheme.surface; border.color: UiTheme.line }
        header: Item {
            implicitHeight: 72
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "管理字段"; font.pixelSize: 20; font.weight: Font.DemiBold; color: UiTheme.ink }
                    Label { text: backend.workflow.className; Layout.fillWidth: true; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight; color: UiTheme.muted; font.pixelSize: 12 }
                }
                Label { text: "拖动左侧手柄，放到蓝色间隙处；勾选控制字段显示。"; font.pixelSize: 12; color: UiTheme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }
        contentItem: GridLayout {
            columns: fieldManager.wideLayout ? 2 : 1
            columnSpacing: 12; rowSpacing: 8
            Rectangle {
                visible: fieldManager.wideLayout || !fieldManager.addingField
                z: fieldOrder.dragging ? 1 : 0
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100
                color: UiTheme.canvas; radius: 10; border.color: UiTheme.line
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 8; spacing: 4
                    RowLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.topMargin: 4
                        Label { text: "字段顺序"; color: UiTheme.ink; font.pixelSize: 13; font.weight: Font.DemiBold }
                        Label { text: fieldOrder.count + " 个字段"; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight }
                        UiButton {
                            objectName: "profileFieldReset"; text: "重置默认"
                            implicitHeight: 28; topPadding: 4; bottomPadding: 4; font.pixelSize: 12
                            ToolTip.visible: hovered
                            ToolTip.text: "恢复默认顺序并显示所有字段，保留自定义字段及填写内容"
                            onClicked: { fieldOrder.cancelDrag(); if (profiles.resetFieldLayout()) fieldOrder.resetPosition() }
                        }
                    }
                    ProfileFieldOrder {
                        id: fieldOrder
                        Layout.fillWidth: true; Layout.fillHeight: true; profiles: page.profiles
                        onRemoveField: function(fieldId,fieldName) { deleteFieldDialog.fieldId=fieldId; deleteFieldDialog.fieldName=fieldName; deleteFieldDialog.open() }
                    }
                }
            }
            Rectangle {
                objectName: "profileFieldAddPanel"
                visible: fieldManager.wideLayout || fieldManager.addingField
                Layout.preferredWidth: fieldManager.wideLayout ? 252 : -1
                Layout.fillWidth: !fieldManager.wideLayout
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                color: UiTheme.stripe; radius: 10; border.color: UiTheme.line
                ScrollView {
                    id: addFieldScroll
                    objectName: "profileFieldAddScroll"
                    anchors.fill: parent; anchors.margins: 16
                    clip: true; contentWidth: availableWidth
                    Flickable {
                        id: addFieldFlick
                        contentWidth: width; contentHeight: fieldForm.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        ColumnLayout {
                            id: fieldForm
                            width: addFieldFlick.width; spacing: 8
                            Label { text: "新增字段"; color: UiTheme.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                            Label { text: "仅添加到当前班期"; color: UiTheme.muted; font.pixelSize: 12; Layout.bottomMargin: 8 }
                            Label { text: "字段名称"; color: UiTheme.ink; font.pixelSize: 12 }
                            UiTextField { id: fieldName; objectName: "profileFieldName"; placeholderText: "例如：方便联系时间"; Layout.fillWidth: true; Accessible.name: "字段名称" }
                            Label { text: "字段类型"; color: UiTheme.ink; font.pixelSize: 12; Layout.topMargin: 4 }
                            UiComboBox {
                                id: fieldType; objectName: "profileFieldType"
                                model: ["文本","日期","下拉选项"]; Layout.fillWidth: true; Accessible.name: "字段类型"
                                SettingsWheelGuard { view: addFieldFlick }
                            }
                            Label { text: "下拉选项"; visible: fieldType.currentIndex === 2; color: UiTheme.ink; font.pixelSize: 12; Layout.topMargin: 4 }
                            TextArea {
                                id: fieldOptions; objectName: "profileFieldOptions"
                                visible: fieldType.currentIndex === 2; placeholderText: "每行一个，例如：\n上午\n下午\n晚上"
                                Layout.fillWidth: true; implicitHeight: 100
                                color: UiTheme.ink; placeholderTextColor: UiTheme.muted; font.pixelSize: 13
                                wrapMode: TextEdit.Wrap; selectByMouse: true; Accessible.name: "下拉选项，每行一个"
                                background: Rectangle { radius: 5; color: UiTheme.surface; border.color: fieldOptions.activeFocus ? UiTheme.accent : UiTheme.line; border.width: fieldOptions.activeFocus ? 2 : 1 }
                            }
                            CheckBox { id: showColumn; text: "显示此字段"; checked: true; font.pixelSize: 13 }
                            UiButton {
                                objectName: "profileFieldAdd"; text: "添加字段"; highlighted: true; Layout.fillWidth: true
                                enabled: fieldName.text.trim().length > 0
                                onClicked: {
                                    if (profiles.addField(fieldName.text,["text","date","choice"][fieldType.currentIndex],fieldOptions.text,showColumn.checked)) {
                                        fieldName.clear(); fieldOptions.clear()
                                        if (!fieldManager.wideLayout) fieldManager.addingField = false
                                    }
                                }
                            }
                            Label { text: "学号、姓名固定显示。\n隐藏字段会保留已填写的内容。"; color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.topMargin: 12 }
                        }
                    }
                }
            }
        }
        footer: Rectangle {
            implicitHeight: 56; color: UiTheme.surface
            Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: UiTheme.line }
            RowLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 8
                Label { text: profiles.fieldOrderSaving ? "正在保存字段顺序…" : profiles.notice === "修改后自动保存" ? "修改自动保存，仅当前班期生效" : profiles.notice; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                UiButton { objectName: "profileFieldShowAdd"; visible: !fieldManager.wideLayout; text: fieldManager.addingField ? "返回字段" : "新增字段"; onClicked: fieldManager.addingField = !fieldManager.addingField }
                UiButton { objectName: "profileFieldDone"; text: "完成"; onClicked: fieldManager.close() }
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
