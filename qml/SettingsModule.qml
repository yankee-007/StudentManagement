import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var settings: backend.settingsModule
    property var selectedTerm: termBox.currentIndex >= 0 && termBox.currentIndex < page.settings.termClasses.length ? page.settings.termClasses[termBox.currentIndex] : ({})
    property var selectedClass: classBox.currentIndex >= 0 && classBox.currentIndex < page.settings.homeworkClasses.length ? page.settings.homeworkClasses[classBox.currentIndex] : ({})
    ColumnLayout {
        anchors.fill: parent; spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Label { text: "平台账号设置"; font.pixelSize: 21; font.bold: true; color: "#17213a" }
            Item { Layout.fillWidth: true }
            Button { text: "刷新状态"; onClicked: page.settings.refresh() }
        }
        Label { text: page.settings.notice; color: "#667085"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
        AccountSettingsCard { platform: "completion"; title: "追光鲸鱼 · 完课平台" }
        AccountSettingsCard { platform: "homework"; title: "作业平台" }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: bindingColumn.implicitHeight + 28
            color: "#ffffff"; radius: 10; border.color: "#e1e6ef"
            ColumnLayout {
                id: bindingColumn; anchors.fill: parent; anchors.margins: 14; spacing: 9
                Label { text: "班期对应关系"; font.pixelSize: 16; font.bold: true; color: "#17213a" }
                Label { text: "两个平台的班期 ID 不同。每个班期确认一次；未绑定的班期不会新建催办。"; font.pixelSize: 12; color: "#667085"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true
                    ComboBox { id: termBox; Layout.preferredWidth: 190; model: page.settings.termClasses; textRole: "name" }
                    ComboBox { id: classBox; Layout.preferredWidth: 190; model: page.settings.homeworkClasses; textRole: "name"; onCurrentIndexChanged: courseBox.currentIndex = 0 }
                    ComboBox { id: courseBox; Layout.preferredWidth: 100; model: page.selectedClass.course_ids || [] }
                    Button { text: page.settings.busy ? "获取中…" : "获取作业班级"; enabled: !page.settings.busy; onClicked: page.settings.fetchHomeworkClasses() }
                    Button { text: "确认绑定"; enabled: !page.settings.busy && courseBox.currentIndex >= 0; onClicked: page.settings.saveBinding(String(page.selectedTerm.termId || ""), Number(page.selectedClass.id), Number(courseBox.currentText)) }
                }
                Label {
                    text: {
                        page.settings.notice
                        var b = page.settings.bindingFor(String(page.selectedTerm.termId || ""))
                        return b.class_id ? "当前已绑定：" + b.class_name + " · 班级 ID " + b.class_id + " · 课程 ID " + b.course_id : "当前班期尚未绑定"
                    }
                    font.pixelSize: 12; color: "#475467"
                }
            }
        }
        Label {
            text: "此页输入的密码由 Windows 凭据管理器保管。更换账号时请同时输入该账号的密码。"
            color: "#667085"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
        }
        Item { Layout.fillHeight: true }
    }
}
