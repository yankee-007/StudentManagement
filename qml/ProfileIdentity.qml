import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: identity
    property var student: ({})
    property var managedFields: backend.profilesModule.managedFields
    function shown(key) {
        return managedFields.some(function(f) { return f.field_id === 'column:' + key && f.show_column })
    }
    Layout.fillWidth: true
    spacing: 4
    Label { text: identity.student.name || "请选择学员"; font.pixelSize: 20; font.bold: true; color: "#17213a" }
    Label {
        text: (identity.shown('class_name') && identity.student.class_name ? identity.student.class_name + " · " : "") + (identity.student.student_id || "")
        color: "#667085"; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight
    }
    Label { visible: identity.shown('roster_status') && !!identity.student.student_id; text: "状态：" + (identity.student.roster_status || ""); color: "#667085"; font.pixelSize: 12 }
}
