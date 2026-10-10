import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "campaignFieldDialog"
    required property var workflow
    anchors.centerIn: parent; modal: true
    title: "管理工作台字段 · " + workflow.className
    width: Math.min(parent.width - 30, 500)
    height: Math.min(parent.height - 30, 470)
    standardButtons: Dialog.Close
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        Label {
            text: "仅影响当前班期。拖动手柄排序；勾选控制表格、详情和跟随聊天浮窗。姓名固定显示。"
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted
        }
        Label {
            text: "往期反馈按每次催办单独列出，可勾选指定记录并调整顺序；只加载所选记录。"
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted
        }
        UiButton {
            objectName: "campaignLocateHistory"; text: "定位往期反馈"
            visible: dialog.workflow.managedFields.some(function(f) { return f.field_id.indexOf("previous_feedback_")===0 })
            onClicked: {
                var history=dialog.workflow.managedFields.filter(function(f) { return f.field_id.indexOf("previous_feedback_")===0 })
                if(history.length) fieldOrder.positionField(history[0].field_id)
            }
        }
        ProfileFieldOrder { id: fieldOrder; Layout.fillWidth: true; Layout.fillHeight: true; profiles: dialog.workflow }
    }
}
