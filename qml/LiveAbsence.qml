import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "liveAbsencePage"
    property var service: backend.liveAbsence
    property string selectedId: ""
    signal openGroupCenter()

    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Label { text: "未进直播间"; font.pixelSize: 22; font.bold: true; color: UiTheme.ink }
            Label {
                text: "按节次读取平台「直播观看时长」；没有观看记录（null）的学员即未进入直播间"
                color: UiTheme.muted; Layout.fillWidth: true; elide: Text.ElideRight
            }
            Label { objectName: "liveAbsenceClass"; text: service.className; color: UiTheme.ink }
            UiButton {
                objectName: "liveAbsenceRefreshLessons"; text: service.busy ? "获取中…" : "刷新课程"
                enabled: !service.busy && !backend.busy && !backend.termsModule.busy; onClicked: service.refreshLessons()
            }
        }
        UiPanel {
            Layout.fillWidth: true; padding: 10
            background: Rectangle { color: UiTheme.surface; radius: 8; border.color: UiTheme.line }
            ColumnLayout {
                anchors.fill: parent; spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "节次"; color: UiTheme.muted }
                    UiComboBox {
                        id: lessonBox; objectName: "liveAbsenceLessonBox"
                        popup.objectName: "liveAbsenceLessonPopup"
                        Layout.fillWidth: true; model: service.lessons; textRole: "label"
                        currentIndex: service.lessonIndex
                        displayText: currentIndex < 0 ? "选择要检查的节次" : currentText
                        enabled: service.lessons.length > 0 && !service.busy && !backend.busy
                        onActivated: function(index) { service.selectLesson(index) }
                        delegate: ItemDelegate {
                            required property var modelData
                            width: parent ? parent.width : 300; text: modelData.label
                            hoverEnabled: true; highlighted: hovered
                        }
                    }
                    UiButton {
                        objectName: "liveAbsenceFetch"; text: service.busy ? "获取中…" : "获取未进直播间名单"
                        enabled: !service.busy && !backend.busy && !backend.termsModule.busy && service.lessonIndex >= 0
                        onClicked: service.fetchRows()
                    }
                    UiButton { text: "取消"; visible: service.busy; onClicked: service.cancel() }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    CheckBox {
                        objectName: "liveAbsenceIncludeZero"; text: "把直播观看 0 秒也算作未进入"
                        checked: service.includeZero; enabled: !service.busy
                        onToggled: service.applyIncludeZero(checked)
                    }
                    CheckBox {
                        objectName: "liveAbsenceExcludeReminded"; text: "排除本节已提醒的学员"
                        checked: service.excludeReminded; enabled: !service.busy
                        onToggled: service.applyExcludeReminded(checked)
                    }
                    CheckBox {
                        objectName: "liveAbsenceShowAll"; text: "显示本节全部学员"
                        checked: service.showAll; enabled: !service.busy
                        onToggled: service.applyShowAll(checked)
                    }
                    Label {
                        objectName: "liveAbsenceFetchedAt"
                        text: service.hasResult ? "获取时间 " + service.fetchedAt.replace("T", " ") : "尚未获取"
                        color: UiTheme.muted; font.pixelSize: 12
                    }
                    UiButton {
                        objectName: "liveAbsenceClearReminders"; text: "清除本节提醒记录"
                        enabled: !service.busy && service.hasResult && service.remindedCount > 0
                        onClicked: clearDialog.open()
                    }
                }
                Label {
                    objectName: "liveAbsenceNotice"; text: service.notice; wrapMode: Text.Wrap
                    Layout.fillWidth: true; color: service.busy ? UiTheme.accent : UiTheme.muted; font.pixelSize: 12
                }
                ProgressBar { visible: service.busy; indeterminate: true; Layout.fillWidth: true }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label { objectName: "liveAbsenceSummary"; text: service.summary; color: UiTheme.ink; Layout.fillWidth: true; wrapMode: Text.Wrap }
        }
        Label {
            objectName: "liveAbsenceIssues"; visible: service.issues !== ""; text: service.issues
            color: UiTheme.warning; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12
        }
        UiPanel {
            Layout.fillWidth: true; Layout.fillHeight: true; padding: 1
            background: Rectangle { color: UiTheme.surface; radius: 8; border.color: UiTheme.line }
            Item {
                anchors.fill: parent
                HorizontalHeaderView {
                    id: headings; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                    height: UiTheme.headerHeight; syncView: table
                    delegate: Rectangle {
                        required property var display
                        implicitWidth: 100; implicitHeight: UiTheme.headerHeight; color: UiTheme.stripe
                        Text { anchors.fill: parent; anchors.leftMargin: 10; text: display; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12; color: UiTheme.ink }
                    }
                }
                TableView {
                    id: table; objectName: "liveAbsenceTable"; model: service.tableModel
                    anchors.top: headings.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                    clip: true; reuseItems: true; columnSpacing: 1; rowSpacing: 1
                    columnWidthProvider: function(c) {
                        return c === 0 ? 60 : c === 1 ? 150 : c === 2 ? 110 : c === 3 ? 110 : c === 4 ? 80 : c === 5 ? 60 : c === 6 ? 160 : Math.max(110, width - 730)
                    }
                    rowHeightProvider: function() { return UiTheme.rowHeight }
                    ScrollBar.vertical: ScrollBar {}
                    ScrollBar.horizontal: ScrollBar {}
                    delegate: Rectangle {
                        required property int row
                        required property int column
                        required property string display
                        required property string studentId
                        implicitHeight: UiTheme.rowHeight; implicitWidth: 100
                        color: studentId === page.selectedId ? UiTheme.selection
                             : (column === 3 && display === "未进入") ? UiTheme.dangerSurface
                             : (column === 7 && display !== "") ? UiTheme.warningSurface
                             : row % 2 ? UiTheme.stripe : UiTheme.surface
                        Text {
                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6
                            text: display; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight; color: UiTheme.ink
                        }
                        TapHandler { onTapped: page.selectedId = studentId }
                    }
                }
                Label {
                    anchors.centerIn: parent; visible: service.visibleCount === 0
                    text: service.hasResult ? "本节没有符合条件的未进入学员" : "选择节次后点「获取未进直播间名单」"
                    color: UiTheme.subtle
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label {
                objectName: "liveAbsenceListable"
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.ink
                text: "可加入新名单 " + service.recipientCount + " 人"
                      + (service.excludeReminded && service.remindedCount > 0 ? "（本节已提醒 " + service.remindedCount + " 人默认跳过）" : "")
                      + (service.includeZero ? "；已把观看 0 秒计入未进入" : "")
            }
            Label {
                visible: service.duplicateCount > 0; color: UiTheme.warning; font.pixelSize: 12
                text: "存在重名 " + service.duplicateCount + " 人，名单内重名会被拦截"
                verticalAlignment: Text.AlignVCenter
            }
            UiButton {
                objectName: "liveAbsenceCreateList"; text: "生成群发名单"
                enabled: !service.busy && !backend.busy && !backend.termsModule.busy
                         && service.recipientCount > 0 && !backend.groupCenter.active
                onClicked: createDialog.open()
            }
        }
    }
    Dialog {
        id: createDialog; objectName: "liveAbsenceCreateDialog"
        anchors.centerIn: parent; modal: true; title: "从未进直播间名单生成群发名单"
        width: Math.min(page.width-30,650); height: Math.min(page.height-30,570)
        property var recordKeys: []
        onOpened: {
            recordKeys = service.recipientKeys.slice()
            groupTitle.text = (service.className || "当前班级") + " · 本节未进直播间"
            messages.load([{type:"text",text:"{姓名}同学，{课程}已经开始了，请尽快进入直播间哦～"}])
        }
        ColumnLayout {
            anchors.fill: parent
            UiTextField { id: groupTitle; objectName: "liveAbsenceListTitle"; placeholderText: "名单名称"; Layout.fillWidth: true }
            Label {
                text: "节次：" + (service.lessonLabel || "未选择") + "；将创建 " + createDialog.recordKeys.length + " 人的独立名单"
                      + (service.excludeReminded && service.remindedCount > 0 ? "（本节已提醒的 " + service.remindedCount + " 人不再加入）" : "")
                      + "。无姓名及补位行跳过；仅创建，不会立即发送。"
                wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted
            }
            Label {
                text: "可用变量：{" + service.messagePlaceholders.join("}、{") + "}"
                wrapMode: Text.Wrap; Layout.fillWidth: true; color: UiTheme.muted; font.pixelSize: 12
            }
            ScrollView {
                id: messageScroll; Layout.fillWidth: true; Layout.fillHeight: true
                contentWidth: availableWidth; clip: true
                MessageFields { id: messages; width: messageScroll.availableWidth }
            }
            Label { text: backend.groupCenter.status; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                UiButton { text: "取消"; onClicked: createDialog.close() }
                UiButton {
                    objectName: "liveAbsenceConfirmCreate"; text: "创建并打开群发中心"
                    onClicked: {
                        if (backend.groupCenter.createFromLiveAbsence(groupTitle.text, messages.values(), createDialog.recordKeys)) {
                            createDialog.close(); page.openGroupCenter()
                        }
                    }
                }
            }
        }
    }
    Dialog {
        id: clearDialog; objectName: "liveAbsenceClearDialog"
        anchors.centerIn: parent; modal: true; title: "清除本节提醒记录"
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label {
            text: "将清除「" + (service.lessonLabel || "未选择") + "」的全部提醒记录，共 " + service.remindedCount
                  + " 人；清除后这些人会重新进入新的群发名单。"
            wrapMode: Text.Wrap; lineHeight: 1.5
        }
        onAccepted: service.clearReminders()
    }
}
