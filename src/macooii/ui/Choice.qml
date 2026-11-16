import QtQuick
import QtQuick.Controls
import "."
ComboBox {
    id: control
    implicitHeight: 42
    font.pixelSize: 13
    palette.text: Theme.text
    palette.buttonText: Theme.text
    palette.button: Theme.raised
    palette.base: Theme.panel
    palette.window: Theme.panel
    palette.highlight: Theme.accentDim
    palette.highlightedText: Theme.accent
    contentItem: Text { text: control.displayText; color: Theme.text; verticalAlignment: Text.AlignVCenter; leftPadding: 13; rightPadding: 30; elide: Text.ElideRight; font: control.font }
    background: Rectangle { radius: 8; color: Theme.background; border.color: control.activeFocus ? Theme.accent : Theme.border }
    delegate: ItemDelegate { width: control.width; text: modelData; highlighted: control.highlightedIndex === index
        contentItem: Text { text: modelData; color: highlighted ? Theme.accent : Theme.text; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: highlighted ? Theme.accentDim : Theme.panel }
    }
}
