import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: panel
    objectName: "recipientMessages"
    required property var center
    property var selectedRow: ({})
    property int selectedField: -1
    property int currentListId: -1
    property var currentModel: tabs.currentIndex===0 ? center.pendingModel : center.sentModel
    property bool canManage: tabs.currentIndex===0 && !center.active && center.editableCount>0
    signal resolveRequested(int recipientId, bool wasSent)
    function editRecipient(recipientId) {
        tabs.currentIndex=0
        selectedRow=center.recipientForView(recipientId,false)
        openEditor()
    }
    function openEditor() {
        if(!selectedRow.id) return
        editor.listId=center.selected.id
        editor.recipientId=selectedRow.id
        editor.canEdit=selectedRow.editable && !center.active
        editor.title=(editor.canEdit ? "编辑消息 · " : "查看消息 · ") + selectedRow.name
        messages.load(selectedRow.items)
        editor.open()
    }
    function typeAt(column) {
        return center.columnInfo(column,false).type
    }
    function maxFieldIndex() {
        return center.pendingFieldCount-1
    }
    function editableAtColumn(column,includePersonal) {
        return center.columnInfo(column,includePersonal).count
    }
    function openColumnEditor(column) {
        if(!canManage || column<0 || column>=center.pendingFieldCount) return
        selectedField=column
        fieldDialog.listId=center.selected.id
        fieldDialog.fieldIndex=column
        fieldDialog.fieldType=typeAt(column)
        fieldDialog.isAdding=false
        fieldDialog.fieldValue=""
        var template=center.selected.content_template || []
        if(column<template.length) {
            fieldDialog.fieldType=template[column].type
            fieldDialog.fieldValue=template[column].type==="file" ? template[column].path : (template[column].template || template[column].text || "")
        }
        fieldDialog.overridePersonal=false
        fieldDialog.open()
    }
    function addMessage(kind) {
        fieldDialog.listId=center.selected.id
        fieldDialog.fieldIndex=-1; fieldDialog.fieldType=kind; fieldDialog.fieldValue=""
        fieldDialog.overridePersonal=false; fieldDialog.isAdding=true; fieldDialog.open()
    }
    function moveColumn(direction) {
        var target=selectedField+direction
        if(center.moveField(selectedField,direction)) selectedField=target
    }
    function openCellEditor(person,index) {
        if(!person.id || index<0 || index>=person.items.length) return
        var item=person.items[index]
        cellDialog.listId=center.selected.id
        cellDialog.recipientId=person.id
        cellDialog.fieldIndex=index
        cellDialog.fieldType=item.type
        cellDialog.fieldValue=item.type==="file" ? item.path : item.text
        cellDialog.canEdit=person.editable && tabs.currentIndex===0 && !center.active
        cellDialog.personName=person.name
        cellDialog.open()
    }
    function restoreSelection() {
        if(!selectedRow.id) return
        selectedRow=center.recipientForView(selectedRow.id,tabs.currentIndex===1)
    }
    Connections {
        target: panel.center
        function onSelectionChanged() {
            var listId=center.selected.id || 0
            if(listId!==panel.currentListId) {
                panel.currentListId=listId
                tabs.currentIndex=0
                panel.selectedRow=({})
                panel.selectedField=0
            }
        }
        function onRowsChanged() { panel.restoreSelection(); fieldDialog.updateImpact() }
    }
    Component.onCompleted: currentListId=center.selected.id || 0
    ColumnLayout {
        anchors.fill: parent
        TabBar {
            id: tabs; objectName: "groupMessageTabs"; Layout.fillWidth: true
            onCurrentIndexChanged: { panel.selectedRow=({}); panel.selectedField=0 }
            TabButton { text: "待处理（" + center.pendingCount + "）" }
            TabButton { text: "已发送（" + center.sentCount + "）" }
        }
        RowLayout {
            visible: tabs.currentIndex===0
            Layout.fillWidth: true
            Label { text: "批量编辑"; font.bold: true }
            UiComboBox {
                id: columnSelector; objectName: "groupColumnSelector"; Layout.fillWidth: true; Layout.minimumWidth: 100
                model: center.messageColumns; textRole: "label"; currentIndex: panel.selectedField>=0 && panel.selectedField<center.pendingFieldCount ? panel.selectedField : (center.pendingFieldCount>0 ? 0 : -1)
                enabled: panel.canManage && count>0
                onActivated: panel.selectedField=currentIndex
            }
            UiButton { objectName: "groupBulkEditButton"; text: "修改本列"; enabled: panel.canManage && columnSelector.currentIndex>=0; onClicked: panel.openColumnEditor(columnSelector.currentIndex) }
            UiButton { id: addFieldButton; text: "添加消息"; enabled: panel.canManage; onClicked: addMenu.popup(addFieldButton,0,addFieldButton.height) }
            UiButton { id: columnActions; text: "调整列"; enabled: panel.canManage && columnSelector.currentIndex>=0; onClicked: { panel.selectedField=columnSelector.currentIndex; columnMenu.popup(columnActions,0,columnActions.height) } }
        }
        Label {
            text: tabs.currentIndex===0 ? "批量修改默认保留个人改动。单击选中消息后可单独编辑，也可双击直接打开。" : "已发送消息只读；需要再次发送时，复制为新名单。"
            elide: Text.ElideRight; color: UiTheme.muted; Layout.fillWidth: true
            ToolTip.visible: hintHover.hovered; ToolTip.text: text
            HoverHandler { id: hintHover }
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            HorizontalHeaderView {
                id: header; syncView: table; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 34
                delegate: Rectangle {
                    required property var display
                    required property int index
                    property bool configurable: index>0 && index<=center.pendingFieldCount && panel.canManage
                    implicitWidth: 220; implicitHeight: 34; color: headerTap.containsMouse && configurable ? "#dbeafe" : "#eef2f8"
                    Text { anchors.fill: parent; anchors.margins: 7; text: display + (configurable ? " · 批量编辑" : ""); elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; color: UiTheme.ink }
                    MouseArea { id: headerTap; anchors.fill: parent; enabled: parent.configurable; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: panel.openColumnEditor(index-1) }
                }
            }
            TableView {
                id: table; objectName: "groupRecipientList"
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: header.bottom; anchors.bottom: parent.bottom
                model: panel.currentModel; clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                columnWidthProvider: function(c) { return c===0 ? 110 : 220 }
                rowHeightProvider: function(r) { return 52 }
                ScrollBar.horizontal: ScrollBar {}
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property int row
                    required property int column
                    required property string display
                    required property string recordKey
                    implicitWidth: 220; implicitHeight: 52
                    color: recordKey===String(panel.selectedRow.id || "") ? UiTheme.selection : row%2 ? UiTheme.stripe : "white"
                    border.width: recordKey===String(panel.selectedRow.id || "") && column>0 && column===panel.selectedField+1 ? 1 : 0
                    border.color: "#809aff"
                    Text { anchors.fill: parent; anchors.margins: 7; text: display; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: 12; color: UiTheme.ink }
                    TapHandler {
                        onTapped: {
                            var person=panel.currentModel.get(row)
                            panel.selectedRow=person
                            var fieldCount=tabs.currentIndex===0 ? center.pendingFieldCount : center.sentFieldCount
                            panel.selectedField=column>0 && column<=fieldCount ? column-1 : -1
                        }
                        onDoubleTapped: {
                            var person=panel.currentModel.get(row)
                            var fieldCount=tabs.currentIndex===0 ? center.pendingFieldCount : center.sentFieldCount
                            if(column>0 && column<=fieldCount) panel.openCellEditor(person,column-1)
                        }
                    }
                }
            }
            Label { anchors.centerIn: parent; visible: tabs.currentIndex===0 ? center.pendingCount===0 : center.sentCount===0; text: center.selectedIndex<0 ? "先新建名单，或从催办 / 画像生成名单" : tabs.currentIndex===0 ? "本名单暂无待处理人员" : "本名单还没有已发送记录"; color: "#98a2b3" }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: panel.selectedRow.id ? "当前："+panel.selectedRow.name : "选择一位收件人，查看或编辑消息"; textFormat: Text.PlainText; elide: Text.ElideRight; Layout.fillWidth: true; color: UiTheme.ink }
            UiButton { objectName: "groupEditCellButton"; text: panel.selectedRow.editable && tabs.currentIndex===0 ? "编辑所选消息" : "查看所选消息"; enabled: !center.active && !!panel.selectedRow.id && panel.selectedField>=0 && panel.selectedField<(panel.selectedRow.items || []).length; onClicked: panel.openCellEditor(panel.selectedRow,panel.selectedField) }
            UiButton { objectName: "groupEditPersonButton"; text: panel.selectedRow.editable && tabs.currentIndex===0 ? "编辑此人全部消息" : "查看此人全部消息"; enabled: !!panel.selectedRow.id && !center.active; onClicked: panel.openEditor() }
        }
        Label { text: (panel.selectedRow.state || "") + " " + (panel.selectedRow.detail || "") + (panel.selectedRow.sync_pending ? "（催办结果尚未回写）" : ""); visible: !!panel.selectedRow.id; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.warning }
        RowLayout {
            visible: panel.selectedRow.state==="结果待确认" || panel.selectedRow.state==="仅粘贴未发送"
            enabled: !center.active
            Label { text: "核实前不可编辑或重发" }
            UiButton { text: "核实已发送"; onClicked: panel.resolveRequested(panel.selectedRow.id,true) }
            UiButton { text: "核实未发送"; onClicked: panel.resolveRequested(panel.selectedRow.id,false) }
        }
    }
    Dialog {
        id: fieldDialog; objectName: "groupColumnMessageDialog"; anchors.centerIn: parent; modal: true; title: fieldDialog.isAdding ? (fieldDialog.fieldType==="file" ? "新增文件字段" : "新增文字字段") : (fieldDialog.fieldType==="file" ? "统一配置文件列" : "统一配置话术列")
        width: Math.min(panel.width-20,620)
        property int fieldIndex: -1
        property int listId: 0
        property string fieldType: "text"
        property string fieldValue: ""
        property bool overridePersonal: false
        property bool isAdding: false
        property int impactCount: 0
        property var columnSummary: ({})
        function updateImpact() {
            if(visible) {
                columnSummary=isAdding ? ({}) : center.columnInfo(fieldIndex,overridePersonal)
                impactCount=isAdding ? center.editableCount : columnSummary.count
            }
        }
        onVisibleChanged: updateImpact()
        onFieldIndexChanged: updateImpact()
        onOverridePersonalChanged: updateImpact()
        onOpened: { columnText.text=fieldType==="text" ? fieldValue : ""; columnFile.text=fieldType==="file" ? fieldValue : ""; updateImpact() }
        ColumnLayout {
            anchors.fill: parent
            Label { text: fieldDialog.isAdding ? "将为 " + fieldDialog.impactCount + " 位可编辑人员追加消息。" : "将修改 " + fieldDialog.impactCount + " 人 · " + (fieldDialog.overridePersonal ? "包含" : "保留") + " " + (fieldDialog.columnSummary.personalCount || 0) + " 人的个人改动"; wrapMode: Text.Wrap; Layout.fillWidth: true; font.bold: true }
            Label { text: "已发送、发送中和待核实记录不修改；保存后重新预览。"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            RowLayout {
                visible: !fieldDialog.isAdding && !!fieldDialog.columnSummary.mixed
                Layout.fillWidth: true
                Label { text: "此列含文字和文件，统一改为：" }
                UiComboBox { model: ["文字","文件"]; currentIndex: fieldDialog.fieldType==="file" ? 1 : 0; onActivated: fieldDialog.fieldType=currentIndex===1 ? "file" : "text" }
            }
            ScrollView {
                visible: fieldDialog.fieldType==="text"; Layout.fillWidth: true; Layout.preferredHeight: 120; clip: true
                TextArea { id: columnText; objectName: "groupColumnTemplateInput"; wrapMode: TextEdit.Wrap; selectByMouse: true; placeholderText: "输入统一模板，可使用 {姓名}、{学号} 和画像字段变量" }
            }
            RowLayout {
                visible: fieldDialog.fieldType==="file"; Layout.fillWidth: true
                UiTextField { id: columnFile; readOnly: true; Layout.fillWidth: true; placeholderText: "选择统一文件" }
                UiButton { text: "选择文件"; onClicked: { var path=center.chooseMessageFile(); if(path) columnFile.text=path } }
            }
            CheckBox { visible: !fieldDialog.isAdding; text: "同时覆盖单独编辑过的内容"; checked: fieldDialog.overridePersonal; onToggled: fieldDialog.overridePersonal=checked; Layout.fillWidth: true }
            Label { text: "文字变量：{" + backend.profilesModule.messagePlaceholders.join("}、{") + "}；另支持 {学号}。保存后需重新预览。"; visible: fieldDialog.fieldType==="text"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted }
            Label { text: center.status; wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.warning }
            RowLayout {
                UiButton { objectName: "saveGroupColumnField"; text: (fieldDialog.isAdding ? "追加到 " : "保存到 ") + fieldDialog.impactCount + " 人"; highlighted: true; enabled: !center.active && fieldDialog.listId===center.selected.id && fieldDialog.impactCount>0 && (fieldDialog.fieldType==="text" ? columnText.text.trim().length>0 : columnFile.text.length>0); onClicked: { var item=fieldDialog.fieldType==="text" ? {type:"text",text:columnText.text} : {type:"file",path:columnFile.text}; var ok=fieldDialog.isAdding ? center.appendField(item) : center.bulkField(fieldDialog.listId,fieldDialog.fieldIndex,item,fieldDialog.overridePersonal); if(ok) { if(fieldDialog.isAdding) selectedField=panel.maxFieldIndex(); fieldDialog.close() } } }
                UiButton { text: "取消"; onClicked: fieldDialog.close() }
            }
        }
    }
    Menu {
        id: addMenu
        MenuItem { text: "添加文字消息"; onTriggered: panel.addMessage("text") }
        MenuItem { text: "添加文件消息"; onTriggered: panel.addMessage("file") }
    }
    Menu {
        id: columnMenu
        MenuItem { text: "向前移动（立即保存）"; enabled: panel.selectedField>0; onTriggered: panel.moveColumn(-1) }
        MenuItem { text: "向后移动（立即保存）"; enabled: panel.selectedField<center.pendingFieldCount-1; onTriggered: panel.moveColumn(1) }
        MenuSeparator {}
        MenuItem { text: "删除本列…"; onTriggered: { deleteConfirm.listId=center.selected.id; deleteConfirm.fieldIndex=panel.selectedField; deleteConfirm.open() } }
    }
    Dialog {
        id: deleteConfirm; anchors.centerIn: parent; modal: true; title: "删除消息字段"; standardButtons: Dialog.Yes | Dialog.No
        property int listId: 0
        property int fieldIndex: -1
        Label { text: "从可继续发送人员中删除所选字段？已发送和待核实人员的内容与发送记录保持不变。"; wrapMode: Text.Wrap }
        onAccepted: { if(listId===center.selected.id && center.removeField(fieldIndex)) selectedField=-1 }
    }
    Dialog {
        id: cellDialog; objectName: "groupSingleCellDialog"; anchors.centerIn: parent; modal: true
        title: (canEdit ? "修改 " : "查看 ") + personName + " 的" + (fieldType==="file" ? "文件" : "话术")
        width: Math.min(panel.width-20,560)
        property int listId: 0
        property int recipientId: 0
        property int fieldIndex: -1
        property string fieldType: "text"
        property string fieldValue: ""
        property string personName: ""
        property bool canEdit: false
        onOpened: { cellText.text=fieldType==="text" ? fieldValue : ""; cellFile.text=fieldType==="file" ? fieldValue : "" }
        ColumnLayout {
            anchors.fill: parent
            Label { text: cellDialog.canEdit ? "只修改这个单元格，其他消息保持不变。" : "该记录当前只能查看。"; Layout.fillWidth: true; wrapMode: Text.Wrap }
            ScrollView {
                visible: cellDialog.fieldType==="text"; Layout.fillWidth: true; Layout.preferredHeight: 160; clip: true
                TextArea { id: cellText; objectName: "groupSingleCellText"; readOnly: !cellDialog.canEdit; wrapMode: TextEdit.Wrap; selectByMouse: true }
            }
            RowLayout {
                visible: cellDialog.fieldType==="file"; Layout.fillWidth: true
                UiTextField { id: cellFile; readOnly: true; Layout.fillWidth: true }
                UiButton { text: "更换文件"; visible: cellDialog.canEdit; enabled: !center.active; onClicked: { var path=center.chooseMessageFile(); if(path) cellFile.text=path } }
            }
            Label { text: center.status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning }
            RowLayout {
                UiButton { text: "关闭"; onClicked: cellDialog.close() }
                UiButton { objectName: "saveGroupSingleCell"; text: "保存此格"; visible: cellDialog.canEdit; enabled: !center.active && (cellDialog.fieldType==="text" ? cellText.text.trim().length>0 : cellFile.text.length>0); highlighted: true; onClicked: { var item=cellDialog.fieldType==="text" ? {type:"text",text:cellText.text} : {type:"file",path:cellFile.text}; if(center.saveRecipientField(cellDialog.listId,cellDialog.recipientId,cellDialog.fieldIndex,item)) cellDialog.close() } }
            }
        }
    }
    Dialog {
        id: editor; objectName: "recipientMessageEditor"
        anchors.centerIn: parent; modal: true
        width: Math.min(parent.width,700); height: Math.min(parent.height,600)
        property int listId: 0
        property int recipientId: 0
        property bool canEdit: false
        ColumnLayout {
            anchors.fill: parent
            Label { text: editor.canEdit ? "仅修改此人；可增删文字、文件并调整顺序。内容按原文保存，不再替换变量。" : "已发送或待核实记录只读，保留发送时内容。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
            ScrollView {
                id: scroll; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                MessageFields { id: messages; objectName: "recipientMessageFields"; width: scroll.availableWidth; enabled: editor.canEdit && !center.active }
            }
            Label { text: center.status; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                UiButton { text: "关闭"; onClicked: editor.close() }
                UiButton { text: "保存该学员消息"; visible: editor.canEdit; enabled: !center.active; onClicked: { if(center.saveRecipientContent(editor.listId,editor.recipientId,messages.values())) editor.close() } }
            }
        }
    }
}
