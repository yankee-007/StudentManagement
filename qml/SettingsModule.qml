import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 设置页：提示行 + 平台账号两张卡片 + 班期对应关系 + 凭据说明（单列，窄屏卡片上下堆叠）。
Item {
    id: page
    property var settings: backend.settingsModule
    property var selectedTerm: termBox.currentIndex >= 0 && termBox.currentIndex < page.settings.termClasses.length ? page.settings.termClasses[termBox.currentIndex] : ({})
    property var selectedClass: classBox.currentIndex >= 0 && classBox.currentIndex < page.settings.homeworkClasses.length ? page.settings.homeworkClasses[classBox.currentIndex] : ({})
    // 宽度足够时两张账号卡片并排，否则上下堆叠。
    property bool cardsSideBySide: width >= 840
    // 只用于驱动只读文案重新求值。
    property int bindingTick: 0

    function bindingText() {
        page.bindingTick
        var b = page.settings.bindingFor(String(page.selectedTerm.termId || ""))
        return b.class_id ? b.class_name + " · 班级 ID " + b.class_id + " · 课程 ID " + b.course_id : ""
    }

    function hasBinding() {
        page.bindingTick
        return !!page.settings.bindingFor(String(page.selectedTerm.termId || "")).class_id
    }

    function courseLabel() {
        var entry = page.selectedClass
        if (!entry || entry.id === undefined) return "选择作业平台班级后自动对应课程。"
        var ids = entry.course_ids || []
        if (!ids.length) return "平台未返回该班级的课程，请先获取作业班级。"
        return ids.length > 1 ? "该班级有多个课程，请选择：" : "平台主课程，自动对应。"
    }

    // 打开本页或切换班期时，带出该班期已确认的作业班级；没有对应关系就留空。
    function syncBinding() {
        page.bindingTick++
        var classes = page.settings.homeworkClasses
        var bound = Number(page.settings.bindingFor(String(page.selectedTerm.termId || "")).class_id || 0)
        for (var i = 0; i < classes.length; i++) {
            if (Number(classes[i].id) === bound) { classBox.currentIndex = i; return }
        }
        classBox.currentIndex = -1
    }

    function confirmBinding() {
        page.settings.saveBinding(String(page.selectedTerm.termId || ""), Number(page.selectedClass.id),
            courseBox.visible ? Number(courseBox.currentText) : 0)
    }

    Flickable {
        id: pageScroll
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        contentWidth: width - scrollBar.width
        contentHeight: contentEnd.y
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { id: scrollBar; policy: ScrollBar.AlwaysOn }

        ColumnLayout {
            id: frame
            width: pageScroll.contentWidth
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Label { text: "设置"; font.pixelSize: 19; font.bold: true; color: UiTheme.ink }
                Label { text: "平台账号与班期对应关系"; font.pixelSize: 12; color: "#98a2b3"; Layout.fillWidth: true }
                UiButton { objectName: "refreshSettingsButton"; text: "刷新状态"; enabled: !page.settings.busy; onClicked: page.settings.refresh() }
            }
            Label {
                objectName: "settingsNotice"
                text: page.settings.notice
                color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Label {
                text: page.cardsSideBySide ? "平台账号 · 两个平台各一份账号，保存后下次获取数据生效"
                                           : "平台账号"
                font.pixelSize: 13; font.bold: true; color: UiTheme.ink
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.cardsSideBySide ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12
                AccountSettingsCard {
                    objectName: "completionAccountCard"
                    platform: "completion"; title: "追光鲸鱼 · 完课平台"
                    pageScroll: pageScroll
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true
                }
                AccountSettingsCard {
                    objectName: "homeworkAccountCard"
                    platform: "homework"; title: "作业平台"
                    pageScroll: pageScroll
                    Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true
                }
            }

            SettingsCard {
                objectName: "bindingCard"
                Layout.fillWidth: true
                title: "班期对应关系"
                subtitle: "两个平台的班期 ID 不同，每个班期确认一次"
                description: "未绑定的班期不能获取学习数据，也不能新建催办。"
                pageScroll: pageScroll
                headerRight: Rectangle {
                    implicitWidth: bindingTag.implicitWidth + 16
                    implicitHeight: 20
                    radius: 10
                    color: page.hasBinding() ? "#ecfdf3" : "#fffaeb"
                    Label {
                        id: bindingTag
                        anchors.centerIn: parent
                        text: page.hasBinding() ? "已绑定" : "未绑定"
                        font.pixelSize: 12
                        color: page.hasBinding() ? "#027a48" : UiTheme.warning
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 10
                    Label { text: "追光鲸鱼班期"; color: UiTheme.muted; font.pixelSize: 12; Layout.preferredWidth: 96; Layout.alignment: Qt.AlignVCenter }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        UiComboBox {
                            id: termBox; objectName: "settingTermBox"
                            Layout.fillWidth: true
                            model: page.settings.termClasses; textRole: "name"
                            enabled: !page.settings.busy
                            onActivated: page.syncBinding()
                            SettingsWheelGuard { view: pageScroll }
                        }
                        UiButton { objectName: "refreshTermsButton"; text: "刷新班期"; enabled: !backend.busy && !backend.termsModule.busy; onClicked: backend.termsModule.refreshAll() }
                    }
                    Label { text: "作业平台班级"; color: UiTheme.muted; font.pixelSize: 12; Layout.preferredWidth: 96; Layout.alignment: Qt.AlignVCenter }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        UiComboBox {
                            id: classBox; objectName: "settingClassBox"
                            Layout.fillWidth: true
                            model: page.settings.homeworkClasses; textRole: "name"
                            enabled: !page.settings.busy
                            // 换班级时回到该班级的主课程，避免沿用上一个班级的课程。
                            onCurrentIndexChanged: courseBox.currentIndex = 0
                            SettingsWheelGuard { view: pageScroll }
                        }
                        UiButton { objectName: "fetchHomeworkClassesButton"; text: page.settings.busy ? "获取中…" : "获取作业班级"; enabled: !page.settings.busy; onClicked: page.settings.fetchHomeworkClasses() }
                    }
                    Label { text: "课程"; color: UiTheme.muted; font.pixelSize: 12; Layout.preferredWidth: 96; Layout.alignment: Qt.AlignTop; topPadding: 6 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Rectangle {
                                objectName: "settingCourseValue"
                                Layout.fillWidth: true
                                implicitHeight: 28
                                radius: 6
                                color: "#f8fafc"; border.color: UiTheme.line
                                Label {
                                    anchors.left: parent.left; anchors.leftMargin: 9; anchors.verticalCenter: parent.verticalCenter
                                    text: page.selectedClass.course_ids && page.selectedClass.course_ids.length ? "课程 ID " + page.selectedClass.course_ids[0] : "尚未获取课程"
                                    font.pixelSize: 12; color: UiTheme.muted
                                }
                            }
                            UiComboBox {
                                id: courseBox
                                objectName: "settingCourseBox"
                                visible: (page.selectedClass.course_ids || []).length > 1
                                Layout.preferredWidth: 110
                                model: page.selectedClass.course_ids || []
                                SettingsWheelGuard { view: pageScroll }
                            }
                        }
                        Label { text: page.courseLabel(); font.pixelSize: 12; color: "#98a2b3"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }

                footer: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#eef1f6" }
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "修改班期或班级后需要重新确认。"; color: "#98a2b3"; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                        UiButton {
                            objectName: "confirmBindingButton"
                            text: "确认绑定"
                            highlighted: true
                            enabled: !page.settings.busy && page.selectedClass.id !== undefined && page.selectedTerm.termId !== undefined
                            onClicked: page.confirmBinding()
                        }
                    }
                    Rectangle {
                        objectName: "bindingStatus"
                        Layout.fillWidth: true
                        visible: page.hasBinding()
                        implicitHeight: 30
                        radius: 8
                        color: "#ecfdf3"; border.color: "#d3f1e0"
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                            spacing: 8
                            Label { text: "✓ 已绑定"; color: "#027a48"; font.pixelSize: 12; font.bold: true }
                            Label { text: page.bindingText(); color: UiTheme.muted; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }
            }

            SettingsCard {
                objectName: "contactDefaultsCard"
                Layout.fillWidth: true
                title: "企微联系人"
                subtitle: "学员画像与催办工作台共用"
                description: "未配置过前缀的班期使用此默认值。已记住的班期前缀保留，可在填写卡片的「选项」中改用默认值。"
                pageScroll: pageScroll
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Label { text: "默认前缀"; color: UiTheme.muted }
                    UiTextField {
                        id: defaultPrefix; objectName: "defaultContactPrefix"
                        Layout.fillWidth: true; text: backend.contactOpener.defaultPrefix
                        placeholderText: "可留空，例如 py169"; enabled: !backend.contactOpener.active
                        Accessible.name: "默认联系人前缀"
                    }
                    UiButton {
                        objectName: "saveDefaultContactPrefix"; text: "保存默认值"
                        enabled: !backend.contactOpener.active
                        onClicked: { contactDefaultStatus.text = backend.contactOpener.setDefaultPrefix(defaultPrefix.text) ? "默认前缀已保存" : backend.contactOpener.notice }
                    }
                }
                Label { id: contactDefaultStatus; objectName: "contactDefaultStatus"; text: ""; visible: text.length > 0; color: UiTheme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            SettingsCard {
                objectName: "credentialNotesCard"
                Layout.fillWidth: true
                title: "凭据说明"
                pageScroll: pageScroll
                Label {
                    Layout.fillWidth: true
                    text: "密码由 Windows 凭据管理器保管，保存后不在界面回显；更换账号时必须同时输入该账号的密码。\n作业平台班级目录按当前作业账号缓存在本地，换账号后需要重新「获取作业班级」。"
                    color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.6
                }
            }

            Item { id: contentEnd; objectName: "settingsContentEnd"; Layout.fillWidth: true; implicitHeight: 0 }
        }
    }

    // 缓存刷新、绑定保存或重新进入本页后，同步下拉框与对应关系提示。
    Connections {
        target: page.settings
        function onChanged() { page.syncBinding() }
    }
}
