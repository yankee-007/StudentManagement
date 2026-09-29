import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property var service: backend.termsModule
    property string selectedId: ""
    spacing: 10
    RowLayout {
        Layout.fillWidth: true
        Label { text: "班期学员"; font.pixelSize: 22; font.bold: true; color: "#17213a" }
        Label { text: "账号班期 · 完整名单 · 自动补位"; color: "#667085"; Layout.fillWidth: true }
        Button { text: "重新获取课程和学员"; enabled: !service.busy && !backend.busy; onClicked: service.refreshAll() }
    }
    Frame {
        Layout.fillWidth: true; padding: 12
        background: Rectangle { color: "white"; radius: 8; border.color: "#e4e7ec" }
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Label { text: "班期"; color: "#475467" }
                ComboBox {
                    model: service.terms; textRole: "label"; currentIndex: service.termIndex
                    Layout.preferredWidth: 250; enabled: !service.busy && !backend.busy
                    displayText: currentIndex < 0 ? "正在初始化班期" : currentText
                    onActivated: { panel.selectedId = ""; service.selectTerm(currentIndex) }
                }
                Item { Layout.fillWidth: true }
                Button { text: "导出当前显示 XLSX"; enabled: service.visibleCount > 0; onClicked: service.exportRoster() }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "课程"; color: "#475467" }
                ComboBox {
                    id: lessonBox; objectName: "termLessonBox"
                    popup.objectName: "termLessonPopup"
                    Layout.fillWidth: true; model: service.lessons; textRole: "label"; currentIndex: service.lessonIndex
                    displayText: currentIndex < 0 ? "展开查看课程列表" : currentText
                    enabled: service.lessons.length > 0 && !service.busy && !backend.busy
                    onActivated: service.selectLesson(currentIndex)
                    delegate: ItemDelegate {
                        required property var modelData
                        width: parent ? parent.width : 300; text: modelData.label
                        hoverEnabled: true; highlighted: hovered
                    }
                }
                Button { text: "取消"; visible: service.busy; onClicked: service.cancel() }
            }
            Label { text: "课程列表仅供查看；获取学员始终使用第 1 节课，与这里的选择无关。"; color: "#667085"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: service.notice; wrapMode: Text.Wrap; Layout.fillWidth: true; color: service.busy ? "#335cff" : "#667085"; font.pixelSize: 12 }
            ProgressBar { visible: service.busy; indeterminate: true; Layout.fillWidth: true }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: service.summary; color: "#344054"; Layout.fillWidth: true }
        TextField { Layout.preferredWidth: 280; placeholderText: "搜索学号、姓名、状态、类型、昵称"; onTextEdited: service.filterRows(text) }
    }
    Frame {
        Layout.fillWidth: true; Layout.fillHeight: true; padding: 1
        background: Rectangle { color: "white"; radius: 8; border.color: "#e4e7ec" }
        Item {
            anchors.fill: parent
            HorizontalHeaderView {
                id: headings; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                height: 32; syncView: roster
                delegate: Rectangle {
                    required property var display
                    implicitWidth: 100; implicitHeight: 32; color: "#f2f4f7"
                    Text { anchors.fill: parent; anchors.leftMargin: 10; text: display; verticalAlignment: Text.AlignVCenter; font.pixelSize: 11; color: "#344054" }
                }
            }
            TableView {
                id: roster; objectName: "termRosterTable"; model: service.tableModel
                anchors.top: headings.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                columnWidthProvider: function(c) { return c === 0 ? 60 : c === 1 ? 180 : c === 2 ? 120 : c === 3 ? 100 : c === 4 ? 80 : Math.max(180, width-545) }
                rowHeightProvider: function() { return 20 }
                ScrollBar.vertical: ScrollBar {}
                ScrollBar.horizontal: ScrollBar {}
                delegate: Rectangle {
                    required property int row
                    required property int column
                    required property string display
                    required property string studentId
                    implicitHeight: 20; implicitWidth: 100
                    color: studentId === panel.selectedId ? "#dce6ff" : row % 2 ? "#f8faff" : "white"
                    Text { anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6; text: display; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: "#344054" }
                    TapHandler { onTapped: panel.selectedId = studentId }
                }
            }
            Label { anchors.centerIn: parent; visible: service.visibleCount === 0; text: "暂无名单，或没有符合搜索条件的学员"; color: "#98a2b3" }
        }
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#667085"; font.pixelSize: 11
        text: "按学号序号排列，补位沿用前一字母（开头默认 A），状态为已退课，其他信息留空。班期身份同步到画像和当前催办，历史批次不变。"
    }
}
