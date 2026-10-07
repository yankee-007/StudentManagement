import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "remarkRenamerPage"
    property var renamer: backend.remarkRenamer
    property bool loadingOptions: false
    property var pickedKeys: []
    property string pickedHint: ""

    function loadOptions() {
        saveTimer.stop()
        loadingOptions = true
        prefix.text = renamer.prefix || ""
        waitSeconds.text = "0.5"
        timeoutSeconds.text = "3"
        loadingOptions = false
    }
    function scheduleSave() {
        if (!loadingOptions && !renamer.active) saveTimer.restart()
    }
    function optionNumber(text, fallback) {
        var value = Number(text)
        return text !== "" && isFinite(value) ? value : fallback
    }
    function saveOptions() {
        saveTimer.stop()
        if (loadingOptions || renamer.active) return true
        return renamer.saveOptions(prefix.text, {wait: optionNumber(waitSeconds.text, 0.5), timeout: optionNumber(timeoutSeconds.text, 3)})
    }
    function pickedIds() {
        var ids = []
        for (var i = 0; i < picked.count; i++) ids.push(picked.get(i).sid)
        return ids
    }
    function togglePick(sid, on) {
        for (var i = 0; i < picked.count; i++) {
            if (picked.get(i).sid === sid) {
                if (!on) picked.remove(i)
                renamer.notifyPicked()
                return
            }
        }
        if (on) picked.append({sid: sid})
        renamer.notifyPicked()
    }
    function startRun() {
        if (!saveOptions()) return
        if (renamer.start([])) startDialog.rows = renamer.pendingCount
        else startDialog.close()
    }

    Timer { id: saveTimer; interval: 600; repeat: false; onTriggered: page.saveOptions() }
    Connections {
        target: renamer
        // Class switch and list reload change the saved prefix of another class;
        // drop any pending save so it cannot write the old value into the new class.
        function onPrefixChanged() {
            saveTimer.stop()
            loadingOptions = true
            prefix.text = renamer.prefix || ""
            loadingOptions = false
        }
    }
    ListModel { id: picked }
    Component.onCompleted: loadOptions()

    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "备注批改"; font.pixelSize: 22; font.bold: true }
            Label {
                text: "按姓名搜索 → Ctrl+O 浮窗读取真实备注 → 旧格式改为「前缀+姓名」；已符合的直接入库跳过"
                color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight
            }
            Label { text: renamer.className; color: UiTheme.ink }
            UiButton { objectName: "remarkReloadButton"; text: "刷新名单"; enabled: !renamer.active; onClicked: { if (saveOptions()) renamer.reload() } }
        }
        UiPanel {
            Layout.fillWidth: true; padding: 10
            background: Rectangle { color: UiTheme.surface; radius: 8; border.color: UiTheme.line }
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Label { text: "备注前缀" }
                    UiTextField {
                        id: prefix; objectName: "remarkPrefixInput"; width: 140
                        placeholderText: "例如 py175"; enabled: !renamer.active
                        onTextEdited: page.scheduleSave()
                    }
                    Label { text: "前缀＋姓名 = 目标备注；按当前班期保存" ; color: UiTheme.muted }
                    Label { text: "浮窗等待（秒）" }
                    UiTextField { id: waitSeconds; objectName: "remarkWaitInput"; width: 70; enabled: !renamer.active; onTextEdited: page.scheduleSave() }
                    Label { text: "浮窗超时（秒）" }
                    UiTextField { id: timeoutSeconds; objectName: "remarkTimeoutInput"; width: 70; enabled: !renamer.active; onTextEdited: page.scheduleSave() }
                }
                Label { text: renamer.summary; color: UiTheme.ink; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Label {
                    text: "只有画像「微信=是」的学员参与；重名者仅标记提示。修改成功与判定已符合都会写回数据库，群发搜索可直接使用新备注。"
                    color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            UiButton {
                objectName: "remarkStartButton"; text: renamer.active ? "处理中…" : "扫描并批改"; highlighted: true
                enabled: !renamer.active && renamer.pendingCount > 0 && prefix.text.length > 0
                onClicked: startDialog.open()
            }
            Label { text: "待处理 " + renamer.pendingCount + " 人"; color: UiTheme.muted }
            UiButton {
                objectName: "remarkForceButton"; text: "强改选中项"
                enabled: !renamer.active && picked.count > 0 && prefix.text.length > 0
                onClicked: forceDialog.open()
            }
            UiButton {
                objectName: "remarkRetryButton"; text: "重试未找到／失败"
                enabled: !renamer.active && renamer.issueCount > 0
                onClicked: renamer.retryFailed()
            }
            Item { Layout.fillWidth: true }
            UiButton {
                objectName: "remarkPauseButton"; text: renamer.pauseRequested ? "等待当前联系人结束…" : "暂停（全局 F11）"
                visible: renamer.active; enabled: !renamer.pauseRequested && !renamer.isPaused; onClicked: renamer.pause()
            }
            UiButton { objectName: "remarkResumeButton"; text: "继续"; visible: renamer.active; enabled: renamer.isPaused; onClicked: renamer.resume() }
            UiButton { objectName: "remarkStopButton"; text: "结束本轮"; visible: renamer.active; onClicked: renamer.stop() }
        }
        Label { text: renamer.notice; color: renamer.active ? UiTheme.warning : UiTheme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            HorizontalHeaderView {
                id: header; syncView: table; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: UiTheme.headerHeight
                delegate: Rectangle {
                    required property var display
                    implicitWidth: 110; implicitHeight: UiTheme.headerHeight; color: UiTheme.stripe
                    Text { anchors.fill: parent; anchors.margins: 6; text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12; color: UiTheme.ink }
                }
            }
            TableView {
                id: table; objectName: "remarkTable"
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: header.bottom; anchors.bottom: parent.bottom
                model: renamer.tableModel; clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                columnWidthProvider: function(c) {
                    var widths = [110, 110, 150, 170, 80, 300, 90]
                    return c >= 0 && c < widths.length ? widths[c] : 110
                }
                rowHeightProvider: function(r) { return UiTheme.rowHeight }
                ScrollBar.horizontal: ScrollBar {}
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property int row
                    required property int column
                    required property string display
                    required property string studentId
                    property bool isPicked: {
                        var revision = renamer.pickRevision
                        for (var i = 0; i < picked.count; i++) if (picked.get(i).sid === studentId) return true
                        return false
                    }
                    implicitHeight: UiTheme.rowHeight; implicitWidth: 110
                    color: isPicked ? UiTheme.selection : row % 2 ? UiTheme.stripe : UiTheme.surface
                    Text {
                        anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 6
                        text: display; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 13; textFormat: Text.PlainText
                        color: column === 4 ? UiTheme.warning : UiTheme.ink
                    }
                    TapHandler { onTapped: { page.togglePick(studentId, !parent.isPicked); renamer.selectRow(row) } }                }
            }
            Label {
                anchors.centerIn: parent; visible: renamer.visibleCount === 0
                text: "当前班期没有画像「微信=是」的学员；请先在学员画像中确认微信字段"
                horizontalAlignment: Text.AlignHCenter; color: UiTheme.subtle; lineHeight: 1.6
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "选中 " + picked.count + " 人" + (renamer.cursorText.length > 0 ? " · " + renamer.cursorText : " · 点击表格可选中/取消并定位"); color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
            UiButton { objectName: "remarkClearPickButton"; text: "清空选中"; enabled: picked.count > 0; onClicked: picked.clear() }
            UiButton { objectName: "remarkSkipButton"; text: "标记跳过所选"; enabled: !renamer.active && picked.count > 0; onClicked: skipDialog.open() }
            UiButton { objectName: "remarkImagesButton"; text: "打开留证截图目录"; onClicked: renamer.openEvidenceDir() }
        }
    }
    Dialog {
        id: startDialog; objectName: "remarkStartDialog"; anchors.centerIn: parent; modal: true
        width: Math.min(page.width - 30, 560)
        title: "开始扫描并批改备注"
        ColumnLayout {
            anchors.fill: parent
            Label {
                text: "本轮将扫描 " + startDialog.rows + " 位待处理学员。\n" +
                      "· 用姓名在企业微信中搜索，Ctrl+O 打开浮窗读取真实备注\n" +
                      "· 备注为「姓名/新生」时改为「" + prefix.text + "姓名」并保存\n" +
                      "· 备注已含「" + prefix.text + "姓名」时跳过改名，仅入库\n" +
                      "· 其它格式只记录为「待确认」，不会自动改\n" +
                      "处理期间不要操作电脑；F11 可在当前联系人结束后暂停，单人失败不中止本轮。"
                wrapMode: Text.Wrap; Layout.fillWidth: true; lineHeight: 1.4
            }
            Label { text: "请先登录企业微信，并保持主窗口可用。"; color: UiTheme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: renamer.notice; color: UiTheme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                UiButton { objectName: "remarkConfirmStart"; text: "开始处理"; highlighted: true; onClicked: { startDialog.close(); page.startRun() } }
                UiButton { text: "取消"; onClicked: startDialog.close() }
            }
        }
    }
    Dialog {
        id: forceDialog; objectName: "remarkForceDialog"; anchors.centerIn: parent; modal: true
        width: Math.min(page.width - 30, 520)
        title: "强制改为目标备注"
        ColumnLayout {
            anchors.fill: parent
            Label {
                text: "将选中 " + picked.count + " 位学员的备注统一改为「" + prefix.text + "姓名」，不论当前是什么格式。\n" +
                      "仅在浮窗确认到学员本人后才会保存；姓名不匹配的会记入「未找到」。"
                wrapMode: Text.Wrap; Layout.fillWidth: true; lineHeight: 1.4
            }
            Label { text: renamer.notice; color: UiTheme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                UiButton { objectName: "remarkConfirmForce"; text: "确认强改"; highlighted: true; onClicked: { forceDialog.close(); renamer.forceSelected(page.pickedIds()) } }
                UiButton { text: "取消"; onClicked: forceDialog.close() }
            }
        }
    }
    Dialog {
        id: skipDialog; anchors.centerIn: parent; modal: true; title: "标记跳过"; standardButtons: Dialog.Ok | Dialog.Cancel
        Label {
            text: "选中 " + picked.count + " 位学员将标记为「已跳过」，重新扫描时不再处理。\n" +
                  "跳过后如需恢复，可在「重试未找到／失败」或清空标记后重新扫描。"
            wrapMode: Text.Wrap
        }
        onAccepted: {
            var ids = page.pickedIds()
            for (var i = 0; i < ids.length; i++) renamer.skip(ids[i])
            picked.clear()
        }
    }
}
