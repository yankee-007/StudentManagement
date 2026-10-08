import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 设置页：提示行 + 平台账号两张卡片 + 班期对应关系 + 凭据说明（单列，窄屏卡片上下堆叠）。
Item {
    id: page
    property var settings: backend.settingsModule
    // 宽度足够时两张账号卡片并排，否则上下堆叠。
    property bool cardsSideBySide: width >= 840
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
                Label { text: "外观、平台账号与班期对应关系"; font.pixelSize: 12; color: UiTheme.subtle; Layout.fillWidth: true }
                UiButton { objectName: "refreshSettingsButton"; text: "刷新状态"; enabled: !page.settings.busy; onClicked: page.settings.refresh() }
            }
            Label {
                objectName: "settingsNotice"
                text: page.settings.notice
                color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            SettingsCard {
                objectName: "appearanceSettingsCard"
                Layout.fillWidth: true
                title: "外观"
                description: "切换后立即生效，主界面与浮窗同步。下次启动沿用此选择。"
                pageScroll: pageScroll
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    Label { text: "界面模式"; color: UiTheme.muted }
                    UiButton {
                        objectName: "appearanceLightButton"; text: "亮色"; checked: !UiTheme.darkMode
                        Accessible.name: "亮色模式"
                        onClicked: page.settings.setAppearanceMode("light")
                    }
                    UiButton {
                        objectName: "appearanceDarkButton"; text: "暗色"; checked: UiTheme.darkMode
                        Accessible.name: "暗色模式"
                        onClicked: page.settings.setAppearanceMode("dark")
                    }
                    Item { Layout.fillWidth: true }
                }
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
                subtitle: "共 " + page.settings.termClasses.length + " 个完课平台班期"
                description: "完课平台班期固定，每行选择对应的作业平台班级；可留空，选择后自动保存，重启后保留。未绑定班期不能获取两平台学习数据或新建催办。"
                pageScroll: pageScroll
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    UiButton { objectName: "refreshTermsButton"; text: "刷新完课班期"; enabled: !backend.busy && !backend.termsModule.busy && !page.settings.busy; onClicked: backend.termsModule.refreshAll() }
                    UiButton { objectName: "fetchHomeworkClassesButton"; text: page.settings.busy ? "获取中…" : "获取作业班级"; enabled: !page.settings.busy && !backend.busy && !backend.termsModule.busy; onClicked: page.settings.fetchHomeworkClasses() }
                }
                Repeater {
                    objectName: "bindingRows"
                    model: page.settings.termClasses
                    SettingsBindingRow {
                        required property var modelData
                        Layout.fillWidth: true
                        termId: String(modelData.termId)
                        termName: modelData.name
                        settings: page.settings
                        scrollView: pageScroll
                    }
                }
                Label {
                    Layout.fillWidth: true
                    visible: page.settings.termClasses.length === 0
                    text: "暂无完课平台班期，请先保存完课平台账号，再点击「刷新完课班期」。"
                    color: UiTheme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
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

}
