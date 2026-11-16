import QtQuick
import QtQuick.Controls
import "."
TextField {
    id: control
    implicitHeight: 44
    color: Theme.text
    placeholderTextColor: Theme.faint
    selectionColor: Theme.accentDim
    selectedTextColor: Theme.text
    font.pixelSize: 14
    leftPadding: 14
    rightPadding: 14
    background: Rectangle {
        color: Theme.background
        radius: 9
        border.color: control.activeFocus ? Theme.accent : Theme.border
    }
}
