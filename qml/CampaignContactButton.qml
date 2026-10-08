import QtQuick
import QtQuick.Controls

UiButton {
    id: button
    property var opener: backend.contactOpener
    property string contactKey: ""
    property string contactPrefix: ""
    property string contactName: ""
    property bool isPlaceholder: false
    property bool fromOverview: false
    font.pixelSize: 12
    text: opener.active ? "正在打开…" : "打开企微联系人"
    enabled: !!contactKey && !!contactName && !isPlaceholder && !opener.active && !backend.groupCenter.active && !backend.workflow.sender.active
    Accessible.name: "打开" + contactName + "的企微联系人"
    onClicked: {
        if (fromOverview) opener.openOverviewContact(contactKey, contactPrefix)
        else opener.openCampaignContact(contactKey, contactPrefix)
    }
}
