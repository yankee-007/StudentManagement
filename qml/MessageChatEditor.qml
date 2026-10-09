import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

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
    property var activeEditor: null
    property var activeEditViewport: null
    property bool committing: false
    property bool commitAccepted: true
    property bool pendingOutsideCommit: false
    // Text inset inside a bubble; the cap keeps long messages readable at the thread width.
    readonly property int bubblePadding: 12
    readonly property int bubbleSlack: 2
    readonly property int messageCount: fields.count
    readonly property bool hasPending: editingIndex>=0 || composer.text.length>0
    readonly property bool compact: height<350
    signal committed()
    signal editCancelled()

    function load(items, preserveComposer) {
        // Keep delegates and the scroll anchor when refreshing a committed draft.
        if(!preserveComposer) fields.clear()
        editingIndex=-1
        pendingOutsideCommit=false
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
    function changed() { dirty=true; feedback=""; commitAccepted=true; committed(); return commitAccepted }
    function revealEnd() { Qt.callLater(function() { thread.positionViewAtEnd() }) }
    function revealEditing() {
        var index=editingIndex
        Qt.callLater(function() {
            if(index<0 || index!==editingIndex) return
            thread.cancelFlick(); thread.forceLayout(); thread.positionViewAtIndex(index,ListView.Contain)
            // Recheck after offscreen delegates have updated their measured height.
            Qt.callLater(function() {
                if(index!==editingIndex) return
                thread.forceLayout(); thread.positionViewAtIndex(index,ListView.Contain)
                var viewport=activeEditViewport
                if(!viewport) return
                var top=viewport.mapToItem(thread,0,0).y
                if(top<0) thread.contentY+=top
                else if(top+viewport.height>thread.height) thread.contentY+=top+viewport.height-thread.height
            })
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
    function appendFiles(result) {
        if(!editable || editingIndex>=0) return false
        if(result.error) { feedback=result.error; return false }
        if(!result.files.length) return false
        for(var i=0;i<result.files.length;i++) fields.append({sourceIndex:-1,kind:"file",value:result.files[i],mixed:false})
        changed(); revealEnd(); composer.forceActiveFocus()
        return true
    }
    function pasteFiles() {
        var result=fileChooser.clipboardMessageFiles()
        if(!result.handled) return false
        appendFiles(result)
        return true
    }
    function dropFiles(urls) { return appendFiles(fileChooser.messageFiles(urls)) }
    function beginEdit(index) {
        if(!editable || (editingIndex>=0 && !finishEdit(true))) return
        var item=fields.get(index)
        if(item.kind==="file") {
            var path=fileChooser.chooseMessageFile()
            if(path) { fields.setProperty(index,"value",path); fields.setProperty(index,"mixed",false); changed() }
        } else {
            activeEditor=null; activeEditViewport=null
            editText=item.value
            editingIndex=index
            revealEditing()
        }
    }
    function saveEdit() {
        if(!editable || editingIndex<0 || committing) return false
        if(!editText.trim()) {
            feedback="消息不能为空，请继续编辑或按 Esc 取消。"
            if(activeEditor) Qt.callLater(function() { if(chat.visible && chat.editingIndex>=0 && chat.activeEditor) chat.activeEditor.forceActiveFocus() })
            return false
        }
        committing=true
        var index=editingIndex
        var value=editText
        var previousValue=fields.get(index).value
        var previousMixed=fields.get(index).mixed
        var previousDirty=dirty
        fields.setProperty(editingIndex,"value",editText)
        fields.setProperty(editingIndex,"mixed",false)
        editingIndex=-1
        var saved=changed()
        if(!saved) {
            fields.setProperty(index,"value",previousValue)
            fields.setProperty(index,"mixed",previousMixed)
            dirty=previousDirty
            editText=value; editingIndex=index; revealEditing()
        }
        committing=false
        if(saved) pendingOutsideCommit=false
        return saved
    }
    function finishEdit(commitInput) { return resolveEdit(commitInput,false) }
    function finishOutsideEdit(commitInput) { return resolveEdit(commitInput,true) }
    function resolveEdit(commitInput, cancelEmpty) {
        if(editingIndex<0) return true
        if(committing || !editable) return false
        if(commitInput) Qt.inputMethod.commit()
        if(activeEditor && activeEditor.inputMethodComposing) return false
        if(activeEditor) editText=activeEditor.text
        if(cancelEmpty && !editText.trim()) { cancelEdit(); return true }
        return saveEdit()
    }
    function cancelEdit() { editingIndex=-1; editText=""; feedback=""; pendingOutsideCommit=false; editCancelled() }
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
        if(!finishEdit(true)) return false
        if(!hasPending) return true
        feedback="输入框还有未加入的消息，请按回车加入或清空输入。"
        if(editingIndex<0) composer.forceActiveFocus()
        return false
    }
    function fileName(path) { return path.replace(/\\/g,"/").split("/").pop() }
    // A {变量} placeholder stays in one piece when a long message wraps; word joiners add no width.
    function keepTokens(text) {
        return String(text).replace(/\{[^{}\s\n]{1,12}\}/g,function (token) {
            return token.split("").join("\u2060")
        })
    }

    ListModel { id: fields }
    MouseArea {
        id: outsideGuard; parent: Overlay.overlay; anchors.fill: parent; z: 100000
        enabled: chat.visible && chat.editable && chat.editingIndex>=0; acceptedButtons: Qt.LeftButton
        onWheel: function(wheel) { wheel.accepted=false }
        onPressed: function(mouse) {
            var viewport=chat.activeEditViewport
            var point=viewport ? viewport.mapFromItem(outsideGuard,mouse.x,mouse.y) : Qt.point(-1,-1)
            var inside=viewport && point.x>=0 && point.y>=0 && point.x<viewport.width && point.y<viewport.height
            if(!inside) chat.finishOutsideEdit(true)
            var composing=!inside && chat.activeEditor && chat.activeEditor.inputMethodComposing
            if(composing) chat.pendingOutsideCommit=true
            mouse.accepted=!!composing
        }
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 6
        ListView {
            id: thread; objectName: chat.controlPrefix+"Thread"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 35
            clip: true; spacing: 14; model: fields; boundsBehavior: Flickable.StopAtBounds
            currentIndex: chat.editingIndex; highlightFollowsCurrentItem: false
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: FocusScope {
                id: bubble
                required property int index
                required property string kind
                required property string value
                required property bool mixed
                readonly property string displayText: mixed ? "各人内容不同 · 编辑后统一" : kind==="file" ? "附件  ·  "+chat.fileName(value) : value
                readonly property string bubbleText: chat.keepTokens(displayText)
                // Hug the widest line instead of letting a rounded card wrap the last glyph:
                // only a message that really is wider than the column is wrapped.
                readonly property real hugWidth: Math.ceil(naturalText.implicitWidth)+2*chat.bubblePadding+chat.bubbleSlack
                readonly property bool hugContent: chat.editingIndex!==bubble.index && hugWidth<=bubbleColumn.width
                width: thread.width
                height: bubbleColumn.implicitHeight+4
                Text {
                    id: naturalText; visible: false
                    text: bubble.bubbleText; textFormat: Text.PlainText
                    font: messageText.font; wrapMode: Text.NoWrap
                }
                ColumnLayout {
                    id: bubbleColumn; anchors.right: parent.right; anchors.rightMargin: 16
                    width: Math.floor(Math.min(thread.width-24,Math.max(220,Math.min(660,thread.width*0.86))))
                    spacing: 4
                    HoverHandler { id: bubbleHover }
                    RowLayout {
                        id: bubbleActions; objectName: chat.controlPrefix+"Actions"+bubble.index
                        Layout.fillWidth: true; spacing: 6
                        opacity: bubbleHover.hovered || editButton.activeFocus || deleteButton.activeFocus || orderButton.activeFocus || orderMenu.visible ? 1 : 0
                        Item { Layout.fillWidth: true }
                        Label { text: "消息 "+(bubble.index+1); color: UiTheme.muted; font.pixelSize: 11 }
                        ToolButton {
                            id: editButton
                            objectName: chat.controlPrefix+"Edit"+bubble.index
                            visible: chat.editable; enabled: chat.editingIndex<0
                            text: "编辑"; font.pixelSize: 12; implicitHeight: 24
                            Accessible.name: "编辑消息"+(bubble.index+1)
                            onClicked: chat.beginEdit(bubble.index)
                        }
                        ToolButton {
                            id: deleteButton
                            objectName: chat.controlPrefix+"Delete"+bubble.index
                            visible: chat.editable; enabled: chat.editingIndex<0
                            text: "删除"; font.pixelSize: 12; implicitHeight: 24
                            Accessible.name: "删除消息"+(bubble.index+1)
                            ToolTip.visible: hovered
                            ToolTip.text: chat.defaultTemplate ? "删除这条消息及对应的个人改动" : "删除这条消息"
                            onClicked: chat.removeMessage(bubble.index)
                        }
                        ToolButton {
                            id: orderButton
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
                        Layout.preferredWidth: bubble.hugContent ? bubble.hugWidth : bubbleColumn.width
                        implicitHeight: body.implicitHeight+2*chat.bubblePadding
                        color: UiTheme.selection; radius: 12
                        TapHandler { enabled: chat.editable && chat.editingIndex!==bubble.index; onDoubleTapped: chat.beginEdit(bubble.index) }
                        ColumnLayout {
                            id: body; anchors.fill: parent; anchors.margins: chat.bubblePadding; spacing: 6
                            Label {
                                id: messageText
                                objectName: chat.controlPrefix+"Bubble"+bubble.index
                                visible: chat.editingIndex!==bubble.index
                                Layout.fillWidth: true; wrapMode: bubble.hugContent ? Text.NoWrap : Text.Wrap; textFormat: Text.PlainText
                                text: bubble.bubbleText
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
                                function activateEditor() {
                                    if(chat.editingIndex!==bubble.index) return
                                    chat.activeEditor=inlineText; chat.activeEditViewport=inlineScroll
                                    var owner=chat, control=inlineText, index=bubble.index
                                    Qt.callLater(function() { if(owner && control && owner.visible && owner.editingIndex===index) control.forceActiveFocus() })
                                }
                                onVisibleChanged: if(visible) activateEditor()
                                Component.onCompleted: if(visible) activateEditor()
                            TextArea {
                                id: inlineText; objectName: chat.controlPrefix+"Inline"+bubble.index
                                width: inlineScroll.availableWidth; readOnly: !chat.editable
                                text: chat.editingIndex===bubble.index ? chat.editText : ""
                                wrapMode: TextEdit.Wrap; selectByMouse: true; color: UiTheme.ink; font.pixelSize: 14
                                placeholderText: bubble.mixed ? "填写消息后将统一此条内容" : "编辑消息"
                                background: Rectangle { color: UiTheme.input; border.color: inlineText.activeFocus ? UiTheme.focus : UiTheme.line; radius: 6 }
                                onTextChanged: if(chat.editingIndex===bubble.index) chat.editText=text
                                onActiveFocusChanged: if(!activeFocus && chat.editingIndex===bubble.index) {
                                    var owner=chat, control=inlineText, index=bubble.index
                                    Qt.callLater(function() { if(owner && control && owner.editingIndex===index && !control.activeFocus) owner.finishOutsideEdit(false) })
                                }
                                onInputMethodComposingChanged: if(!inputMethodComposing && chat.editingIndex===bubble.index && (!activeFocus || chat.pendingOutsideCommit)) {
                                    var owner=chat, index=bubble.index
                                    Qt.callLater(function() { if(owner && owner.editingIndex===index) owner.finishOutsideEdit(false) })
                                }
                                Keys.onPressed: function(event) {
                                    if((event.key===Qt.Key_Return || event.key===Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                        if(!inputMethodComposing && !event.isAutoRepeat) chat.finishEdit(true)
                                        event.accepted=true
                                    }
                                    if(event.key===Qt.Key_Escape) { chat.cancelEdit(); event.accepted=true }
                                    if(event.key===Qt.Key_Tab || event.key===Qt.Key_Backtab) event.accepted=!chat.finishEdit(true)
                                }
                            }
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
            id: composerBox; objectName: chat.controlPrefix+"ComposerBox"
            visible: chat.editable && chat.editingIndex<0; Layout.fillWidth: true
            implicitHeight: composerColumn.implicitHeight+16
            color: fileDrop.containsDrag ? UiTheme.selection : UiTheme.input; radius: 10; border.color: fileDrop.containsDrag || composer.activeFocus ? UiTheme.focus : UiTheme.line
            DropArea {
                id: fileDrop; objectName: chat.controlPrefix+"FileDrop"; anchors.fill: parent; z: 2
                enabled: chat.editable && chat.editingIndex<0
                onEntered: function(drag) { drag.accepted=drag.hasUrls }
                onDropped: function(drop) { if(drop.hasUrls) { chat.dropFiles(drop.urls); drop.accept(Qt.CopyAction) } }
            }
            ColumnLayout {
                id: composerColumn; anchors.fill: parent; anchors.margins: 8; spacing: 4
                ScrollView {
                    id: inputScroll; Layout.fillWidth: true; Layout.preferredHeight: chat.height<200 ? 32 : chat.compact ? 50 : 76
                    contentWidth: availableWidth; clip: true
                    TextArea {
                        id: composer; objectName: chat.controlPrefix+"Composer"; width: inputScroll.availableWidth
                        enabled: chat.editingIndex<0; placeholderText: chat.defaultTemplate ? "写一条消息，可用 {姓名} 等变量…" : "写一条仅发给此人的消息…"
                        wrapMode: TextEdit.Wrap; selectByMouse: true; font.pixelSize: 14; color: UiTheme.ink
                        background: null; Accessible.name: "待加入的消息"
                        onTextChanged: chat.feedback=""
                        Keys.onPressed: function(event) {
                            if(event.matches(StandardKey.Paste) && chat.pasteFiles()) { event.accepted=true; return }
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
