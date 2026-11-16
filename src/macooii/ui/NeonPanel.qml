import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Rectangle {
    id: panel
    property string title: ""
    property string icon: "Activity"
    property string action: ""
    signal actionClicked()
    default property alias contentData: body.data
    radius: 16
    color: "#dc091a36"
    border.color: "#4773a0"
    gradient: Gradient {
        GradientStop { position: 0; color: "#ed102746" }
        GradientStop { position: 0.3; color: "#ec081831" }
        GradientStop { position: 1; color: "#e01c1945" }
    }
    Canvas {
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const c=getContext("2d"); c.reset(); c.clearRect(0,0,width,height);
            let top=c.createRadialGradient(width*0.25,0,0,width*0.25,0,90);
            top.addColorStop(0,"rgba(15,199,255,0.24)"); top.addColorStop(1,"transparent");
            c.fillStyle=top; c.fillRect(1,1,width-2,height-2);
            let bottom=c.createRadialGradient(width-35,height,0,width-35,height,90);
            bottom.addColorStop(0,"rgba(213,40,255,0.32)"); bottom.addColorStop(1,"transparent");
            c.fillStyle=bottom; c.fillRect(1,1,width-2,height-2);
        }
    }
    Rectangle {
        x: 18; y: 0; width: parent.width - 36; height: 1
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.25; color: Theme.accent }
            GradientStop { position: 0.7; color: Theme.violet }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Rectangle {
        x: 22; y: parent.height - 1; width: parent.width - 44; height: 1
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.8; color: Theme.magenta }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    RowLayout {
        x: 16; y: 12; width: parent.width - 32; height: 25; spacing: 10
        RailIcon { kind: panel.icon; tint: Theme.accent; Layout.preferredWidth: 23; Layout.preferredHeight: 23 }
        Text { Layout.fillWidth: true; text: panel.title; color: Theme.text; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1.2; elide: Text.ElideRight }
        Button {
            visible: panel.action.length > 0; text: panel.action; padding: 0; implicitHeight: 25
            background: null
            contentItem: Text { text: parent.text; color: parent.hovered ? "white" : Theme.accent; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter }
            onClicked: panel.actionClicked()
        }
    }
    Rectangle { x: 16; y: 46; width: parent.width - 32; height: 1; color: "#2b5273" }
    Item { id: body; x: 16; y: 57; width: parent.width - 32; height: parent.height - 70 }
}
