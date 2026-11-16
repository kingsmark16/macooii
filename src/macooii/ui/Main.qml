import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "."

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    width: Math.max(minimumWidth, Math.min(1500, Screen.desktopAvailableWidth))
    height: Math.max(minimumHeight, Math.min(900, Screen.desktopAvailableHeight - 48))
    minimumWidth: 1000
    minimumHeight: 700
    visible: true
    title: "MACOOII — AI Personal Assistant"
    color: Theme.background
    property int currentPage: 0
    property bool trayAvailable: false
    readonly property bool compact: width < 1250
    onClosing: function(close) {
        if (trayAvailable) { close.accepted = false; window.hide() }
    }
    NeonBackdrop { anchors.fill: parent }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: window.compact ? 104 : 146
            Layout.fillHeight: true
            color: "#90060d24"
            Rectangle { width: 1; height: parent.height; anchors.right: parent.right; color: "#2d4169" }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 8
                Item { Layout.fillWidth: true; Layout.preferredHeight: 140
                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: 24; width: 47; height: 47; radius: 24; color: "#09112f"; border.width: 2; border.color: Theme.magenta
                        Rectangle { anchors.centerIn: parent; width: 38; height: 42; radius: 21; color: "transparent"; border.width: 2; border.color: Theme.accent; rotation: -30 }
                        Rectangle { x: 9; y: 39; width: 28; height: 2; radius: 1; color: "#b7fbff" }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 88; text: "MACOOII"; color: Theme.text; font.pixelSize: 14; font.letterSpacing: 3 }
                }
                Repeater {
                    model: ["Voice", "Notes", "Memory", "Activity", "Settings"]
                    delegate: Item {
                        required property string modelData
                        required property int index
                        Layout.fillWidth: true; Layout.preferredHeight: 60
                        Layout.topMargin: index === 4 ? 20 : 0
                        Rectangle { visible: index === 4; y: -12; x: 10; width: parent.width-20; height: 1; color: "#395375" }
                        Rectangle {
                            anchors.fill: parent; anchors.margins: 1; radius: 12
                            visible: window.currentPage === index || navMouse.containsMouse
                            border.color: window.currentPage === index ? Theme.accent : "#355a80"
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: window.currentPage === index ? "#0a7883" : "#112447" }
                                GradientStop { position: 0.5; color: "#132343" }
                                GradientStop { position: 1; color: window.currentPage === index ? "#56168b" : "#192144" }
                            }
                            Rectangle { visible: window.currentPage === index; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width-18; height: 2; color: Theme.magenta }
                        }
                        Row { anchors.centerIn: parent; spacing: window.compact ? 9 : 14
                            RailIcon { kind: modelData; width: window.compact ? 20 : 25; height: width; tint: window.currentPage === index ? Theme.accent : index === 3 ? "#ed8cfa" : "#c5d8f4" }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData; color: Theme.text; font.pixelSize: window.compact ? 11 : 13; font.weight: Font.Medium }
                        }
                        MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.currentPage = index }
                        activeFocusOnTab: true
                        Keys.onReturnPressed: window.currentPage = index
                        Keys.onSpacePressed: window.currentPage = index
                        Accessible.role: Accessible.Button; Accessible.name: modelData
                        Accessible.onPressAction: window.currentPage = index
                        Rectangle { anchors.fill: parent; radius: 12; color: "transparent"; border.color: Theme.accent; visible: parent.activeFocus }
                    }
                }
                Item { Layout.fillHeight: true }
                Text { Layout.alignment: Qt.AlignHCenter; text: "v0.8.0"; color: Theme.faint; font.pixelSize: 10; font.letterSpacing: 1 }
                Rectangle { Layout.alignment: Qt.AlignHCenter; Layout.bottomMargin: 26; width: 58; height: 22; radius: 5; color: "#10213e"; border.color: "#5873ba"
                    Text { anchors.centerIn: parent; text: "DESKTOP"; color: Theme.accent; font.pixelSize: 8; font.letterSpacing: 0.6 }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 86; color: "#64070d25"
                Rectangle { height: 1; width: parent.width; anchors.bottom: parent.bottom; color: "#263d68" }
                RowLayout { anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 24; spacing: 22
                    Text { text: "MACOOII"; color: Theme.text; font.pixelSize: window.compact ? 22 : 27; font.weight: Font.Light; font.letterSpacing: 9 }
                    Rectangle { width: 2; height: 30; color: Theme.accent
                        Rectangle { anchors.fill: parent; anchors.margins: -4; color: "#30613aff" }
                    }
                    Column { spacing: 7
                        Text { text: ["AI PERSONAL ASSISTANT", "YOUR NOTES", "EXPLICIT MEMORY", "ACTIVITY LOG", "PREFERENCES"][window.currentPage]; color: Theme.text; font.pixelSize: 12; font.letterSpacing: 2.3 }
                        Text { text: "YOUR INTELLIGENT OPERATING SYSTEM"; color: Theme.muted; font.pixelSize: 8; font.letterSpacing: 2; visible: !window.compact }
                    }
                    Item { Layout.fillWidth: true }
                    Rectangle { Layout.preferredWidth: 94; Layout.preferredHeight: 30; radius: 15; color: "#071b35"; border.color: "#3c6389"
                        Row { anchors.centerIn: parent; spacing: 8
                            Rectangle { width: 7; height: 7; radius: 4; color: backend.busy ? Theme.magenta : Theme.success; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: backend.busy ? "WORKING" : "READY"; color: Theme.text; font.pixelSize: 9; font.letterSpacing: 0.7 }
                        }
                    }
                    HudButton { text: backend.settings.provider === "codex" ? "CODEX MODE  ⌄" : backend.settings.provider === "local" ? "LOCAL AI  ⌄" : "HYBRID AI  ⌄"; implicitHeight: 30; onClicked: window.currentPage = 4 }
                }
            }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: window.currentPage
                ChatPage { onSettingsRequested: window.currentPage = 4; onPageRequested: function(index) { window.currentPage = index } }
                NotesPage {}
                MemoryPage {}
                ActivityPage {}
                SettingsPage {}
            }
        }
    }

    Rectangle {
        id: toastBox
        z: 20
        visible: false
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        width: Math.min(parent.width - 80, toastLabel.implicitWidth + 40)
        height: toastLabel.implicitHeight + 28
        radius: 10
        color: "#263e42"
        border.color: "#47766d"
        Text { id: toastLabel; anchors.fill: parent; anchors.margins: 14; color: Theme.text; font.pixelSize: 13; wrapMode: Text.Wrap }
        Timer { id: toastTimer; interval: 6000; onTriggered: toastBox.visible = false }
    }
    Connections { target: backend; function onToast(message) { toastLabel.text = message; toastBox.visible = true; toastTimer.restart() } }

    Connections { target: backend; function onBrowserCaptureChanged() {
        if (Object.keys(backend.browserCapture).length) window.currentPage = 0
    } function onMicrophoneTestRequested() { window.currentPage = 0 } }
    Rectangle {
        z: 29; anchors.fill: parent; color: "#bb05090d"
        visible: Object.keys(backend.browserCapture).length > 0
        MouseArea { anchors.fill: parent }
        Rectangle {
            width: Math.min(800, parent.width - 80); height: Math.min(700, parent.height - 60); anchors.centerIn: parent
            color: Theme.panel; border.color: Theme.border; radius: 18
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 28; spacing: 14
                Text { text: "Review your Facebook capture"; color: Theme.text; font.pixelSize: 23; font.weight: Font.DemiBold }
                Text { Layout.fillWidth: true; text: backend.browserCapture.title || ""; textFormat: Text.PlainText; color: Theme.accent; wrapMode: Text.Wrap; font.pixelSize: 14 }
                Text { Layout.fillWidth: true; text: backend.browserCapture.url || ""; textFormat: Text.PlainText; color: Theme.muted; wrapMode: Text.Wrap; font.pixelSize: 12 }
                Text { Layout.fillWidth: true; text: "This text is local. Summarize uses your selected AI mode and asks before sharing private text with a cloud service. Only loaded page text is included." + (backend.browserCapture.selection ? " You selected this excerpt." : "") + (backend.browserCapture.truncated ? " The capture was truncated." : ""); color: Theme.muted; font.pixelSize: 13; wrapMode: Text.Wrap }
                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    TextArea { text: backend.browserCapture.text || ""; readOnly: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; selectByMouse: true; color: Theme.text; font.pixelSize: 12; padding: 14; background: Rectangle { color: Theme.background; radius: 8 } }
                }
                RowLayout { Layout.fillWidth: true
                    ActionButton { text: "Dismiss and discard"; onClicked: backend.dismissBrowserCapture() }
                    Item { Layout.fillWidth: true }
                    ActionButton { text: "Summarize this capture"; primary: true; onClicked: backend.summarizeBrowserCapture() }
                }
            }
        }
    }

    Rectangle {
        z: 30
        anchors.fill: parent
        visible: Object.keys(backend.pendingApproval).length > 0
        color: "#bb05090d"
        MouseArea { anchors.fill: parent }
        Rectangle {
            width: Math.min(760, parent.width - 80); height: Math.min(660, parent.height - 80); anchors.centerIn: parent
            color: Theme.panel; border.color: Theme.border; radius: 18
            ColumnLayout { anchors.fill: parent; anchors.margins: 28; spacing: 16
                Text { text: "You decide what leaves your PC"; color: Theme.text; font.pixelSize: 23; font.weight: Font.DemiBold }
                Text { Layout.fillWidth: true; text: "Share this exact context with " + (backend.pendingApproval.provider || "an external service") + " for this task? " + (backend.pendingApproval.provider === "Google Gemini" ? "Free-tier Gemini content may be used to improve Google’s products. This also covers cloud speech based on this information." : "The request will leave this computer and follow that service’s data-use terms."); color: Theme.muted; font.pixelSize: 13; wrapMode: Text.Wrap; lineHeight: 1.3 }
                Text { text: backend.pendingApproval.label || ""; color: Theme.accent; font.pixelSize: 13; font.weight: Font.DemiBold }
                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    TextArea { text: backend.pendingApproval.text || ""; readOnly: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.pixelSize: 12; selectByMouse: true; padding: 14; background: Rectangle { color: Theme.background; radius: 8 } }
                }
                RowLayout { Layout.fillWidth: true
                    ActionButton { text: "Decline sharing"; onClicked: backend.resolveApproval("decline") }
                    ActionButton { text: "Use local AI"; visible: !!backend.pendingApproval.allowLocal; onClicked: backend.resolveApproval("local") }
                    Item { Layout.fillWidth: true }
                    ActionButton { text: "Approve for this task"; primary: true; onClicked: backend.resolveApproval("approve") }
                }
            }
        }
    }
}
