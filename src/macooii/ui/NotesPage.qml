import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    property string selectedId: ""
    function newNote() { selectedId = ""; titleField.text = ""; bodyField.text = ""; titleField.forceActiveFocus() }
    RowLayout { anchors.fill: parent; anchors.margins: 30; spacing: 22
        ColumnLayout { Layout.preferredWidth: 235; Layout.fillHeight: true; spacing: 13
            ActionButton { text: "+  New note"; primary: true; Layout.fillWidth: true; onClicked: page.newNote() }
            Field { id: search; placeholderText: "Filter notes…"; Layout.fillWidth: true }
            ListView { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8; clip: true; model: backend.notes
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width; height: visible ? 79 : 0
                    visible: search.text === "" || (modelData.title + " " + modelData.body).toLowerCase().indexOf(search.text.toLowerCase()) >= 0
                    radius: 10; color: page.selectedId === modelData.id ? Theme.accentDim : Theme.panel
                    Column { anchors.fill: parent; anchors.margins: 13; spacing: 8
                        Text { width: parent.width; text: modelData.title; color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.body.replace(/\n/g, " "); color: Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
                        Text { text: modelData.updated.substring(0, 10); color: Theme.faint; font.pixelSize: 9 }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { page.selectedId = modelData.id; titleField.text = modelData.title; bodyField.text = modelData.body } }
                }
            }
            Text { visible: backend.notes.length === 0; text: "Your first idea starts here."; color: Theme.faint; font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
        }
        Rectangle { Layout.fillHeight: true; width: 1; color: Theme.border }
        ColumnLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            Text { text: page.selectedId ? "Edit note" : "A fresh page"; color: Theme.text; font.pixelSize: 24; font.weight: Font.DemiBold }
            Text { text: "Saved on your computer. Shared only with your approval."; color: Theme.muted; font.pixelSize: 12 }
            Field { id: titleField; objectName: "noteTitle"; placeholderText: "Give your idea a title"; Layout.fillWidth: true; maximumLength: 160 }
            ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                TextArea { id: bodyField; objectName: "noteBody"; placeholderText: "Write something worth keeping…"; placeholderTextColor: Theme.faint; color: Theme.text; font.pixelSize: 14; wrapMode: TextEdit.Wrap; selectByMouse: true; padding: 17; background: Rectangle { color: Theme.panel; radius: 10; border.color: Theme.border } }
            }
            RowLayout { Layout.fillWidth: true
                ActionButton { text: "Save note"; primary: true; onClicked: { const id = backend.saveNote(titleField.text, bodyField.text, page.selectedId); if (id) page.selectedId = id } }
                ActionButton { text: "Export…"; enabled: page.selectedId !== ""; onClicked: backend.exportNote(page.selectedId) }
                Item { Layout.fillWidth: true }
                ActionButton { text: "Delete"; destructive: true; quiet: true; enabled: page.selectedId !== ""; onClicked: { backend.deleteNote(page.selectedId); page.newNote() } }
            }
        }
    }
}
