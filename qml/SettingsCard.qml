import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 设置卡片骨架：标题 / 说明 / 内容 / 底部操作，四种设置分组共用。
Item {
    id: card
    property string title: ""
    property string subtitle: ""
    property string description: ""
    // 状态标签（是否已保存 / 是否已绑定），由卡片自行渲染在 headerRight。
    property string tag: ""
    property color tagColor: "#027a48"
    property color tagBackground: "#ecfdf3"
    // 并排卡片用它把底部操作压到同一基线。
    property bool stretch: false
    // 由设置页注入：鼠标停在下拉框上时滚轮仍然滚动整页。
    property var pageScroll: null
    // 内容区宽度，子组件用它对齐自己的宽度。
    readonly property real contentWidth: Math.max(0, width - 32)

    default property alias content: contentLayout.data
    property alias footer: footerLayout.data
    property alias headerRight: headerRightPlaceholder.data

    implicitHeight: layout.implicitHeight + 32

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: "#ffffff"
        border.color: "#e1e6ef"
    }

    ColumnLayout {
        id: layout
        x: 16; y: 16
        width: card.contentWidth
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Label {
                text: card.title
                font.pixelSize: 15; font.bold: true; color: UiTheme.ink
            }
            Label {
                visible: text.length > 0
                text: card.subtitle
                font.pixelSize: 12; color: UiTheme.muted
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Item { visible: !card.subtitle; Layout.fillWidth: true }
            Item {
                id: headerRightPlaceholder
                Layout.preferredWidth: childrenRect.width
                Layout.preferredHeight: childrenRect.height
            }
        }

        Label {
            visible: card.description.length > 0
            text: card.description
            font.pixelSize: 12; color: UiTheme.muted; wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        // 内容：子组件直接由本布局管理，高度自然并入 implicitHeight。
        ColumnLayout {
            id: contentLayout
            Layout.fillWidth: true
            Layout.fillHeight: card.stretch
            spacing: 10
            SettingsWheelGuard { Layout.fillWidth: true; Layout.preferredHeight: 0; view: card.pageScroll }
        }

        ColumnLayout {
            id: footerLayout
            Layout.fillWidth: true
            spacing: 10
        }
    }
}
