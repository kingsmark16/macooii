import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    objectName: "dashboardRight"
    signal pageRequested(int index)
    property string latestRequest: ""
    spacing:16
    readonly property var dailyActivity: {
        let counts=[0,0,0,0,0,0,0], today=new Date(); today.setHours(0,0,0,0);
        for(let row of backend.activity) {
            let date=new Date(row.created); date.setHours(0,0,0,0);
            let ago=Math.round((today-date)/86400000);
            if(ago>=0&&ago<7)counts[6-ago]++;
        }
        return counts;
    }
    NeonPanel {
        Layout.fillWidth:true; Layout.preferredHeight:183
        title:"ASSISTANT STATUS"; icon:"Activity"
        RowLayout { anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top; spacing:4
            Repeater {
                model: [
                    {name:"Voice",icon:"Voice",value:backend.recording?"Listening":backend.speaking?"Speaking":backend.settings.speech_enabled?"Enabled":"Muted",tint:"#39eeff"},
                    {name:"Memory",icon:"Memory",value:backend.memories.length+" saved",tint:"#cb65ff"},
                    {name:"Intelligence",icon:"Bolt",value:backend.busy?"Working":"Standby",tint:"#f052ff"},
                    {name:"Context",icon:"Notes",value:"Local",tint:"#31eee4"}
                ]
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth:true; spacing:7
                    Rectangle { Layout.alignment:Qt.AlignHCenter; width:46; height:46; radius:23; color:"#07162f"; border.color:modelData.tint; border.width:2
                        Rectangle { anchors.fill:parent; anchors.margins:-4; radius:28; color:"transparent"; border.width:3; border.color:modelData.tint; opacity:0.12 }
                        RailIcon { anchors.centerIn:parent; kind:modelData.icon; tint:modelData.tint; width:23; height:23 }
                    }
                    Text { Layout.alignment:Qt.AlignHCenter; text:modelData.name; color:Theme.text; font.pixelSize:10 }
                    Text { Layout.alignment:Qt.AlignHCenter; text:modelData.value; color:Theme.success; font.pixelSize:9 }
                }
            }
        }
        Text { anchors.bottom:parent.bottom; anchors.horizontalCenter:parent.horizontalCenter; text:backend.speechReady?"●  Local transcription ready":"○  Speech model setup needed"; color:backend.speechReady?Theme.success:Theme.muted; font.pixelSize:9 }
    }
    NeonPanel {
        Layout.fillWidth:true; Layout.preferredHeight:222
        title:"CONTEXT"; icon:"Memory"; action:"Edit ↗"
        onActionClicked:root.pageRequested(2)
        ColumnLayout { anchors.fill:parent; spacing:5
            Repeater {
                model: [
                    {title:"Workspace",detail:backend.notes.length+" notes · "+backend.memories.length+" saved preferences",icon:"Notes",page:1},
                    {title:"Focus",detail:root.latestRequest||"Ready for your next command",icon:"Focus",page:0},
                    {title:"Active work",detail:backend.notes.length?backend.notes[0].title:"No notes yet — create your first",icon:"Notes",page:1}
                ]
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    Layout.fillWidth:true; Layout.fillHeight:true; radius:10; color:"#691b3154"; border.color:"#233c62"
                    Rectangle { x:7; anchors.verticalCenter:parent.verticalCenter; width:31; height:31; radius:8; color:index===1?"#581966":index===0?"#123d83":"#075266"
                        RailIcon { anchors.centerIn:parent; kind:modelData.icon; width:20; height:20; tint:index===1?"#f7a1ff":Theme.accent }
                    }
                    Column { x:48; anchors.verticalCenter:parent.verticalCenter; width:parent.width-56; spacing:3
                        Text { text:modelData.title; color:Theme.text; font.pixelSize:11; font.weight:Font.Medium }
                        Text { width:parent.width; text:modelData.detail; textFormat:Text.PlainText; color:Theme.muted; font.pixelSize:10; elide:Text.ElideRight }
                    }
                    MouseArea { anchors.fill:parent; cursorShape:Qt.PointingHandCursor; onClicked:root.pageRequested(modelData.page) }
                    Accessible.role:Accessible.Button; Accessible.name:modelData.title+": "+modelData.detail
                    Accessible.onPressAction:root.pageRequested(modelData.page)
                    activeFocusOnTab:true
                    Keys.onReturnPressed:root.pageRequested(modelData.page)
                    border.width:activeFocus?2:1
                }
            }
        }
    }
    NeonPanel {
        Layout.fillWidth:true; Layout.preferredHeight:200
        title:"SYSTEM INSIGHTS"; icon:"Chart"
        RowLayout { anchors.fill:parent; spacing:14
            ColumnLayout { Layout.fillWidth:true; Layout.fillHeight:true; spacing:8
                Text { text:"ACTIVITY · LAST 7 DAYS"; color:Theme.faint; font.pixelSize:7; font.letterSpacing:0.6 }
                RowLayout { id: chart; Layout.fillWidth:true; Layout.fillHeight:true; spacing:5
                    Repeater { model:root.dailyActivity
                        delegate: Rectangle {
                            required property int modelData
                            required property int index
                            Layout.fillWidth:true; Layout.alignment:Qt.AlignBottom
                            objectName:"activityBar"+index
                            Layout.minimumHeight:2
                            Layout.preferredHeight:Math.max(2, 65*modelData/Math.max(1,...root.dailyActivity))
                            Layout.maximumHeight:Layout.preferredHeight
                            radius:1
                            gradient:Gradient { GradientStop { position:0; color:index<3?Theme.accent:Theme.magenta } GradientStop { position:1; color:"#17294b" } }
                            ToolTip.visible:barMouse.containsMouse; ToolTip.text:modelData+" logged actions"
                            MouseArea { id:barMouse; anchors.fill:parent; hoverEnabled:true }
                        }
                    }
                }
                Text { text:root.dailyActivity.some(n=>n>0)?"Based on local activity":"No activity recorded yet"; color:Theme.faint; font.pixelSize:8 }
            }
            Rectangle { Layout.fillHeight:true; width:1; color:"#2c4268" }
            ColumnLayout { Layout.preferredWidth:128; spacing:5
                Repeater {
                    model:[{label:"Chat turns",count:backend.messages.filter(m=>m.role==="user").length},{label:"Notes",count:backend.notes.length},{label:"Memories",count:backend.memories.length},{label:"Logged actions",count:backend.activity.length}]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth:true; spacing:10
                        Text { Layout.preferredWidth:27; text:modelData.count; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                        Text { text:modelData.label; color:Theme.muted; font.pixelSize:10 }
                    }
                }
                Text { text:"CURRENT LOCAL RECORDS"; color:Theme.faint; font.pixelSize:6; font.letterSpacing:0.6; Layout.topMargin:4 }
            }
        }
    }
    Item { Layout.fillHeight:true }
}
