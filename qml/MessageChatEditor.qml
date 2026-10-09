import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: chat
    required property var fileChooser
    property string controlPrefix: "chat"
    property bool editable: true
    property bool defaultTemplate: false
    property bool dirty: false
    property int editingIndex: -1
    property string editText: ""
    property string feedback: ""
    readonly property int messageCount: fields.count
    readonly property bool hasPending: editingIndex>=0 || composer.text.length>0
    readonly property bool compact: height<350
    signal committed()

    function load(items, preserveComposer) {
        // Keep delegates and the scroll anchor when refreshing a committed draft.
        if(!preserveComposer) fields.clear()
        editingIndex=-1
        editText=""
        for(var i=0;i<items.length;i++) {
            var item=items[i]
            var field={sourceIndex: defaultTemplate ? item.sourceIndex : -1,
                kind:item.type, value:defaultTemplate ? item.value : (item.type==="file" ? item.path : item.text),
                mixed:defaultTemplate && !!item.mixed}
            if(i<fields.count) fields.set(i,field)
            else fields.append(field)
        }
        if(fields.count>items.length) fields.remove(items.length,fields.count-items.length)
        if(!preserveComposer) composer.text=""
        dirty=false
        feedback=""
    }
    function values() {
        var result=[]
        for(var i=0;i<fields.count;i++) {
            var item=fields.get(i)
            result.push(defaultTemplate ? {sourceIndex:item.sourceIndex,type:item.kind,value:item.value}
                : item.kind==="file" ? {type:"file",path:item.value} : {type:"text",text:item.value})
        }
        return result
    }
    function changed() { dirty=true; feedback=""; committed() }
    function revealEnd() { Qt.callLater(function() { thread.positionViewAtEnd() }) }
    function revealEditing() {
        var index=editingIndex
        Qt.callLater(function() {
            if(index>=0 && index===editingIndex) { thread.forceLayout(); thread.positionViewAtIndex(index,ListView.Contain) }
        })
    }
    function addText() {
        if(!editable || editingIndex>=0 || composer.inputMethodComposing) return
        if(!composer.text.trim()) { composer.forceActiveFocus(); return }
        fields.append({sourceIndex:-1,kind:"text",value:composer.text,mixed:false})
        composer.text=""
        changed()
        revealEnd()
        composer.forceActiveFocus()
    }
    function addFile() {
        if(!editable || editingIndex>=0) return
        var path=fileChooser.chooseMessageFile()
        if(path) { fields.append({sourceIndex:-1,kind:"file",value:path,mixed:false}); changed(); revealEnd() }
    }
    function beginEdit(index) {
        if(!editable || editingIndex>=0) return
        var item=fields.get(index)
        if(item.kind==="file") {
            var path=fileChooser.chooseMessageFile()
            if(path) { fields.setProperty(index,"value",path); fields.setProperty(index,"mixed",false); changed() }
        } else {
            editText=item.value
            editingIndex=index
            revealEditing()
        }
    }
    function saveEdit() {
        if(!editable || editingIndex<0 || !editText.trim()) return
        fields.setProperty(editingIndex,"value",editText)
        fields.setProperty(editingIndex,"mixed",false)
        editingIndex=-1
        changed()
    }
    function cancelEdit() { editingIndex=-1; editText=""; feedback="" }
    function removeMessage(index) {
        if(!editable || editingIndex>=0) return
        fields.remove(index)
        changed()
    }
    function moveMessage(index, direction) {
        var target=index+direction
        if(!editable || editingIndex>=0 || target<0 || target>=fields.count) return
        fields.move(index,target,1)
        changed()
    }
    function checkPending() {
        Qt.inputMethod.commit()
        if(!hasPending) return true
        feedback=editingIndex>=0 ? "请先保存或取消正在编辑的消息。" : "输入框还有未加入的消息，请按回车加入或清空输入。"
        if(editingIndex<0) composer.forceActiveFocus()
        return false
    }
    function fileName(path) { return path.replace(/\\/g,"/").split("/").pop() }

    ListModel { id: fields }
    ColumnLayout {
        anchors.fill: parent; spacing: 6
        ListView {
            id: thread; objectName: chat.controlPrefix+"Thread"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 35
            clip: true; spacing: 14; model: fields; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Item {
                id: bubble
                required property int index
                required property string kind
                required property string value
                required property bool mixed
                readonly property string displayText: mixed ? "各人内容不同 · 编辑后统一" : kind==="file" ? "附件  ·  "+chat.fileName(value) : value
                width: thread.width
                height: bubbleColumn.implicitHeight+4
                Text {
                    id: naturalText; visible: false
                    text: bubble.displayText; textFormat: Text.PlainText
                    font: messageText.font; wrapMode: Text.NoWrap
                }
                ColumnLayout {
                    id: bubbleColumn; anchors.right: parent.right; anchors.rightMargin: 16
                    width: Math.min(thread.width-24,Math.max(220,Math.min(660,thread.width*0.86)))
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Item { Layout.fillWidth: true }
                        Label { text: "消息 "+(bubble.index+1); color: UiTheme.muted; font.pixelSize: 11 }
                        ToolButton {
                            objectName: chat.controlPrefix+"Edit"+bubble.index
                            visible: chat.editable; enabled: chat.editingIndex<0
                            text: "编辑"; font.pixelSize: 12; implicitHeight: 24
                            Accessible.name: "编辑消息"+(bubble.index+1)
                            onClicked: chat.beginEdit(bubble.index)
                        }
                        ToolButton {
                            objectName: chat.controlPrefix+"Delete"+bubble.index
                            visible: chat.editable; enabled: chat.editingIndex<0
                            text: "删除"; font.pixelSize: 12; implicitHeight: 24
                            Accessible.name: "删除消息"+(bubble.index+1)
                            ToolTip.visible: hovered
                            ToolTip.text: chat.defaultTemplate ? "删除这条消息及对应的个人改动" : "删除这条消息"
                            onClicked: chat.removeMessage(bubble.index)
                        }
                        ToolButton {
                            visible: chat.editable; enabled: chat.editingIndex<0
                            text: "顺序"; font.pixelSize: 12; implicitHeight: 24
                            Accessible.name: "调整消息"+(bubble.index+1)+"顺序"
                            onClicked: orderMenu.popup()
                            Menu {
                                id: orderMenu
                                MenuItem { text: "上移"; enabled: bubble.index>0; onTriggered: chat.moveMessage(bubble.index,-1) }
                                MenuItem { text: "下移"; enabled: bubble.index<chat.messageCount-1; onTriggered: chat.moveMessage(bubble.index,1) }
                            }
                        }
                    }
                    Rectangle {
                        objectName: chat.controlPrefix+"BubbleCard"+bubble.index
                        Layout.alignment: Qt.AlignRight
                        Layout.minimumWidth: Math.min(44,bubbleColumn.width)
                        Layout.maximumWidth: bubbleColumn.width
                        Layout.preferredWidth: chat.editingIndex===bubble.index ? bubbleColumn.width : Math.min(bubbleColumn.width,naturalText.implicitWidth+24)
                        implicitHeight: body.implicitHeight+24
                        color: UiTheme.selection; radius: 12
                        ColumnLayout {
                            id: body; anchors.fill: parent; anchors.margins: 12; spacing: 6
                            Label {
                                id: messageText
                                objectName: chat.controlPrefix+"Bubble"+bubble.index
                                visible: chat.editingIndex!==bubble.index
                                Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                                text: bubble.displayText
                                color: bubble.mixed ? UiTheme.muted : UiTheme.ink; font.pixelSize: 14
                                ToolTip.visible: fileHover.hovered && bubble.kind==="file"
                                ToolTip.text: bubble.value
                                HoverHandler { id: fileHover }
                            }
                            ScrollView {
                                id: inlineScroll; objectName: chat.controlPrefix+"InlineScroll"+bubble.index; visible: chat.editingIndex===bubble.index
                                Layout.fillWidth: true; Layout.preferredHeight: Math.max(50,Math.min(160,inlineText.implicitHeight,thread.height-100))
                                contentWidth: availableWidth; clip: true
                                onHeightChanged: if(visible) chat.revealEditing()
                            TextArea {
                                id: inlineText; objectName: chat.controlPrefix+"Inline"+bubble.index
                                width: inlineScroll.availableWidth; readOnly: !chat.editable
                                text: chat.editingIndex===bubble.index ? chat.editText : ""
                                wrapMode: TextEdit.Wrap; selectByMouse: true; color: UiTheme.ink; font.pixelSize: 14
                                placeholderText: bubble.mixed ? "填写消息后将统一此条内容" : "编辑消息"
                                background: Rectangle { color: UiTheme.input; border.color: inlineText.activeFocus ? UiTheme.focus : UiTheme.line; radius: 6 }
                                onVisibleChanged: if(visible && chat.editingIndex===bubble.index) Qt.callLater(function() { inlineText.forceActiveFocus() })
                                onTextChanged: if(chat.editingIndex===bubble.index) chat.editText=text
                                Keys.onPressed: function(event) {
                                    if((event.key===Qt.Key_Return || event.key===Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                        if(!inputMethodComposing && !event.isAutoRepeat) chat.saveEdit()
                                        event.accepted=true
                                    }
                                }
                            }
                            }
                            RowLayout {
                                visible: chat.editingIndex===bubble.index; Layout.fillWidth: true
                                Label { text: "Shift＋回车换行"; color: UiTheme.muted; font.pixelSize: 11; Layout.fillWidth: true }
                                UiButton { objectName: chat.editingIndex===bubble.index ? chat.controlPrefix+"CancelEdit" : ""; text: "取消"; implicitHeight: 28; onClicked: chat.cancelEdit() }
                                UiButton { objectName: chat.editingIndex===bubble.index ? chat.controlPrefix+"SaveEdit" : ""; text: "保存"; implicitHeight: 28; highlighted: true; enabled: chat.editable && chat.editText.trim().length>0; onClicked: { Qt.inputMethod.commit(); chat.saveEdit() } }
                            }
                        }
                    }
                }
            }
            Label {
                anchors.centerIn: parent; width: parent.width-30; horizontalAlignment: Text.AlignHCenter
                visible: chat.messageCount===0; wrapMode: Text.Wrap; color: UiTheme.muted
                text: chat.editable ? "像聊天一样写消息\n按回车加入第一条" : "暂无消息"
            }
        }
        Label { objectName: chat.controlPrefix+"Feedback"; visible: text.length>0; text: chat.feedback; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.warning; font.pixelSize: 12 }
        Rectangle {
            visible: chat.editable && chat.editingIndex<0; Layout.fillWidth: true
            implicitHeight: composerColumn.implicitHeight+16
            color: UiTheme.input; radius: 10; border.color: composer.activeFocus ? UiTheme.focus : UiTheme.line
            ColumnLayout {
                id: composerColumn; anchors.fill: parent; anchors.margins: 8; spacing: 4
                ScrollView {
                    id: inputScroll; Layout.fillWidth: true; Layout.preferredHeight: chat.compact ? 50 : 76
                    contentWidth: availableWidth; clip: true
                    TextArea {
                        id: composer; objectName: chat.controlPrefix+"Composer"; width: inputScroll.availableWidth
                        enabled: chat.editingIndex<0; placeholderText: chat.defaultTemplate ? "写一条消息，可用 {姓名} 等变量…" : "写一条仅发给此人的消息…"
                        wrapMode: TextEdit.Wrap; selectByMouse: true; font.pixelSize: 14; color: UiTheme.ink
                        background: null; Accessible.name: "待加入的消息"
                        onTextChanged: chat.feedback=""
                        Keys.onPressed: function(event) {
                            if((event.key===Qt.Key_Return || event.key===Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                if(!inputMethodComposing && !event.isAutoRepeat) chat.addText()
                                event.accepted=true
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    UiButton { objectName: chat.controlPrefix+"Attach"; text: "＋ 附件"; implicitHeight: 30; enabled: chat.editingIndex<0; onClicked: chat.addFile() }
                    Label { text: "回车加入 · Shift＋回车换行"; visible: chat.width>400; font.pixelSize: 11; color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
                    Item { visible: chat.width<=400; Layout.fillWidth: true }
                    UiButton { objectName: chat.controlPrefix+"Send"; text: "发送"; highlighted: true; implicitHeight: 30; enabled: chat.editingIndex<0 && composer.text.trim().length>0; ToolTip.visible: hovered; ToolTip.text: chat.defaultTemplate ? "加入消息模板，预览后再开始群发" : "加入个人消息，保存后生效"; onClicked: { Qt.inputMethod.commit(); chat.addText() } }
                }
            }
        }
    }
}
