import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: field
    property string studentId
    property var saveTarget: backend
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
    spacing: 10
    Label { text: field.displayCaption.replace(/\n/g, " "); Layout.preferredWidth: 76; elide: Text.ElideRight; font.pixelSize: 12; color: "#667085"; ToolTip.visible: labelHover.hovered; ToolTip.text: field.displayCaption; HoverHandler { id: labelHover } }
    ComboBox {
        id: choice
        objectName: "profileChoice"
        visible: field.options.length > 0
        enabled: field.editable
        Layout.fillWidth: true
        implicitHeight: 32
        font.pixelSize: 13
        leftPadding: 10
        wheelEnabled: false
        model: field.options
        property string savedValue: field.initialValue
        currentIndex: field.options.indexOf(savedValue)
        displayText: currentIndex < 0 ? "原值：" + savedValue : (currentText || "未填写")
        background: Rectangle { radius: 6; color: choice.down ? "#eef2ff" : "#f9fafb"; border.color: choice.activeFocus ? "#809aff" : "#e4e7ec" }
        delegate: ItemDelegate {
            id: option
            required property string modelData
            required property int index
            width: choice.width; text: modelData || "未填写（清空）"
            implicitHeight: 34
            hoverEnabled: true
            highlighted: hovered
            leftPadding: 10
            rightPadding: 10
            contentItem: Text {
                text: option.text
                font.pixelSize: 13
                color: option.hovered ? "#335cff" : "#344054"
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
            if (field.saveValue(currentText)) savedValue = currentText
            currentIndex = field.options.indexOf(savedValue)
        }
    }
    TextField {
        id: input
        objectName: "profileInput"
        visible: field.options.length === 0 && field.fieldKind !== "date" && field.fieldKind !== "exemption"
        Layout.fillWidth: true
        text: ""
        readOnly: !field.editable
        placeholderText: field.editable ? "未填写" : "无记录"
        font.pixelSize: 13
        implicitHeight: 32
        padding: 7
        selectByMouse: true
        background: Rectangle { radius: 6; color: field.editable ? "#f9fafb" : "#f2f4f7"; border.color: input.activeFocus ? "#809aff" : "#e4e7ec" }
        function persist() {
            if (field.ready && !field.loading && field.editable && activeFocus && !inputMethodComposing)
                field.saveValue(text)
        }
        onTextChanged: persist()
        onInputMethodComposingChanged: persist()
        onAccepted: { if (field.saveValue(text)) field.advance() }
    }
    RowLayout {
        visible: field.fieldKind === "date" || field.fieldKind === "exemption"
        Layout.fillWidth: true
        Button {
            id: dateButton
            Layout.fillWidth: true; enabled: field.editable
            text: (field.initialValue || "选择日期") + (field.expired ? " · 已到期" : "")
            palette.buttonText: field.expired ? "#98a2b3" : "#344054"
            onClicked: {
                var capturedKey = field.recordKey
                var value = field.fieldKind === "exemption" ? backend.chooseDate(field.initialValue) : backend.chooseProfileDate(field.initialValue)
                if (capturedKey === field.recordKey && value !== field.initialValue) field.saveValue(value)
            }
        }
        Button { text: "清除"; enabled: field.editable && field.initialValue.length > 0; onClicked: field.saveValue("") }
    }
    Component.onCompleted: { ready = true; loadValue() }
}
