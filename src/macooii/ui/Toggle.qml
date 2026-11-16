import QtQuick
import QtQuick.Controls
import "."
Switch {
    id: control
    implicitHeight: 30
    spacing: 10
    indicator: Rectangle {
        implicitWidth: 36; implicitHeight: 21; x: control.leftPadding; y: parent.height / 2 - height / 2
        radius: 11; color: control.checked ? Theme.accentDim : Theme.border
        Rectangle { width: 15; height: 15; radius: 8; y: 3; x: control.checked ? 18 : 3; color: control.checked ? Theme.accent : Theme.faint }
    }
    contentItem: Text { text: control.text; color: control.enabled ? Theme.text : Theme.faint; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; leftPadding: control.indicator.width + control.spacing }
}
