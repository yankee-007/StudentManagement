import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: panel
    objectName: "recipientMessages"
    required property var center
    property alias contactPrefix: prefix.text
    property var selectedRow: ({})
    property int selectedField: -1
    property int currentListId: -1
    property var currentModel: tabs.currentIndex===0 ? center.pendingModel : center.sentModel
    property int fieldCount: tabs.currentIndex===0 ? center.pendingFieldCount : center.sentFieldCount
    property bool canManage: !center.active && center.editableCount>0
    property bool defaultsDirty: false
    property bool loadingDefaults: false
    readonly property bool compact: height<420
    property string draftRevision: ""
    property real nameWidth: width<750 ? 120 : 180
    property real infoWidth: width<750 ? 150 : 220
    property real messageWidth: Math.max(210,(messageArea.width-Math.max(0,fieldCount-1))/Math.max(1,fieldCount))
    signal prefixEdited()
    signal resolveRequested(int recipientId, bool wasSent)
    function loadDefaults() {
        loadingDefaults=true
        defaults.clear()
        var fields=center.defaultFields
        for(var i=0;i<fields.length;i++) defaults.append({sourceIndex:fields[i].sourceIndex,kind:fields[i].type,value:fields[i].value,mixed:fields[i].mixed})
        draftRevision=center.contentRevision
        defaultsDirty=false
        overridePersonal.checked=false
        loadingDefaults=false
    }
    function draftValues() {
        var result=[]
        for(var i=0;i<defaults.count;i++) {
            var f=defaults.get(i)
            result.push({sourceIndex:f.sourceIndex,type:f.kind,value:f.value})
        }
        return result
    }
    function updateDefault(index,value) {
        if(!loadingDefaults && defaults.get(index).value!==value) {
            defaults.setProperty(index,"value",value)
            defaultsDirty=true
        }
    }
    function addDefault(kind) {
        defaults.append({sourceIndex:-1,kind:kind,value:"",mixed:false})
        defaultsDirty=true
        Qt.callLater(function() { defaultsScroll.contentX=Math.max(0,defaultsScroll.contentWidth-defaultsScroll.width) })
    }
    function removeDefault() {
        if(defaults.count>0) { defaults.remove(defaults.count-1); defaultsDirty=true }
    }
    function saveDefaults() {
        Qt.inputMethod.commit()
        if(!defaultsDirty) return true
        if(!canManage || currentListId!==center.selected.id) return false
        console.log('DSHPROBE draft', draftRevision, 'current', center.contentRevision, 'listId', currentListId)
        if(!center.saveDefaultRow(currentListId,draftRevision,draftValues(),overridePersonal.checked)) return false
        loadDefaults()
        return true
    }
    function editRecipient(recipientId) {
        if(!saveDefaults()) return
        tabs.currentIndex=0
        selectedRow=center.recipientForView(recipientId,false)
        openEditor()
    }
    function openEditor() {
        if(!selectedRow.id || !saveDefaults()) return
        editor.listId=center.selected.id
        editor.recipientId=selectedRow.id
        editor.canEdit=selectedRow.editable && !center.active
        editor.title=(editor.canEdit ? "编辑消息 · " : "查看消息 · ") + selectedRow.name
        messages.load(selectedRow.items)
        editor.open()
    }
    function openCellEditor(person,index) {
        if(!person.id || index<0 || index>=person.items.length || !saveDefaults()) return
        person=center.recipientForView(person.id,tabs.currentIndex===1)
        if(index>=person.items.length) return
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
        if(selectedRow.id) selectedRow=center.recipientForView(selectedRow.id,tabs.currentIndex===1)
    }
    function selectPerson(row,column) {
        selectedRow=currentModel.get(row)
        selectedField=column>0 && column<=fieldCount ? column-1 : -1
    }
    Connections {
        target: panel.center
        function onSelectionChanged() {
            var listId=center.selected.id || 0
            if(listId!==panel.currentListId) {
                panel.currentListId=listId
                tabs.currentIndex=0
                panel.selectedRow=({})
                panel.selectedField=-1
                panel.loadDefaults()
            }
        }
        function onRowsChanged() {
            panel.restoreSelection()
            if(!panel.defaultsDirty) panel.loadDefaults()
        }
        function onModelInfoChanged() { table.forceLayout(); namesTable.forceLayout(); infoTable.forceLayout() }
    }
    Component.onCompleted: { currentListId=center.selected.id || 0; loadDefaults() }
    ListModel { id: defaults }
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            UiPanel {
                Layout.preferredWidth: panel.nameWidth; Layout.minimumWidth: panel.nameWidth; Layout.maximumWidth: panel.nameWidth
                Layout.preferredHeight: panel.compact ? 96 : 140; padding: panel.compact ? 8 : 12
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: "姓名前缀"; font.bold: true; font.pixelSize: 15 }
                    UiTextField {
                        id: prefix; objectName: "groupContactPrefix"; Layout.fillWidth: true
                        enabled: !center.active && center.selectedIndex>=0
                        placeholderText: "可留空"; Accessible.name: "姓名前缀"
                        onTextChanged: panel.prefixEdited()
                    }
                    Label { visible: !panel.compact; text: "前缀＋姓名\n自动保存"; Layout.fillWidth: true; color: UiTheme.muted; font.pixelSize: 12 }
                    Item { Layout.fillHeight: true }
                }
            }
            UiPanel {
                objectName: "groupDefaultRow"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredHeight: panel.compact ? 96 : 140; padding: panel.compact ? 8 : 12
                ColumnLayout {
                    anchors.fill: parent; spacing: 4
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        Label { text: "默认消息"; font.bold: true; font.pixelSize: 15; Layout.fillWidth: true; elide: Text.ElideRight }
                        UiButton { objectName: "groupResetDefaults"; text: "重载"; visible: panel.defaultsDirty; enabled: !center.active; implicitHeight: 28; onClicked: panel.loadDefaults() }
                        UiButton { objectName: "groupApplyDefaults"; text: "应用"; implicitHeight: 28; enabled: panel.canManage && panel.defaultsDirty; onClicked: panel.saveDefaults() }
                        UiButton { objectName: "groupRemoveDefault"; text: "−"; implicitWidth: 28; implicitHeight: 28; enabled: panel.canManage && defaults.count>0; Accessible.name: "移除最后一条默认消息"; ToolTip.visible: hovered; ToolTip.text: "移除最后一条消息，应用后生效"; onClicked: panel.removeDefault() }
                        UiButton { objectName: "groupAddDefault"; text: "+"; implicitWidth: 28; implicitHeight: 28; enabled: panel.canManage; Accessible.name: "添加默认消息"; onClicked: panel.addDefault("text") }
                    }
                    Flickable {
                        id: defaultsScroll; objectName: "groupDefaultsViewport"; Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; contentWidth: draftRow.width; contentHeight: height; boundsBehavior: Flickable.StopAtBounds
                        onContentXChanged: if(dragging || flicking) table.contentX=contentX
                        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                        Row {
                            id: draftRow; spacing: 1; height: defaultsScroll.height-12
                            Repeater {
                                model: defaults
                                Rectangle {
                                    id: draftField
                                    required property int index
                                    required property int sourceIndex
                                    required property string kind
                                    required property string value
                                    required property bool mixed
                                    width: panel.messageWidth; height: draftRow.height; color: UiTheme.stripe
                                    ColumnLayout {
                                        anchors.fill: parent; anchors.margins: 4; spacing: 2; enabled: panel.canManage
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Label { text: "消息"+(draftField.index+1); color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                                            UiComboBox {
                                                objectName: "groupDefaultType"+draftField.index; model: ["文字","文件"]; implicitHeight: panel.compact ? 22 : 26; implicitWidth: 76
                                                currentIndex: draftField.kind==="file" ? 1 : 0; Accessible.name: "消息"+(draftField.index+1)+"类型"
                                                onActivated: { defaults.setProperty(draftField.index,"kind",currentIndex===1 ? "file" : "text"); defaults.setProperty(draftField.index,"value",""); panel.defaultsDirty=true }
                                            }
                                        }
                                        ScrollView {
                                            id: defaultTextScroll; visible: draftField.kind==="text"; Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; clip: true
                                            TextArea {
                                            objectName: "groupDefaultText"+draftField.index; width: defaultTextScroll.availableWidth; text: draftField.value
                                            font.pixelSize: 13; color: UiTheme.ink; wrapMode: TextEdit.Wrap; selectByMouse: true
                                            placeholderText: draftField.mixed ? "此列内容不同，填写以统一" : "填写默认消息，可用 {姓名}"
                                            Accessible.name: "消息"+(draftField.index+1)+"默认文字"
                                            background: Rectangle { color: UiTheme.input; border.color: parent.activeFocus ? UiTheme.focus : UiTheme.line; radius: 3 }
                                            onTextChanged: if(!inputMethodComposing) panel.updateDefault(draftField.index,text)
                                            onInputMethodComposingChanged: if(!inputMethodComposing) panel.updateDefault(draftField.index,text)
                                            }
                                        }
                                        RowLayout {
                                            visible: draftField.kind==="file"; Layout.fillWidth: true; Layout.fillHeight: true
                                            UiTextField { text: draftField.value; readOnly: true; Layout.fillWidth: true; placeholderText: "未选择文件"; Accessible.name: "消息"+(draftField.index+1)+"默认文件" }
                                            UiButton { objectName: "groupDefaultFile"+draftField.index; text: "选择"; onClicked: { var path=center.chooseMessageFile(); if(path) panel.updateDefault(draftField.index,path) } }
                                        }
                                    }
                                }
                            }
                        }
                        Label { anchors.centerIn: parent; visible: defaults.count===0; text: "点击 + 添加默认消息"; color: UiTheme.muted }
                    }
                }
            }
            UiPanel {
                objectName: "groupStatistics"; Layout.preferredWidth: panel.infoWidth; Layout.minimumWidth: panel.infoWidth; Layout.maximumWidth: panel.infoWidth; Layout.preferredHeight: panel.compact ? 96 : 140; padding: panel.compact ? 8 : 12
                ColumnLayout {
                    anchors.fill: parent; spacing: 6
                    Label { text: "状态统计"; font.bold: true; font.pixelSize: 15 }
                    GridLayout {
                        visible: !panel.compact; columns: 2; Layout.fillWidth: true; rowSpacing: 6
                        Label { text: "成功"; color: UiTheme.muted; Layout.fillWidth: true }
                        Label { objectName: "groupSuccessCount"; text: center.statistics.success; color: UiTheme.success; font.bold: true }
                        Label { text: "失败"; color: UiTheme.muted }
                        Label { objectName: "groupFailureCount"; text: center.statistics.failed; color: UiTheme.danger; font.bold: true }
                        Label { text: "待发"; color: UiTheme.muted }
                        Label { objectName: "groupPendingCount"; text: center.statistics.pending; color: UiTheme.warning; font.bold: true }
                        Label { text: "待核实"; color: UiTheme.muted }
                        Label { objectName: "groupUncertainCount"; text: center.statistics.uncertain; color: UiTheme.muted; font.bold: true }
                    }
                    GridLayout {
                        visible: panel.compact; columns: 2; Layout.fillWidth: true; rowSpacing: 8; columnSpacing: 8
                        Label { text: "成功 "+center.statistics.success; color: UiTheme.success; font.pixelSize: 12 }
                        Label { text: "失败 "+center.statistics.failed; color: UiTheme.danger; font.pixelSize: 12 }
                        Label { text: "待发 "+center.statistics.pending; color: UiTheme.warning; font.pixelSize: 12 }
                        Label { text: "待核实 "+center.statistics.uncertain; color: UiTheme.muted; font.pixelSize: 12 }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            TabBar {
                id: tabs; objectName: "groupMessageTabs"; Layout.fillWidth: true; implicitHeight: 30
                onCurrentIndexChanged: { panel.selectedRow=({}); panel.selectedField=-1 }
                TabButton { text: "待处理（"+center.pendingCount+"）"; implicitHeight: 30 }
                TabButton { text: "已发送（"+center.sentCount+"）"; implicitHeight: 30 }
            }
            CheckBox { id: overridePersonal; objectName: "groupOverridePersonal"; text: panel.width<750 ? "覆盖个人改动" : "应用时覆盖个人改动"; enabled: panel.canManage; implicitHeight: 30; onToggled: if(!panel.loadingDefaults) panel.defaultsDirty=true }
            UiButton { id: compactActions; objectName: "groupCompactRecipientActions"; visible: panel.compact; text: "编辑"; implicitHeight: 30; enabled: !!panel.selectedRow.id && !center.active; onClicked: recipientMenu.popup(compactActions,0,compactActions.height) }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
            UiPanel {
                Layout.preferredWidth: panel.nameWidth; Layout.minimumWidth: panel.nameWidth; Layout.maximumWidth: panel.nameWidth; Layout.fillHeight: true; padding: 8
                ColumnLayout {
                    anchors.fill: parent; spacing: 1
                    Label { text: "姓名"; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.bold: true; Layout.preferredHeight: 34; background: Rectangle { color: UiTheme.stripe } }
                    TableView {
                        id: namesTable; objectName: "groupNamesTable"; Layout.fillWidth: true; Layout.fillHeight: true
                        model: panel.currentModel; syncView: table; syncDirection: Qt.Vertical; clip: true; reuseItems: true; rowSpacing: 1
                        columnWidthProvider: function(c) { return c===0 ? namesTable.width : 0 }; rowHeightProvider: function(r) { return 44 }
                        delegate: Rectangle {
                            required property int row
                            required property string display
                            required property string recordKey
                            implicitWidth: 120; implicitHeight: 44; color: recordKey===String(panel.selectedRow.id || "") ? UiTheme.selection : row%2 ? UiTheme.stripe : UiTheme.surface
                            Label { anchors.fill: parent; anchors.margins: 7; text: (row+1)+"  "+display; elide: Text.ElideRight; textFormat: Text.PlainText }
                            TapHandler { onTapped: panel.selectPerson(row,0) }
                        }
                    }
                }
            }
            UiPanel {
                id: messageArea; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0; padding: 8
                ColumnLayout {
                    anchors.fill: parent; spacing: 1
                    HorizontalHeaderView {
                        id: header; syncView: table; Layout.fillWidth: true; Layout.preferredHeight: 34; clip: true
                        delegate: Rectangle {
                            required property var display
                            required property int index
                            implicitWidth: panel.messageWidth; implicitHeight: 34; color: UiTheme.stripe
                            Label { anchors.fill: parent; anchors.margins: 7; text: panel.fieldCount===0 ? "消息" : display; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter; font.bold: true }
                        }
                    }
                    TableView {
                        id: table; objectName: "groupRecipientList"; Layout.fillWidth: true; Layout.fillHeight: true
                        model: panel.currentModel; clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                        columnWidthProvider: function(c) { return c>0 && c<=panel.fieldCount ? panel.messageWidth : (panel.fieldCount===0 && c===0 ? table.width : 0) }
                        rowHeightProvider: function(r) { return 44 }
                        onContentXChanged: if(!defaultsScroll.dragging && !defaultsScroll.flicking) defaultsScroll.contentX=Math.min(contentX,Math.max(0,defaultsScroll.contentWidth-defaultsScroll.width))
                        ScrollBar.horizontal: ScrollBar {}
                        ScrollBar.vertical: ScrollBar {}
                        delegate: Rectangle {
                            required property int row
                            required property int column
                            required property string display
                            required property string recordKey
                            implicitWidth: panel.messageWidth; implicitHeight: 44
                            color: recordKey===String(panel.selectedRow.id || "") ? UiTheme.selection : row%2 ? UiTheme.stripe : UiTheme.surface
                            border.width: recordKey===String(panel.selectedRow.id || "") && column===panel.selectedField+1 ? 1 : 0; border.color: UiTheme.focus
                            Text { anchors.fill: parent; anchors.margins: 7; text: panel.fieldCount===0 ? "尚未配置消息" : display; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: 13; color: panel.fieldCount===0 ? UiTheme.muted : UiTheme.ink }
                            TapHandler {
                                onTapped: panel.selectPerson(row,column)
                                onDoubleTapped: if(column>0 && column<=panel.fieldCount) panel.openCellEditor(panel.currentModel.get(row),column-1)
                            }
                        }
                    }
                    Label { visible: (tabs.currentIndex===0 ? center.pendingCount : center.sentCount)===0; text: center.selectedIndex<0 ? "先新建或生成名单" : "暂无人员"; color: UiTheme.muted; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                }
            }
            UiPanel {
                Layout.preferredWidth: panel.infoWidth; Layout.minimumWidth: panel.infoWidth; Layout.maximumWidth: panel.infoWidth; Layout.fillHeight: true; padding: 8
                ColumnLayout {
                    anchors.fill: parent; spacing: 1
                    Label { text: "信息"; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.bold: true; Layout.preferredHeight: 34; background: Rectangle { color: UiTheme.stripe } }
                    TableView {
                        id: infoTable; objectName: "groupInformationTable"; Layout.fillWidth: true; Layout.fillHeight: true
                        model: panel.currentModel; syncView: table; syncDirection: Qt.Vertical; clip: true; reuseItems: true; rowSpacing: 1
                        columnWidthProvider: function(c) { return c===panel.fieldCount+2 ? infoTable.width : 0 }; rowHeightProvider: function(r) { return 44 }
                        delegate: Rectangle {
                            required property int row
                            required property string display
                            required property string recordKey
                            property var person: { var revision=center.contentRevision; return panel.currentModel.get(row) }
                            implicitWidth: 160; implicitHeight: 44; color: recordKey===String(panel.selectedRow.id || "") ? UiTheme.selection : row%2 ? UiTheme.stripe : UiTheme.surface
                            Text { anchors.fill: parent; anchors.margins: 7; text: (parent.person.state || "")+(display ? " · "+display : ""); textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: 12; color: parent.person.state==="已发送" ? UiTheme.success : parent.person.state==="未发送失败" ? UiTheme.danger : UiTheme.muted }
                            TapHandler { onTapped: panel.selectPerson(row,-1) }
                            ToolTip.visible: infoHover.hovered; ToolTip.text: (person.state || "")+" "+display
                            HoverHandler { id: infoHover }
                        }
                    }
                }
            }
        }
        RowLayout {
            visible: !panel.compact; Layout.fillWidth: true
            Label { text: panel.selectedRow.id ? "当前："+panel.selectedRow.name : "默认消息在上方统一配置"; textFormat: Text.PlainText; elide: Text.ElideRight; Layout.fillWidth: true; color: UiTheme.muted }
            UiButton { objectName: "groupEditCellButton"; text: "单独编辑"; enabled: !center.active && !!panel.selectedRow.id && panel.selectedField>=0 && panel.selectedField<(panel.selectedRow.items || []).length; onClicked: panel.openCellEditor(panel.selectedRow,panel.selectedField) }
            UiButton { objectName: "groupEditPersonButton"; text: tabs.currentIndex===0 && panel.selectedRow.editable ? "此人全部消息" : "查看全部消息"; enabled: !!panel.selectedRow.id && !center.active; onClicked: panel.openEditor() }
        }
        RowLayout {
            visible: panel.selectedRow.state==="结果待确认" || panel.selectedRow.state==="仅粘贴未发送"; enabled: !center.active; Layout.fillWidth: true
            Label { text: "核实前不可编辑或重发"; Layout.fillWidth: true; color: UiTheme.warning }
            UiButton { text: "核实已发送"; onClicked: panel.resolveRequested(panel.selectedRow.id,true) }
            UiButton { text: "核实未发送"; onClicked: panel.resolveRequested(panel.selectedRow.id,false) }
        }
    }
    Menu {
        id: recipientMenu
        MenuItem { text: "编辑所选消息"; enabled: panel.selectedField>=0 && panel.selectedField<(panel.selectedRow.items || []).length; onTriggered: panel.openCellEditor(panel.selectedRow,panel.selectedField) }
        MenuItem { text: "查看或编辑此人全部消息"; onTriggered: panel.openEditor() }
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
