import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "campaignExportDialog"
    required property var workflow
    anchors.centerIn: parent; modal: true
    title: "导出全班 XLSX · 选择字段"
    width: Math.min(parent.width - 30, 480); height: Math.min(parent.height - 30, 580)
    property var orderedFields: []
    property var selectedKeys: []
    property bool loading: false
    property string batchContext: ""
    property int dropIndex: -1
    property string draggingKey: ""
    function resetSelection(all) {
        selectedKeys = orderedFields.filter(function(f) { return all || f.selected }).map(function(f) { return f.key })
    }
    function defaultFields() {
        var defaults = ["student_id","name","courses","homework","missing_total","completed_courses","completed_homework","feedback","roster_status","wechat","exemption_text"]
        var fields = workflow.exportFields.slice()
        fields.sort(function(a,b) {
            var ai = defaults.indexOf(a.key), bi = defaults.indexOf(b.key)
            return (ai < 0 ? defaults.length : ai) - (bi < 0 ? defaults.length : bi)
        })
        orderedFields = fields
        selectedKeys = fields.filter(function(f) { return defaults.indexOf(f.key) >= 0 }).map(function(f) { return f.key })
    }
    function moveField(key,target) {
        var fields = orderedFields.slice()
        var source = fields.findIndex(function(f) { return f.key === key })
        if (source < 0 || target < 0 || target >= fields.length || source === target) return
        fields.splice(target,0,fields.splice(source,1)[0])
        orderedFields = fields
    }
    function persist() {
        if (!visible || loading || orderedFields.length !== workflow.exportFields.length) return
        workflow.saveExportPreferences(orderedFields.map(function(f) { return f.key }),selectedKeys)
    }
    onOrderedFieldsChanged: persist()
    onSelectedKeysChanged: persist()
    onOpened: {
        loading = true
        batchContext = workflow.className + "|" + workflow.batchTitle
        orderedFields = workflow.exportFields.slice()
        resetSelection(false)
        loading = false
    }
    Connections {
        target: dialog.workflow
        function onChanged() {
            if (dialog.visible && dialog.batchContext !== dialog.workflow.className + "|" + dialog.workflow.batchTitle) dialog.close()
        }
    }
    ColumnLayout {
        anchors.fill: parent
        Label {
            text: "导出所选批次的全班快照，按学号升序，不受当前搜索、筛选影响。拖动手柄调整导出列顺序；字段选择与表格显示独立。"
            wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted
        }
        RowLayout {
            UiButton { text: "默认字段"; onClicked: dialog.defaultFields() }
            UiButton { text: "全选"; onClicked: dialog.resetSelection(true) }
            UiButton { text: "清空"; onClicked: dialog.selectedKeys = [] }
        }
        ListView {
            id: list; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            model: dialog.orderedFields; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                width: list.width; height: 42; radius: 5
                color: dialog.dropIndex === index ? "#e9efff" : index % 2 ? "#f9fafb" : "white"
                border.color: dialog.dropIndex === index ? "#809aff" : "transparent"
                RowLayout {
                    anchors.fill: parent; anchors.margins: 3
                    Label {
                        text: "⠿"; font.pixelSize: 22; color: UiTheme.muted; Layout.preferredWidth: 28
                        MouseArea {
                            anchors.fill: parent; cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                            preventStealing: true
                            onPressed: { dialog.draggingKey = row.modelData.key; dialog.dropIndex = row.index }
                            onPositionChanged: function(mouse) {
                                if (!pressed) return
                                var p = mapToItem(list.contentItem,mouse.x,mouse.y)
                                var viewportY = p.y - list.contentY
                                if (viewportY < 18) list.contentY = Math.max(0,list.contentY-12)
                                if (viewportY > list.height-18) list.contentY = Math.min(Math.max(0,list.contentHeight-list.height),list.contentY+12)
                                dialog.dropIndex = Math.max(0,Math.min(list.count-1,Math.floor(p.y/42)))
                            }
                            onReleased: {
                                var key = dialog.draggingKey, target = dialog.dropIndex
                                dialog.draggingKey = ""; dialog.dropIndex = -1
                                dialog.moveField(key,target)
                            }
                            onCanceled: { dialog.draggingKey=""; dialog.dropIndex=-1 }
                        }
                    }
                    CheckBox {
                        text: row.modelData.name; Layout.fillWidth: true
                        checked: dialog.selectedKeys.indexOf(row.modelData.key) >= 0
                        onToggled: {
                            var keys = dialog.selectedKeys.slice(), i = keys.indexOf(row.modelData.key)
                            if (checked && i < 0) keys.push(row.modelData.key)
                            if (!checked && i >= 0) keys.splice(i,1)
                            dialog.selectedKeys = keys
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            UiButton { text: "取消"; onClicked: dialog.close() }
            UiButton {
                text: "导出 XLSX"; enabled: dialog.selectedKeys.length > 0
                onClicked: {
                    var all = dialog.orderedFields.map(function(f) { return f.key })
                    var keys = all.filter(function(key) { return dialog.selectedKeys.indexOf(key) >= 0 })
                    dialog.workflow.exportBatch(keys)
                    dialog.close()
                }
            }
        }
    }
}
