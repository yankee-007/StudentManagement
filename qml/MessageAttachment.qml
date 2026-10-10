import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: attachment
    required property var fileChooser
    property string path: ""
    property bool compact: false
    property real availableWidth: 320
    property real maximumImageHeight: 180
    property int revision: 0
    readonly property var info: { var currentRevision=revision; return path && fileChooser ? fileChooser.messageFileInfo(path) : ({}) }
    readonly property bool showsImage: !!info.image && preview.status!==Image.Error
    readonly property bool imageReady: preview.status===Image.Ready
    readonly property real scaleFactor: Math.max(0,Math.min(1,Math.min(240,availableWidth)/Math.max(1,info.width || 1),maximumImageHeight/Math.max(1,info.height || 1)))
    readonly property real previewWidth: Math.max(1,Math.floor((info.width || 1)*scaleFactor))
    readonly property real previewHeight: Math.max(1,Math.floor((info.height || 1)*scaleFactor))
    readonly property string extension: info.extension || ""
    readonly property string iconText: /^(docx?|odt)$/.test(extension) ? "W" : /^(xlsx?|csv|ods)$/.test(extension) ? "X" : /^(pptx?|odp)$/.test(extension) ? "P" : extension ? extension.toUpperCase().slice(0,4) : "FILE"
    readonly property color iconColor: iconText==="W" ? "#1d5bc4" : iconText==="X" ? "#237849" : iconText==="P" ? "#be522d" : extension==="pdf" ? "#bd3d3d" : UiTheme.accentFill
    implicitWidth: compact ? Math.min(320,availableWidth) : showsImage ? previewWidth : Math.min(320,availableWidth)
    implicitHeight: compact ? 32 : showsImage ? previewHeight : 88
    Accessible.role: Accessible.StaticText
    Accessible.name: (showsImage ? "图片：" : "文件：")+(info.name || "附件")
    Accessible.description: !info.available ? "文件已失效" : info.sizeLabel || ""
    HoverHandler { id: attachmentHover }
    ToolTip.visible: attachmentHover.hovered && !compact
    ToolTip.text: path

    Rectangle {
        anchors.fill: parent
        visible: !attachment.compact || !attachment.showsImage
        color: attachment.compact ? "transparent" : UiTheme.surface
        border.width: attachment.compact ? 0 : 1; border.color: UiTheme.line
        radius: 6
    }
    Image {
        id: preview; objectName: attachment.objectName+"Image"
        visible: attachment.showsImage
        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
        width: attachment.compact ? Math.min(48,attachment.width) : attachment.width
        height: attachment.height
        source: attachment.info.image ? attachment.info.url : ""
        // Decode a thumbnail, including on high DPI screens, rather than the full attachment.
        sourceSize: attachment.compact ? Qt.size(96,64) : Qt.size(Math.max(1,Math.ceil(attachment.previewWidth*2)),Math.max(1,Math.ceil(attachment.previewHeight*2)))
        asynchronous: true; autoTransform: true; fillMode: Image.PreserveAspectFit
        smooth: true; mipmap: true
    }
    Label {
        anchors.centerIn: parent; visible: attachment.showsImage && !attachment.imageReady && !attachment.compact
        text: "加载中…"; color: UiTheme.muted; font.pixelSize: 12
    }
    Rectangle {
        id: fileIcon; objectName: attachment.objectName+"Icon"
        visible: !attachment.showsImage
        width: attachment.compact ? 28 : 46; height: width; radius: 5
        x: attachment.compact ? 0 : Math.max(0,attachment.width-width-14)
        anchors.verticalCenter: parent.verticalCenter
        color: attachment.iconColor
        Text {
            anchors.centerIn: parent; text: attachment.iconText; color: "#ffffff"
            font.pixelSize: text.length===1 ? (attachment.compact ? 20 : 32) : (attachment.compact ? 8 : 11)
            font.bold: true
        }
    }
    ColumnLayout {
        anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: attachment.compact ? (attachment.showsImage ? 58 : 36) : 14
        anchors.rightMargin: attachment.compact ? 0 : 74
        spacing: 8
        visible: !attachment.showsImage || attachment.compact
        Label {
            objectName: attachment.objectName+"Name"; Layout.fillWidth: true
            text: attachment.info.name || "附件"; textFormat: Text.PlainText; color: UiTheme.ink
            font.pixelSize: attachment.compact ? 13 : 14
            wrapMode: attachment.compact ? Text.NoWrap : Text.WrapAnywhere
            maximumLineCount: attachment.compact ? 1 : 2; elide: Text.ElideRight
        }
        Label {
            objectName: attachment.objectName+"Size"; visible: !attachment.compact
            Layout.fillWidth: true; font.pixelSize: 12
            text: !attachment.info.available ? "文件已失效" : attachment.info.image && preview.status===Image.Error ? "图片无法预览 · "+attachment.info.sizeLabel : attachment.info.sizeLabel || ""
            color: attachment.info.available ? UiTheme.muted : UiTheme.warning
            elide: Text.ElideRight
        }
    }
}
