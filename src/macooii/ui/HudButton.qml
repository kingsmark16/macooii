import QtQuick
import QtQuick.Controls
import "."
Button {
    id: control
    property bool primary: false
    property bool destructive: false
    implicitHeight: 38
    implicitWidth: Math.max(82, contentItem.implicitWidth + 28)
    hoverEnabled: true
    padding: 12
    background: Rectangle {
        radius: 9
        gradient: Gradient {
            GradientStop { position: 0; color: control.down ? "#245977" : control.primary ? "#126878" : control.hovered ? "#244b70" : "#142e51" }
            GradientStop { position: 0.55; color: control.primary ? "#073446" : "#0b1937" }
            GradientStop { position: 1; color: control.primary ? "#087286" : "#29204f" }
        }
        border.color: control.destructive ? "#e88596" : control.primary || control.activeFocus ? Theme.accent : control.hovered ? Theme.magenta : "#3f6796"
        opacity: control.enabled ? 1 : 0.4
        Behavior on color { ColorAnimation { duration: 160 } }
        Behavior on border.color { ColorAnimation { duration: 160 } }
    }
    contentItem: Text {
        text: control.text; font.family: "Figtree"; font.pixelSize: 12; font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        color: !control.enabled ? Theme.faint : control.destructive ? "#f0b0a9" : Theme.text
    }
}
