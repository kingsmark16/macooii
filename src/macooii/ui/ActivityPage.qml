import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    ColumnLayout { anchors.fill: parent; anchors.margins: 32; spacing: 18
        Text { text: "Actions, without the mystery."; color: Theme.text; font.pixelSize: 27; font.weight: Font.DemiBold }
        Text { Layout.fillWidth: true; text: "A local record of tools used and their outcomes. File contents, tool arguments, and credentials are excluded from this log. Records expire after 30 days."; color: Theme.muted; font.pixelSize: 13; wrapMode: Text.Wrap; lineHeight: 1.4 }
        ListView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 8; model: backend.activity
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width; height: 65; radius: 10; color: Theme.panel
                RowLayout { anchors.fill: parent; anchors.margins: 16; spacing: 14
                    Rectangle { width: 7; height: 7; radius: 4; color: modelData.status === "completed" ? Theme.accent : Theme.danger }
                    Text { text: modelData.action.replace(/_/g, " "); color: Theme.text; font.pixelSize: 14; Layout.fillWidth: true }
                    Text { text: modelData.status; color: modelData.status === "completed" ? Theme.accent : Theme.danger; font.pixelSize: 11 }
                    Text { text: new Date(modelData.created).toLocaleString(Qt.locale(), "MMM d, h:mm AP"); color: Theme.faint; font.pixelSize: 11; Layout.preferredWidth: 130; horizontalAlignment: Text.AlignRight }
                }
            }
            Text { anchors.centerIn: parent; visible: backend.activity.length === 0; text: "Your completed actions will appear here."; color: Theme.faint; font.pixelSize: 14 }
        }
    }
}
