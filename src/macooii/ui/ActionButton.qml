import QtQuick
import QtQuick.Controls
import "."
Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool destructive: false
    implicitHeight: 40
    implicitWidth: Math.max(72, label.implicitWidth + 28)
    padding: 14
    hoverEnabled: true
    font.family: "Figtree"
    contentItem: Text {
        id: label
        text: control.text
        font.pixelSize: 13
        font.weight: control.primary ? Font.DemiBold : Font.Medium
        color: !control.enabled ? Theme.faint : control.destructive ? Theme.danger : control.primary ? "#0b2923" : Theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 9
        opacity: control.enabled ? 1 : 0.5
        color: control.primary ? (control.hovered ? "#7bf1d7" : Theme.accent) : control.quiet ?
               (control.hovered ? Theme.raised : "transparent") : (control.hovered ? "#213342" : Theme.raised)
        border.width: control.primary || control.quiet ? 0 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.border
    }
}
