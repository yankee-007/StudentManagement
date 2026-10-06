import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: field
    property string studentId
    property var saveTarget: backend
    property bool deferTextSave: false
    property bool compact: false
    property string caption
    property string displayCaption: caption
    property var options: []
    property string initialValue
    property bool editable: true
    property bool ready: false
    property string ownerId: studentId
    property string recordKey: ""
    property bool loading: false
    property string fieldKind: "text"
    property bool expired: false
    signal advance()
    function focusEditor() {
        if (!editable) return
        if (choice.visible) choice.forceActiveFocus()
        else if (input.visible) { input.forceActiveFocus(); input.selectAll() }
        else dateButton.forceActiveFocus()
    }
    function saveValue(value) {
        if (!ready || loading || !editable || !ownerId) return false
        return recordKey ? saveTarget.saveEditorField(recordKey, caption, value)
                         : saveTarget.autoSaveField(ownerId, caption, value)
    }
    function loadValue() {
        if (!ready) return
        loading = true
        if (input.activeFocus && input.inputMethodComposing) Qt.inputMethod.reset()
        input.text = initialValue
        choice.savedValue = initialValue
        choice.currentIndex = options.indexOf(initialValue)
        loading = false
    }
    onInitialValueChanged: loadValue()
    Layout.fillWidth: true
    spacing: field.compact ? 5 : 10
    Label { text: field.displayCaption.replace(/\n/g, " "); Layout.preferredWidth: field.compact ? 56 : 76; elide: Text.ElideRight; font.pixelSize: field.compact ? 11 : 12; color: UiTheme.muted; ToolTip.visible: labelHover.hovered; ToolTip.text: field.displayCaption; HoverHandler { id: labelHover } }
    UiComboBox {
        id: choice
        objectName: "profileChoice"
        visible: field.options.length > 0
        enabled: field.editable
        Layout.fillWidth: true
        implicitHeight: field.compact ? 27 : 32
        font.pixelSize: field.compact ? 11 : 13
        leftPadding: field.compact ? 5 : 10
        wheelEnabled: false
        model: field.options
        property string savedValue: field.initialValue
        currentIndex: field.options.indexOf(savedValue)
        displayText: currentIndex < 0 ? "原值：" + savedValue : (currentText || "未填写")
        background: Rectangle { radius: 6; color: choice.down ? "#eef2ff" : "#f9fafb"; border.color: choice.activeFocus ? "#809aff" : UiTheme.line }
        delegate: ItemDelegate {
            id: option
            required property string modelData
            required property int index
            width: choice.width; text: modelData || "未填写（清空）"
            implicitHeight: field.compact ? 29 : 34
            hoverEnabled: true
            highlighted: hovered
            leftPadding: 10
            rightPadding: 10
            contentItem: Text {
                text: option.text
                font.pixelSize: field.compact ? 11 : 13
                color: option.hovered ? UiTheme.accent : UiTheme.ink
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                anchors.fill: parent
                anchors.margins: 2
                radius: 5
                color: option.hovered ? "#eef2ff" : "transparent"
            }
        }
        onActivated: {
            var picked = currentText
            if (field.deferTextSave) {
                if (field.saveTarget.queueEditorField(field.recordKey, field.caption, picked)) savedValue = picked
            } else if (field.saveValue(picked)) savedValue = picked
            currentIndex = field.options.indexOf(savedValue)
        }
    }
    UiTextField {
        id: input
        objectName: "profileInput"
        visible: field.options.length === 0 && field.fieldKind !== "date" && field.fieldKind !== "exemption"
        Layout.fillWidth: true
        text: ""
        readOnly: !field.editable
        placeholderText: field.editable ? "未填写" : "无记录"
        font.pixelSize: field.compact ? 11 : 13
        implicitHeight: field.compact ? 27 : 32
        padding: field.compact ? 5 : 7
        selectByMouse: true
        background: Rectangle { radius: 6; color: field.editable ? "#f9fafb" : UiTheme.stripe; border.color: input.activeFocus ? "#809aff" : UiTheme.line }
        function persist() {
            if (field.ready && !field.loading && field.editable && activeFocus && !inputMethodComposing)
                field.deferTextSave ? field.saveTarget.queueEditorField(field.recordKey, field.caption, text)
                                    : field.saveValue(text)
        }
        onTextChanged: persist()
        onInputMethodComposingChanged: persist()
        onAccepted: { if (field.saveValue(text)) field.advance() }
    }
    RowLayout {
        visible: field.fieldKind === "date" || field.fieldKind === "exemption"
        Layout.fillWidth: true
        UiButton {
            id: dateButton
            Layout.fillWidth: true; enabled: field.editable
            font.pixelSize: field.compact ? 10 : 12
            text: (field.initialValue || "选择日期") + (field.expired ? " · 已到期" : "")
            palette.buttonText: field.expired ? "#98a2b3" : UiTheme.ink
            onClicked: {
                var capturedKey = field.recordKey
                var value = field.fieldKind === "exemption" ? backend.chooseDate(field.initialValue) : backend.chooseProfileDate(field.initialValue)
                if (capturedKey === field.recordKey && value !== field.initialValue) field.saveValue(value)
            }
        }
        UiButton { text: "清除"; enabled: field.editable && field.initialValue.length > 0; font.pixelSize: field.compact ? 10 : 12; onClicked: field.saveValue("") }
    }
    Component.onCompleted: { ready = true; loadValue() }
}
