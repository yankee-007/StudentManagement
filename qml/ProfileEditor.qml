import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: editor
    property var fields: []
    property var saveTarget
    property bool deferTextSave: false
    property bool compact: false
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    function advance(index) {
        var next = fieldRows.itemAt(index + 1)
        if (next) {
            next.focusEditor()
            var bottom = next.y + next.height
            if (bottom > contentItem.contentY + availableHeight)
                contentItem.contentY = bottom - availableHeight + 8
        } else editor.forceActiveFocus()
    }
    ColumnLayout {
        width: editor.availableWidth - (editor.compact ? 4 : 10)
        spacing: editor.compact ? 5 : 8
        Repeater {
            id: fieldRows
            model: editor.fields
            AutoProfileField {
                required property var modelData
                required property int index
                saveTarget: editor.saveTarget
                deferTextSave: editor.deferTextSave
                compact: editor.compact
                studentId: modelData.studentId
                recordKey: modelData.recordKey
                caption: modelData.label
                displayCaption: modelData.displayLabel
                initialValue: modelData.value
                options: modelData.options
                editable: modelData.editable
                fieldKind: modelData.kind
                expired: modelData.expired
                onAdvance: editor.advance(index)
            }
        }
    }
}
