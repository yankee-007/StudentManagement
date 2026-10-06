import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property bool loading: false
    property var fileChooser: backend.groupCenter
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
        model: fields
        UiPanel {
            id: fieldRow
            required property int index
            required property string kind
            required property string value
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Label { text: "字段 " + (fieldRow.index+1) + (fieldRow.kind==="file" ? " · 文件" : " · 文字"); Layout.fillWidth: true }
                    UiButton { text: "↑"; enabled: fieldRow.index>0; onClicked: fields.move(fieldRow.index,fieldRow.index-1,1) }
                    UiButton { text: "↓"; enabled: fieldRow.index<fields.count-1; onClicked: fields.move(fieldRow.index,fieldRow.index+1,1) }
                    UiButton { text: "移除"; onClicked: fields.remove(fieldRow.index) }
                }
                TextArea {
                    visible: fieldRow.kind==="text"; Layout.fillWidth: true; implicitHeight: 80
                    text: fieldRow.value; wrapMode: TextEdit.Wrap; selectByMouse: true
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
        UiButton { text: "＋文字字段"; onClicked: fields.append({kind:"text",value:""}) }
        UiButton { text: "＋文件字段"; onClicked: fields.append({kind:"file",value:""}) }
    }
}
