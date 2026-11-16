import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    signal pageRequested(int index)
    signal commandRequested(string command)
    spacing: 20
    readonly property var recent: {
        let rows=[];
        for (let note of backend.notes.slice(0,4)) rows.push({title:"Note saved", detail:note.title, date:note.updated, icon:"Notes", page:1});
        for (let memory of backend.memories.slice(0,4)) rows.push({title:"Memory updated", detail:memory.body, date:memory.created, icon:"Memory", page:2});
        for (let action of backend.activity.slice(0,4)) rows.push({title:action.action.replace(/_/g," "), detail:action.status, date:action.created, icon:"Activity", page:3});
        rows.sort((a,b)=>new Date(b.date)-new Date(a.date));
        return rows.slice(0,4);
    }
    NeonPanel {
        Layout.fillWidth: true; Layout.preferredHeight: 300
        title: root.width < 240 ? "ACTIVITY" : "RECENT ACTIVITY"; icon: "Clock"; action: "View all ↗"
        onActionClicked: root.pageRequested(3)
        Column {
            anchors.fill: parent
            Repeater {
                model: root.recent
                delegate: Item {
                    required property var modelData
                    required property int index
                    width: parent.width; height: 57
                    Rectangle { x:0; y:7; width:35; height:35; radius:10; color: index%2 ? "#421453" : "#075064"
                        RailIcon { anchors.centerIn: parent; kind:modelData.icon; tint:index%2 ? "#f7a1ff" : Theme.accent; width:21; height:21 }
                    }
                    Column { x:46; y:7; width:parent.width-46; spacing:5
                        Text { width:parent.width; text:modelData.title; color:Theme.text; font.pixelSize:12; font.weight:Font.Medium; elide:Text.ElideRight; textFormat:Text.PlainText }
                        Text { width:parent.width; text:modelData.detail; color:Theme.muted; font.pixelSize:10; elide:Text.ElideRight; textFormat:Text.PlainText }
                    }
                    Rectangle { y:height-1; width:parent.width; height:1; color:"#274263"; visible:index<root.recent.length-1 }
                    MouseArea { anchors.fill:parent; cursorShape:Qt.PointingHandCursor; onClicked:root.pageRequested(modelData.page) }
                    Accessible.role: Accessible.Button; Accessible.name: modelData.title + ": " + modelData.detail
                    Accessible.onPressAction: root.pageRequested(modelData.page)
                    activeFocusOnTab: true
                    Keys.onReturnPressed: root.pageRequested(modelData.page)
                    Rectangle { anchors.fill:parent; color:"transparent"; border.color:Theme.accent; radius:6; visible:parent.activeFocus }
                }
            }
        }
        Column { anchors.centerIn:parent; width:parent.width-12; spacing:14; visible:root.recent.length===0
            RailIcon { anchors.horizontalCenter:parent.horizontalCenter; kind:"Clock"; width:32; height:32; tint:Theme.faint }
            Text { width:parent.width; text:"A fresh start."; color:Theme.text; font.pixelSize:14; horizontalAlignment:Text.AlignHCenter }
            Text { width:parent.width; text:"Your notes, memories, and completed actions will appear here."; color:Theme.muted; font.pixelSize:11; horizontalAlignment:Text.AlignHCenter; wrapMode:Text.Wrap; lineHeight:1.4 }
        }
    }
    NeonPanel {
        Layout.fillWidth:true; Layout.preferredHeight:246
        title:"QUICK COMMANDS"; icon:"Bolt"
        ColumnLayout { anchors.fill:parent; spacing:7
            Repeater {
                model: ["Summarize my notes", "Find a file or document", "Find something in memory", "Research a topic"]
                delegate: HudButton {
                    required property string modelData
                    required property int index
                    Layout.fillWidth:true; Layout.fillHeight:true
                    text:modelData; objectName:"quickCommand"+index
                    contentItem: RowLayout {
                        Text { Layout.fillWidth:true; text:modelData; color:Theme.text; font.pixelSize:11; elide:Text.ElideRight }
                        Text { text:"›"; color:index%2 ? Theme.magenta : Theme.accent; font.pixelSize:24; font.weight:Font.Light }
                    }
                    onClicked: root.commandRequested(["Summarize my notes", "/find ", "Find something in my saved memory about ", "Research "][index])
                }
            }
        }
    }
    Item { Layout.fillHeight:true }
}
