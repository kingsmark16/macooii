import QtQuick
import "."
Item {
    id: orb
    property bool active: false
    implicitWidth: 140
    implicitHeight: 140
    Rectangle { anchors.fill: parent; anchors.margins: 4; radius: width / 2; color: "#102824"; opacity: 0.45 }
    Rectangle { anchors.fill: parent; anchors.margins: 18; radius: width / 2; color: "transparent"; border.color: "#225950"; border.width: 1 }
    Rectangle { anchors.fill: parent; anchors.margins: 31; radius: width / 2; color: "#122e2b"; border.color: "#3aa78f"; border.width: 1 }
    Rectangle { anchors.centerIn: parent; width: 37; height: 37; radius: 19; color: Theme.accent; opacity: orb.active ? 1 : 0.85 }
    Rectangle { anchors.centerIn: parent; width: 13; height: 13; radius: 7; color: "#dcfff6" }
    Repeater {
        model: 4
        Item {
            required property int index
            anchors.fill: parent
            rotation: index * 90 + 45
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: 13; width: 3; height: 12; radius: 2; color: Theme.accent }
        }
    }
}
