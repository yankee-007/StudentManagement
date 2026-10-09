import QtQuick
import QtQuick.Controls

Item {
    id: order
    objectName: "profileFieldOrder"
    property var profiles
    readonly property int count: fieldList.count
    readonly property bool dragging: draggingId.length > 0
    readonly property int rowHeight: 48
    readonly property int rowSpacing: 6
    readonly property int stride: rowHeight + rowSpacing
    property int dropIndex: -1 // Insertion gap, including the gap after the final card.
    property int sourceIndex: -1
    property string draggingId: ""
    property var draggingField: ({})
    property point pointer: Qt.point(0, 0)
    property point grabAnchor: Qt.point(0, 0)
    property string recentId: ""
    property int dragGeneration: 0
    signal removeField(string fieldId, string fieldName)
    implicitHeight: Math.min(count * stride + 12, 380)

    ListModel { id: fieldModel }
    function syncFields() {
        var fields = profiles ? profiles.managedFields : []
        for (var i = 0; i < fields.length; ++i) {
            var f = fields[i]
            var record = {field_id: f.field_id, name: f.name, show_column: !!f.show_column,
                locked: !!f.locked, deletable: !!f.deletable, kind: f.kind || "", note: f.note || ""}
            var signature = JSON.stringify(record)
            var existing = -1
            for (var j = i; j < fieldModel.count; ++j) {
                if (fieldModel.get(j).record.field_id === record.field_id) { existing = j; break }
            }
            if (existing < 0) fieldModel.insert(i, {record: record, signature: signature})
            else {
                if (existing !== i) fieldModel.move(existing, i, 1)
                if (fieldModel.get(i).signature !== signature) {
                    fieldModel.setProperty(i, "record", record)
                    fieldModel.setProperty(i, "signature", signature)
                }
            }
        }
        if (fieldModel.count > fields.length) fieldModel.remove(fields.length, fieldModel.count - fields.length)
    }
    function resetPosition() {
        cancelDrag(); recentId = ""
        Qt.callLater(function() { if (!order.dragging) fieldList.positionViewAtBeginning() })
    }

    function cancelDrag() {
        dragGeneration += 1
        draggingId = ""
        draggingField = ({})
        sourceIndex = -1
        dropIndex = -1
    }
    function beginDrag(field, index, card, start, current) {
        sourceIndex = index
        draggingField = field
        var local = mapToItem(card, start.x, start.y)
        grabAnchor = Qt.point(local.x / card.width, local.y / card.height)
        draggingId = field.field_id
        forceActiveFocus()
        updatePointer(current)
    }
    function updatePointer(point) {
        pointer = point
        if (point.x < 0 || point.x > width || point.y < -12 || point.y > height + 12) {
            dropIndex = -1
            return
        }
        var y = mapToItem(fieldList.contentItem, point.x, point.y).y - fieldList.originY - 8
        dropIndex = Math.max(0, Math.min(count, Math.floor((y + rowSpacing / 2 + stride / 2) / stride)))
    }
    function finishDrag() {
        var key = draggingId
        var target = dropIndex > sourceIndex ? dropIndex - 1 : dropIndex
        var valid = dragging && dropIndex >= 0 && target !== sourceIndex
        cancelDrag() // Clear the gesture before applying the saved order.
        if (valid && saveMove(key, target)) {
            recentId = key
            recentTimer.restart()
            fieldList.positionViewAtIndex(target, ListView.Contain)
        }
    }
    function saveMove(fieldId, index) {
        return typeof profiles.moveFieldAsync === "function" ? profiles.moveFieldAsync(fieldId, index) : profiles.moveField(fieldId, index)
    }
    function moveBy(fieldId, index, offset) {
        cancelDrag()
        if (saveMove(fieldId, index + offset)) {
            recentId = fieldId
            recentTimer.restart()
            fieldList.positionViewAtIndex(index + offset, ListView.Contain)
        }
    }
    Keys.onEscapePressed: function(event) {
        if (dragging) { cancelDrag(); event.accepted = true }
        else event.accepted = false
    }
    onVisibleChanged: if (!visible) cancelDrag()
    onProfilesChanged: { cancelDrag(); syncFields() }
    Component.onCompleted: syncFields()
    Connections {
        target: order.profiles
        ignoreUnknownSignals: true // The shared workflow controller only has changed.
        function onChanged() { order.cancelDrag(); order.syncFields() }
        function onFieldLayoutChanged() { order.cancelDrag(); order.syncFields() }
    }

    Timer { id: recentTimer; interval: 650; onTriggered: order.recentId = "" }
    Timer {
        interval: 16; repeat: true
        running: order.dragging && order.dropIndex >= 0
        onTriggered: {
            var edge = Math.min(44, fieldList.height / 4)
            var delta = order.pointer.y < edge ? -Math.ceil((edge - order.pointer.y) / 4)
                      : order.pointer.y > fieldList.height - edge ? Math.ceil((order.pointer.y - fieldList.height + edge) / 4) : 0
            if (delta !== 0) {
                var minY = fieldList.originY // Preserve the first gap after incremental moves shift the origin.
                var maxY = Math.max(minY, fieldList.originY + fieldList.contentHeight - fieldList.height)
                fieldList.contentY = Math.max(minY, Math.min(maxY, fieldList.contentY + delta))
                order.updatePointer(order.pointer)
            }
        }
    }
    ListView {
        id: fieldList
        objectName: "profileFieldList"
        anchors.fill: parent
        model: fieldModel
        spacing: order.rowSpacing
        header: Item { height: 8 }
        footer: Item { height: 8 }
        clip: true
        interactive: !order.dragging
        cacheBuffer: order.dragging ? contentHeight : 0
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        onModelChanged: order.cancelDrag()
        delegate: Item {
            id: row
            required property var record
            readonly property var modelData: record
            required property int index
            objectName: "profileFieldRow"
            width: fieldList.width; height: order.rowHeight
            readonly property bool pickedUp: order.draggingId === modelData.field_id
            Rectangle {
                anchors.fill: card
                visible: row.pickedUp
                radius: 6; color: UiTheme.stripe; border.color: UiTheme.line
                Label { anchors.centerIn: parent; text: "移动「" + row.modelData.name + "」"; color: UiTheme.muted; font.pixelSize: 12 }
            }
            ProfileFieldCard {
                id: card
                objectName: "profileFieldCard"
                x: 8; width: parent.width - 24; height: order.rowHeight
                opacity: row.pickedUp ? 0 : 1
                field: row.modelData; position: row.index; fieldCount: order.count
                interactive: !order.dragging
                recent: order.recentId === row.modelData.field_id
                onVisibilityToggled: function(value) { order.profiles.setFieldVisible(row.modelData.field_id, value) }
                onMoveRequested: function(offset) { order.moveBy(row.modelData.field_id, row.index, offset) }
                onRemoveRequested: order.removeField(row.modelData.field_id, row.modelData.name)
            }
            MouseArea {
                id: grip
                objectName: "fieldDragHandle"
                x: card.x + 6; y: 8; width: 36; height: row.height - 16
                hoverEnabled: true; preventStealing: true
                cursorShape: order.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property point pressPoint
                property int pressGeneration: -1
                onPressed: function(mouse) {
                    pressPoint = mapToItem(order, mouse.x, mouse.y)
                    pressGeneration = order.dragGeneration
                }
                onPositionChanged: function(mouse) {
                    if (!pressed || pressGeneration !== order.dragGeneration) return
                    var point = mapToItem(order, mouse.x, mouse.y)
                    if (!order.dragging && Math.hypot(point.x - pressPoint.x, point.y - pressPoint.y) >= Qt.styleHints.startDragDistance)
                        order.beginDrag(row.modelData, row.index, card, pressPoint, point)
                    else if (order.dragging) order.updatePointer(point)
                }
                onReleased: function(mouse) {
                    if (order.dragging) {
                        order.updatePointer(mapToItem(order, mouse.x, mouse.y))
                        order.finishDrag()
                    }
                }
                onCanceled: order.cancelDrag()
                ToolTip.visible: containsMouse && !pressed; ToolTip.text: "拖动调整字段顺序"
            }
        }
    }
    Item {
        anchors.fill: parent; clip: true; z: 4
        Rectangle {
            objectName: "fieldInsertionGap"
            x: 8; width: parent.width - 24; height: 6; radius: 3
            y: fieldList.originY + 8 + order.dropIndex * order.stride - fieldList.contentY - order.rowSpacing / 2 - height / 2
            visible: order.dragging && order.dropIndex >= 0
            color: UiTheme.selection
            Rectangle { anchors.centerIn: parent; width: parent.width; height: 2; radius: 1; color: UiTheme.accent }
            Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: UiTheme.accent }
            Rectangle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: UiTheme.accent }
        }
    }
    Item {
        id: floatingCard
        objectName: "fieldDragPreview"
        z: 3; visible: order.dragging
        // Preserve the pressed point throughout narrowing and movement, without clamping the preview.
        property real widthFactor: visible ? 0.9 : 1
        x: order.pointer.x - order.grabAnchor.x * width
        y: order.pointer.y - order.grabAnchor.y * height
        width: (fieldList.width - 24) * widthFactor; height: order.rowHeight
        opacity: visible ? 0.72 : 1
        Behavior on widthFactor { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Repeater {
            model: 4
            Rectangle {
                required property int index
                x: -index * 2; y: 5 + index * 2
                width: floatingCard.width + index * 4; height: floatingCard.height
                radius: 8 + index * 2; color: UiTheme.ink
                opacity: UiTheme.darkMode ? 0.09 : 0.035
            }
        }
        ProfileFieldCard {
            anchors.fill: parent; field: order.draggingField
            position: order.sourceIndex; fieldCount: order.count
            interactive: false; lifted: true
        }
    }
}
