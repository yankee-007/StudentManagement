import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: row
    required property string termId
    required property string termName
    required property var settings
    required property var scrollView
    property var savedBinding: ({})
    property string saveError: ""
    readonly property bool sideBySide: width >= 650
    readonly property var classChoices: {
        var entries = [{id: 0, name: "未绑定（留空）", course_ids: []}]
        var classes = settings.homeworkClasses
        var found = false
        for (var i = 0; i < classes.length; i++) {
            entries.push(classes[i])
            if (Number(classes[i].id) === Number(savedBinding.class_id)) found = true
        }
        // 目录暂缺时仍展示持久化的名称，不把已有绑定伪装成空值。
        if (savedBinding.class_id && !found) {
            entries.push({id: savedBinding.class_id, name: savedBinding.class_name + "（已保存，目录暂缺）",
                          course_ids: [savedBinding.course_id], cachedOnly: true})
        }
        return entries
    }
    readonly property var selectedClass: classChoices[classBox.currentIndex] || ({})
    implicitHeight: body.implicitHeight + 20
    objectName: "bindingRow_" + termId

    function syncBinding() {
        savedBinding = settings.bindingFor(termId)
        restoreSelection()
    }

    function restoreSelection() {
        var selected = 0
        for (var i = 0; i < classChoices.length; i++) {
            if (Number(classChoices[i].id) === Number(savedBinding.class_id || 0)) { selected = i; break }
        }
        classBox.currentIndex = selected
        var courses = selectedClass.course_ids || []
        var courseIndex = courses.indexOf(Number(savedBinding.course_id))
        courseBox.currentIndex = courseIndex >= 0 ? courseIndex : 0
    }

    function saveSelection(courseId) {
        var ok = settings.saveBinding(termId, Number(selectedClass.id || 0), courseId)
        saveError = ok ? "" : settings.notice
        if (!ok) restoreSelection()
    }

    Rectangle { anchors.fill: parent; radius: 6; color: UiTheme.stripe; border.color: UiTheme.line }
    GridLayout {
        id: body
        x: 10; y: 10; width: Math.max(0, row.width - 20)
        columns: row.sideBySide ? 2 : 1
        columnSpacing: 20; rowSpacing: 10
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0
            Layout.preferredWidth: row.sideBySide ? body.width * 0.4 : -1
            Layout.alignment: Qt.AlignTop
            spacing: 4
            Label { text: "完课平台班期"; color: UiTheme.muted; font.pixelSize: 12 }
            Label {
                objectName: "bindingTermName_" + row.termId
                text: row.termName; color: UiTheme.ink; font.pixelSize: 13; font.bold: true
                wrapMode: Text.Wrap; Layout.fillWidth: true
            }
            Label {
                objectName: "bindingStatus_" + row.termId
                text: row.savedBinding.class_id ? "已绑定 · 已保存" : "未绑定（可留空）"
                color: row.savedBinding.class_id ? UiTheme.success : UiTheme.muted
                font.pixelSize: 12
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0
            Layout.preferredWidth: row.sideBySide ? body.width * 0.6 : -1
            spacing: 4
            Label { text: "作业平台班级"; color: UiTheme.muted; font.pixelSize: 12 }
            UiComboBox {
                id: classBox
                objectName: "settingClassBox_" + row.termId
                Layout.fillWidth: true; Layout.minimumWidth: 0
                model: row.classChoices; textRole: "name"
                enabled: !row.settings.busy && !backend.busy && !backend.termsModule.busy
                Accessible.name: row.termName + "对应的作业平台班级，可留空"
                onActivated: {
                    if (Number(row.selectedClass.id || 0) === Number(row.savedBinding.class_id || 0)) {
                        row.saveError = ""
                        row.restoreSelection()
                    } else {
                        courseBox.currentIndex = 0
                        row.saveSelection(0)
                    }
                }
                SettingsWheelGuard { view: row.scrollView }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: (row.selectedClass.course_ids || []).length > 1
                Label { text: "课程"; color: UiTheme.muted; font.pixelSize: 12 }
                UiComboBox {
                    id: courseBox
                    objectName: "settingCourseBox_" + row.termId
                    Layout.fillWidth: true
                    model: row.selectedClass.course_ids || []
                    enabled: classBox.enabled
                    Accessible.name: row.termName + "对应的作业课程"
                    onActivated: row.saveSelection(Number(currentText))
                    SettingsWheelGuard { view: row.scrollView }
                }
            }
            Label {
                visible: !!row.selectedClass.cachedOnly
                text: "已保留原绑定。需要更换时请先获取作业班级，也可选择留空。"
                color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
            }
            Label {
                objectName: "bindingError_" + row.termId
                visible: row.saveError.length > 0
                text: row.saveError; color: UiTheme.danger; font.pixelSize: 12
                wrapMode: Text.Wrap; Layout.fillWidth: true
            }
        }
    }

    Component.onCompleted: syncBinding()
    Connections {
        target: row.settings
        function onBindingsChanged() { row.syncBinding() }
        function onHomeworkClassesChanged() { row.syncBinding() }
    }
}
