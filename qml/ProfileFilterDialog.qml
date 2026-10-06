import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: popup
    property string filterObjectName: "profileColumnFilter"
    objectName: filterObjectName
    required property var profiles
    property var info: ({options:[],values:[]})
    property var selectedValues: []
    anchors.centerIn: parent; modal: true
    width: Math.min(parent.width-20,390); height: Math.min(parent.height-20,550)
    title: "筛选 · " + (info.label || "")
    function openFor(index) {
        info=profiles.columnFilterInfo(index)
        selectedValues=info.values.slice()
        optionSearch.text=""
        tabs.currentIndex=info.mode === "values" ? 0 : 1
        condition.currentIndex=Math.max(0,["contains","exact","empty","notempty"].indexOf(info.mode))
        conditionValue.text=info.value || ""
        open()
    }
    function visibleOptions() {
        var tokens=optionSearch.text.trim().toLowerCase().split(/\s+/).filter(function(s) { return s.length>0 })
        return info.options.filter(function(o) { return tokens.length===0 || tokens.some(function(t) { return o.label.toLowerCase().indexOf(t)>=0 }) })
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            UiButton { text: "↑ 升序"; Layout.fillWidth: true; onClicked: { profiles.sortField(popup.info.key,false); popup.close() } }
            UiButton { text: "↓ 降序"; Layout.fillWidth: true; onClicked: { profiles.sortField(popup.info.key,true); popup.close() } }
        }
        TabBar { id: tabs; Layout.fillWidth: true; TabButton { text: "按选项" } TabButton { text: "按条件" } }
        UiTextField { id: optionSearch; visible: tabs.currentIndex===0; Layout.fillWidth: true; placeholderText: "搜索选项，空格分隔多个关键词" }
        CheckBox {
            visible: tabs.currentIndex===0; text: "全部搜索结果（" + popup.visibleOptions().length + " 项）"
            checked: popup.visibleOptions().length>0 && popup.visibleOptions().every(function(o) { return popup.selectedValues.indexOf(o.value)>=0 })
            onToggled: {
                var values=popup.selectedValues.slice()
                popup.visibleOptions().forEach(function(o) {
                    var i=values.indexOf(o.value)
                    if(checked && i<0) values.push(o.value)
                    if(!checked && i>=0) values.splice(i,1)
                })
                popup.selectedValues=values
            }
        }
        ListView {
            visible: tabs.currentIndex===0; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            model: popup.visibleOptions(); ScrollBar.vertical: ScrollBar {}
            delegate: CheckBox {
                required property var modelData
                width: ListView.view.width
                text: modelData.label + "（" + modelData.count + "）"
                checked: popup.selectedValues.indexOf(modelData.value)>=0
                onToggled: {
                    var values=popup.selectedValues.slice(); var i=values.indexOf(modelData.value)
                    if(checked && i<0) values.push(modelData.value)
                    if(!checked && i>=0) values.splice(i,1)
                    popup.selectedValues=values
                }
            }
        }
        ColumnLayout {
            visible: tabs.currentIndex===1; Layout.fillWidth: true; Layout.fillHeight: true
            UiComboBox { id: condition; model: ["包含","等于","为空","不为空"]; Layout.fillWidth: true }
            UiTextField { id: conditionValue; visible: condition.currentIndex<2; placeholderText: "条件内容"; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
        }
        RowLayout {
            UiButton { text: "确定"; highlighted: true; onClicked: {
                profiles.setColumnFilter(popup.info.key,tabs.currentIndex===0 ? "values" : ["contains","exact","empty","notempty"][condition.currentIndex],popup.selectedValues,conditionValue.text)
                popup.close()
            } }
            UiButton { text: "重置"; onClicked: { profiles.setColumnFilter(popup.info.key,"clear",[],""); popup.close() } }
            UiButton { text: "取消"; onClicked: popup.close() }
        }
    }
}
