import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    property string editingId: ""
    ColumnLayout { anchors.fill: parent; anchors.margins: 32; spacing: 18
        Text { text: "A memory you control."; font.pixelSize: 27; color: Theme.text; font.weight: Font.DemiBold }
        Text { Layout.fillWidth: true; text: "Macooii remembers only what you explicitly save. These preferences stay on this computer; using them with cloud AI requires approval for that task."; color: Theme.muted; font.pixelSize: 13; wrapMode: Text.Wrap; lineHeight: 1.4 }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 122; radius: 12; color: Theme.panel; border.color: Theme.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 12
                Field { id: memoryField; objectName: "memoryField"; Layout.fillWidth: true; placeholderText: "For example: I prefer concise explanations in Taglish"; maximumLength: 2000 }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Or say: “Macooii, remember that…”"; color: Theme.faint; font.pixelSize: 11; Layout.fillWidth: true }
                    ActionButton { text: page.editingId ? "Update preference" : "Remember this"; primary: true; enabled: memoryField.text.trim().length > 0; onClicked: { backend.saveMemory(memoryField.text, page.editingId); memoryField.clear(); page.editingId = "" } }
                }
            }
        }
        ListView { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12; clip: true; model: backend.memories
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width; height: Math.max(90, body.implicitHeight + 38); radius: 12; color: Theme.panel; border.color: Theme.border
                RowLayout { anchors.fill: parent; anchors.margins: 18; spacing: 16
                    Text { text: "◇"; color: Theme.accent; font.pixelSize: 25 }
                    ColumnLayout { Layout.fillWidth: true; spacing: 8
                        Text { id: body; text: modelData.body; color: Theme.text; font.pixelSize: 14; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Text { text: "EXPLICITLY SAVED  ·  " + modelData.created.substring(0, 10); color: Theme.faint; font.pixelSize: 9; font.letterSpacing: 0.7 }
                    }
                    ActionButton { text: "Edit"; quiet: true; onClicked: { page.editingId = modelData.id; memoryField.text = modelData.body; memoryField.forceActiveFocus() } }
                    ActionButton { text: "Forget"; quiet: true; destructive: true; onClicked: backend.deleteMemory(modelData.id) }
                }
            }
            Text { anchors.centerIn: parent; visible: backend.memories.length === 0; text: "Nothing remembered yet. You set the pace."; color: Theme.faint; font.pixelSize: 14 }
        }
    }
}
