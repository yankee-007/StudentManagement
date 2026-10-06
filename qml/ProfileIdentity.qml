import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: identity
    property var student: ({})
    property bool showName: true
    property bool compact: false
    property var managedFields: backend.profilesModule.managedFields
    function shown(key) {
        return managedFields.some(function(f) { return f.field_id === 'column:' + key && f.show_column })
    }
    Layout.fillWidth: true
    spacing: 4
    Label { visible: identity.showName; text: identity.student.name || "请选择学员"; font.pixelSize: identity.compact ? 16 : 20; font.bold: true; color: UiTheme.ink }
    Label {
        text: (identity.shown('class_name') && identity.student.class_name ? identity.student.class_name + " · " : "") + (identity.student.student_id || "")
        color: UiTheme.muted; font.pixelSize: identity.compact ? 10 : 12; Layout.fillWidth: true; elide: Text.ElideRight
    }
    Label { visible: identity.shown('roster_status') && !!identity.student.student_id; text: "状态：" + (identity.student.roster_status || ""); color: UiTheme.muted; font.pixelSize: identity.compact ? 10 : 12 }
}
