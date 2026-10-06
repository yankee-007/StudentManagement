import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property var service: backend.termsModule
    property string selectedId: ""
    ClassSwitchOverlay { id: termSwitch }
    spacing: 10
    RowLayout {
        Layout.fillWidth: true
        Label { text: "班期学员"; font.pixelSize: 22; font.bold: true; color: UiTheme.ink }
        Label { text: "账号班期 · 完整名单 · 自动补位"; color: UiTheme.muted; Layout.fillWidth: true }
        UiButton { text: "重新获取课程和学员"; enabled: !service.busy && !backend.busy; onClicked: service.refreshAll() }
    }
    UiPanel {
        Layout.fillWidth: true; padding: 12
        background: Rectangle { color: "white"; radius: 8; border.color: UiTheme.line }
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Label { text: "班期"; color: UiTheme.muted }
                UiComboBox {
                    objectName: "termClassSelector"
                    popup.objectName: "termClassSelectorPopup"
                    model: service.terms; textRole: "label"; currentIndex: service.termIndex
                    Layout.preferredWidth: 250; enabled: !service.busy && !backend.busy
                    displayText: currentIndex < 0 ? "正在初始化班期" : currentText
                    onActivated: function(index) {
                        popup.close()
                        if (index === service.termIndex) return
                        var name = service.terms[index].label
                        var size = service.termRosterSize(index)
                        termSwitch.begin(name, function() {
                            panel.selectedId = ""
                            service.selectTerm(index)
                        }, size < 0 || size >= 300)
                    }
                }
                Item { Layout.fillWidth: true }
                UiButton { text: "导出当前显示 XLSX"; enabled: service.visibleCount > 0; onClicked: service.exportRoster() }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: "课程"; color: UiTheme.muted }
                UiComboBox {
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
                UiButton { text: "取消"; visible: service.busy; onClicked: service.cancel() }
            }
            Label { text: "课程列表仅供查看；获取学员始终使用第 1 节课，与这里的选择无关。"; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: service.notice; wrapMode: Text.Wrap; Layout.fillWidth: true; color: service.busy ? UiTheme.accent : UiTheme.muted; font.pixelSize: 12 }
            ProgressBar { visible: service.busy; indeterminate: true; Layout.fillWidth: true }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: service.summary; color: UiTheme.ink; Layout.fillWidth: true }
        UiTextField { Layout.preferredWidth: 280; placeholderText: "搜索学号、姓名、状态、类型、昵称"; onTextEdited: service.filterRows(text) }
    }
    UiPanel {
        Layout.fillWidth: true; Layout.fillHeight: true; padding: 1
        background: Rectangle { color: "white"; radius: 8; border.color: UiTheme.line }
        Item {
            anchors.fill: parent
            HorizontalHeaderView {
                id: headings; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                height: UiTheme.headerHeight; syncView: roster
                delegate: Rectangle {
                    required property var display
                    implicitWidth: 100; implicitHeight: UiTheme.headerHeight; color: UiTheme.stripe
                    Text { anchors.fill: parent; anchors.leftMargin: 10; text: display; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12; color: UiTheme.ink }
                }
            }
            TableView {
                id: roster; objectName: "termRosterTable"; model: service.tableModel
                anchors.top: headings.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                columnWidthProvider: function(c) { return c === 0 ? 60 : c === 1 ? 180 : c === 2 ? 120 : c === 3 ? 100 : c === 4 ? 80 : Math.max(180, width-545) }
                rowHeightProvider: function() { return UiTheme.rowHeight }
                ScrollBar.vertical: ScrollBar {}
                ScrollBar.horizontal: ScrollBar {}
                delegate: Rectangle {
                    required property int row
                    required property int column
                    required property string display
                    required property string studentId
                    implicitHeight: UiTheme.rowHeight; implicitWidth: 100
                    color: studentId === panel.selectedId ? UiTheme.selection : row % 2 ? UiTheme.stripe : "white"
                    Text { anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6; text: display; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: UiTheme.ink }
                    TapHandler { onTapped: panel.selectedId = studentId }
                }
            }
            Label { anchors.centerIn: parent; visible: service.visibleCount === 0; text: "暂无名单，或没有符合搜索条件的学员"; color: "#98a2b3" }
        }
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12
        text: "按学号序号排列，补位沿用前一字母（开头默认 A），状态为已退课，其他信息留空。班期身份同步到画像和当前催办，历史批次不变。"
    }
}
