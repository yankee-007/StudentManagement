import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property bool loading: false
    property var fileChooser: backend.groupCenter
    property var activeTextEditor: null
    readonly property int count: fields.count
    function insertVariable(name) {
        var area = activeTextEditor
        if (!area) {
            for (var i = 0; i < fields.count; i++) {
                if (fields.get(i).kind === "text") { area = fieldRepeater.itemAt(i).textEditor; break }
            }
        }
        if (!area) {
            fields.append({kind:"text",value:""})
            Qt.callLater(function() { editor.insertVariable(name) })
            return
        }
        area.forceActiveFocus()
        var position = area.selectionStart
        if (area.selectionEnd > position) area.remove(position, area.selectionEnd)
        area.insert(position, "{" + name + "}")
        area.cursorPosition = position + name.length + 2
    }
    function load(items) {
        loading=true
        fields.clear()
        for(var i=0;i<items.length;i++) fields.append({kind:items[i].type,value:items[i].type==="file" ? items[i].path : items[i].text})
        loading=false
    }
    function values() {
        var result=[]
        for(var i=0;i<fields.count;i++) {
            var f=fields.get(i)
            result.push(f.kind==="file" ? {type:"file",path:f.value} : {type:"text",text:f.value})
        }
        return result
    }
    ListModel { id: fields }
    Repeater {
        id: fieldRepeater
        model: fields
        UiPanel {
            id: fieldRow
            required property int index
            required property string kind
            required property string value
            property alias textEditor: textArea
            Layout.fillWidth: true
            padding: 12
            background: Rectangle { color: UiTheme.stripe; border.color: UiTheme.line; radius: 8 }
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Label { text: "消息 " + (fieldRow.index+1) + (fieldRow.kind==="file" ? " · 附件" : " · 文字"); color: UiTheme.ink; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    UiButton { text: "↑"; Accessible.name: "上移消息"; enabled: fieldRow.index>0; onClicked: fields.move(fieldRow.index,fieldRow.index-1,1) }
                    UiButton { text: "↓"; Accessible.name: "下移消息"; enabled: fieldRow.index<fields.count-1; onClicked: fields.move(fieldRow.index,fieldRow.index+1,1) }
                    UiButton { text: "移除"; onClicked: fields.remove(fieldRow.index) }
                }
                TextArea {
                    id: textArea
                    visible: fieldRow.kind==="text"; Layout.fillWidth: true; implicitHeight: Math.max(96, contentHeight + 20)
                    color: UiTheme.ink; font.pixelSize: 13; padding: 10
                    Accessible.name: "消息 " + (fieldRow.index + 1) + " 文字"
                    background: Rectangle { color: UiTheme.input; radius: 5; border.color: textArea.activeFocus ? UiTheme.focus : UiTheme.line }
                    text: fieldRow.value; wrapMode: TextEdit.Wrap; selectByMouse: true
                    onActiveFocusChanged: if (activeFocus) editor.activeTextEditor = textArea
                    Component.onDestruction: if (editor.activeTextEditor === textArea) editor.activeTextEditor = null
                    placeholderText: "填写这条消息，可换行"
                    onTextChanged: { if(activeFocus && !editor.loading && !inputMethodComposing) fields.setProperty(fieldRow.index,"value",text) }
                    onInputMethodComposingChanged: { if(activeFocus && !editor.loading && !inputMethodComposing) fields.setProperty(fieldRow.index,"value",text) }
                }
                RowLayout {
                    visible: fieldRow.kind==="file"; Layout.fillWidth: true
                    UiTextField { text: fieldRow.value; readOnly: true; placeholderText: "选择图片、压缩包或其他文件"; Layout.fillWidth: true }
                    UiButton { text: "选择文件"; onClicked: { var path=editor.fileChooser.chooseMessageFile(); if(path) fields.setProperty(fieldRow.index,"value",path) } }
                }
            }
        }
    }
    RowLayout {
        UiButton { text: "＋ 添加文字"; onClicked: fields.append({kind:"text",value:""}) }
        UiButton { text: "＋ 添加附件"; onClicked: fields.append({kind:"file",value:""}) }
    }
}
