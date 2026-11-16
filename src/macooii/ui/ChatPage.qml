import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    objectName: "assistantPage"
    signal settingsRequested()
    signal pageRequested(int index)
    readonly property bool compact: width < 1120
    function prepareCommand(command) { composer.text = command; composer.forceActiveFocus() }
    property bool historyOpen: false
    property bool detailsOpen: false
    property string latestRequest: ""
    property string currentReply: ""
    readonly property string mode: Object.keys(backend.pendingApproval).length ? "approval" : backend.recording ? "listening" : backend.speaking ? "speaking" : backend.busy ? "thinking" : "idle"
    readonly property color signalColor: mode === "listening" ? (backend.microphoneClipping ? "#ff9e93" : "#39eeff") : mode === "thinking" ? "#b9b0ff" : mode === "approval" ? "#ebc68c" : "#39eeff"
    function submit() {
        if (composer.text.trim().length && !backend.busy && !backend.recording) {
            const value = composer.text; composer.clear(); backend.send(value)
        }
    }
    Connections { target: backend
        function onTranscriptReady(text) { composer.text = text; composer.forceActiveFocus() }
        function onMessagesChanged() {
            const rows = backend.messages
            if (!rows.length) { page.currentReply = ""; page.latestRequest = ""; return }
            const last = rows[rows.length-1]
            if (last.role === "user") { page.latestRequest = last.content; page.currentReply = "" }
            else page.currentReply = last.content
            scrollTimer.restart()
        }
        function onApprovalChanged() { if (Object.keys(backend.pendingApproval).length) { page.historyOpen = false; page.detailsOpen = false } }
    }
    Keys.onEscapePressed: { historyOpen = false; detailsOpen = false }
    Timer { id: scrollTimer; interval: 60; onTriggered: messages.positionViewAtEnd() }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 22; anchors.rightMargin: 20; anchors.topMargin: 26; anchors.bottomMargin: 35; spacing: 18
        DashboardLeft {
            Layout.preferredWidth: page.compact ? 215 : Math.min(295,page.width*0.225)
            Layout.minimumWidth: Layout.preferredWidth
            Layout.maximumWidth: Layout.preferredWidth
            Layout.fillHeight: true
            onPageRequested: function(index) { page.pageRequested(index) }
            onCommandRequested: function(command) { page.prepareCommand(command) }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            Item {
                id: stage
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 160
                VoiceCore {
                    id: core
                    objectName: "voiceCore"
                    anchors.centerIn: parent
                    width: Math.min(stage.height*1.15, stage.width*1.13, 600); height: width
                    mode: page.mode; tint: page.signalColor
                    level: backend.recording ? backend.microphoneLevel : backend.speaking ? backend.voiceLevel : 0
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button; Accessible.name: "Hold the voice core to speak"
                    Keys.onPressed: function(event) { if (event.key === Qt.Key_Space && !event.isAutoRepeat) { backend.startRecording(); event.accepted = true } }
                    Keys.onReleased: function(event) { if (event.key === Qt.Key_Space && !event.isAutoRepeat) { backend.stopRecording(); event.accepted = true } }
                    Rectangle { anchors.fill:parent; anchors.margins:width*0.12; radius:width/2; color:"transparent"; border.color:page.signalColor; visible:core.activeFocus }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        enabled: !backend.busy || backend.settings.voice_conversation
                        onPressed: { core.forceActiveFocus(); backend.startRecording() }
                        onReleased: backend.stopRecording()
                        onCanceled: backend.cancel()
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 7
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: "M A C O O I I"; font.pixelSize: page.compact ? 29 : 36; font.weight: Font.Light; font.letterSpacing: 7; color: "#f0f4ff" }
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: page.mode === "listening" ? "I'm listening." : page.mode === "speaking" ? "Speaking to you." : page.mode === "thinking" ? "One moment. I'm on it." : page.mode === "approval" ? "Your approval is needed." : "At your command."; color: Theme.text; font.pixelSize: 16; font.letterSpacing: 1.5 }
            }
            Item { Layout.fillWidth:true; Layout.preferredHeight:52
                Row { anchors.centerIn:parent; spacing:18
                    Row { anchors.verticalCenter:parent.verticalCenter; spacing:4
                        Repeater { model:9
                            Rectangle { required property int index; width:2; radius:1; height:3+Math.sin(index*0.9)*Math.sin(index*0.9)*(10+core.level*25); anchors.verticalCenter:parent.verticalCenter; color: index<4?Theme.magenta:Theme.accent }
                        }
                    }
                    Rectangle { width:page.compact?166:194; height:39; radius:20; border.color:page.signalColor; border.width:1.5
                        gradient:Gradient { orientation:Gradient.Horizontal
                            GradientStop { position:0; color:"#075663" } GradientStop { position:0.5; color:"#08172e" } GradientStop { position:1; color:"#66127f" }
                        }
                        Row { anchors.centerIn:parent; spacing:10
                            RailIcon { kind:"Voice"; width:19; height:19; tint:page.signalColor }
                            Text { anchors.verticalCenter:parent.verticalCenter; text:page.mode==="idle"?"STANDBY":page.mode.toUpperCase(); color:Theme.text; font.pixelSize:12; font.letterSpacing:2; font.weight:Font.DemiBold }
                        }
                    }
                    Row { anchors.verticalCenter:parent.verticalCenter; spacing:4
                        Repeater { model:9
                            Rectangle { required property int index; width:2; radius:1; height:3+Math.cos(index*0.8)*Math.cos(index*0.8)*(10+core.level*25); anchors.verticalCenter:parent.verticalCenter; color:index>4?Theme.magenta:Theme.accent }
                        }
                    }
                }
            }
            Rectangle {
                visible: page.currentReply.length>0 || page.latestRequest.length>0
                Layout.fillWidth:true; Layout.preferredHeight:66; radius:10; color:"#d70a1934"; border.color:"#35557d"
                RowLayout { anchors.fill:parent; anchors.margins:12; spacing:10
                    ColumnLayout { Layout.fillWidth:true; spacing:4
                        Text { text:page.currentReply.length?"LATEST RESPONSE":"YOUR REQUEST"; color:page.signalColor; font.pixelSize:8; font.letterSpacing:1.5 }
                        Text { Layout.fillWidth:true; text:page.currentReply||page.latestRequest; textFormat:Text.PlainText; color:Theme.muted; font.pixelSize:11; maximumLineCount:2; wrapMode:Text.Wrap; elide:Text.ElideRight }
                    }
                    HudButton { text:"Read ↗"; visible:page.currentReply.length>0; implicitWidth:65; implicitHeight:30; onClicked:page.detailsOpen=true }
                }
            }
            Flow { Layout.fillWidth:true; Layout.preferredHeight:visible?childrenRect.height:0; spacing:6; visible:backend.cards.length>0
                Repeater { model:backend.cards.slice(0,3)
                    HudButton { required property var modelData; text:modelData.name.substring(0,24)+" ↗"; enabled:!backend.busy
                        onClicked: { if(modelData.kind==="file")page.prepareCommand("Summarize file "+modelData.id);else backend.openUrl(modelData.url) }
                        ToolTip.visible:hovered; ToolTip.text:modelData.path||modelData.url||""
                    }
                }
            }
            Rectangle {
                Layout.fillWidth:true; Layout.preferredHeight:65; radius:17
                gradient:Gradient { orientation:Gradient.Horizontal
                    GradientStop { position:0; color:Theme.magenta } GradientStop { position:0.3; color:Theme.violet } GradientStop { position:0.65; color:Theme.accent } GradientStop { position:1; color:"#4477ff" }
                }
                Rectangle { anchors.fill:parent; anchors.margins:2; radius:15; color:"#091833"
                    Rectangle { anchors.fill:parent; anchors.margins:-6; radius:20; color:"transparent"; border.width:5; border.color:Theme.accent; opacity:composer.activeFocus?0.13:0.05 }
                }
                RowLayout { anchors.fill:parent; anchors.margins:11; spacing:8
                    Text { text:"✦"; color:"#f6b3ff"; font.pixelSize:25; Layout.leftMargin:5 }
                    ScrollView { Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        TextArea { id:composer; objectName:"composer"; placeholderText:backend.recording?"Listening…":"Ask MACOOII anything, or give a command…"; placeholderTextColor:Theme.muted; color:Theme.text; font.pixelSize:13; font.family:"Figtree"; wrapMode:TextEdit.Wrap; selectByMouse:true; background:null; padding:8
                            enabled:!backend.busy&&!backend.recording
                            Keys.onReturnPressed:function(event) { if(!(event.modifiers&Qt.ShiftModifier)) { event.accepted=true; page.submit() }else event.accepted=false }
                        }
                    }
                    HudButton { objectName:"sendButton"
                        readonly property bool stopAction:backend.busy||backend.recording||(backend.speaking&&!composer.text.trim().length)
                        text:stopAction?"Stop":"Send"; implicitWidth:48; implicitHeight:40; primary:true; destructive:stopAction
                        enabled:stopAction||composer.text.trim().length>0
                        onClicked:stopAction?backend.cancel():page.submit()
                        contentItem:Item {
                            RailIcon { anchors.centerIn:parent; kind:"Send"; width:22; height:22; tint:Theme.text; visible:!parent.parent.stopAction }
                            Text { anchors.centerIn:parent; text:"Stop"; color:Theme.text; font.pixelSize:11; visible:parent.parent.stopAction }
                        }
                        Accessible.name:stopAction?"Stop current action":"Send command"
                    }
                }
            }
            RowLayout { Layout.fillWidth:true; spacing:8
                HudButton { objectName:"talkButton"; Layout.fillWidth:true; implicitHeight:52; primary:true
                    text:backend.recording?"Listening…":"Hold to Talk"; enabled:!backend.busy||backend.settings.voice_conversation
                    onPressed:backend.startRecording(); onReleased:backend.stopRecording(); onCanceled:backend.cancel()
                    ToolTip.visible:hovered; ToolTip.text:backend.settings.talk_shortcut+" · hold to speak"
                }
                HudButton { objectName:"conversationButton"; Layout.fillWidth:true; implicitHeight:52
                    text:backend.settings.voice_conversation?"Conversation on":"Conversation"; enabled:!backend.recording
                    onClicked:backend.toggleVoiceConversation()
                    ToolTip.visible:hovered; ToolTip.text:"Toggle automatic voice conversation"
                }
                HudButton { Layout.fillWidth:true; implicitHeight:52; text:"Analyze"; onClicked:page.prepareCommand("Analyze a file or document ") }
                HudButton { Layout.fillWidth:true; implicitHeight:52; text:"Memory"; onClicked:page.pageRequested(2) }
                HudButton { text:"•••"; implicitWidth:36; implicitHeight:52; onClicked:moreMenu.open()
                    Menu { id:moreMenu; y:-height
                        MenuItem { text:"Conversation history"; onTriggered:page.historyOpen=true }
                        MenuItem { text:backend.settings.speech_enabled?"Mute voice output":"Enable voice output"; onTriggered:backend.toggleSpeech() }
                        MenuItem { text:"Voice settings"; onTriggered:page.settingsRequested() }
                    }
                }
            }
            RowLayout { Layout.fillWidth:true; spacing:8
                Text { Layout.fillWidth:true; text:backend.recognitionFeedback||(backend.recording?(backend.microphoneClipping?"MIC CLIPPING": "MICROPHONE ACTIVE"):backend.settings.talk_shortcut.toUpperCase()+"  ·  HOLD TO TALK"); color:backend.recognitionFeedback||backend.microphoneClipping?"#ffbda9":Theme.faint; font.pixelSize:8; elide:Text.ElideRight }
                Button { text:"History ↗"; implicitHeight:22; padding:0; background:null
                    contentItem:Text { text:parent.text; color:Theme.muted; font.pixelSize:9; verticalAlignment:Text.AlignVCenter }
                    onClicked:page.historyOpen=true
                }
            }
        }
        DashboardRight {
            Layout.preferredWidth:Math.min(330,page.width*0.255); Layout.fillHeight:true
            Layout.minimumWidth:Layout.preferredWidth
            Layout.maximumWidth:Layout.preferredWidth
            visible:!page.compact
            latestRequest:page.latestRequest
            onPageRequested:function(index) { page.pageRequested(index) }
        }
    }
    Rectangle { anchors.fill: parent; z: 8; visible: page.historyOpen || page.detailsOpen; color: "#b0050b12"
        MouseArea { anchors.fill: parent; onClicked: { page.historyOpen = false; page.detailsOpen = false } }
    }
    Rectangle {
        id: history
        z: 9; width: Math.min(530,page.width-36); height: parent.height
        x: page.width-width
        visible: page.historyOpen
        color: "#101b28"; border.color: "#2b455b"
        ColumnLayout { anchors.fill: parent; anchors.margins: 24; spacing: 16
            RowLayout { Layout.fillWidth: true
                Column { spacing: 6
                    Text { text: "Conversation history"; color: Theme.text; font.pixelSize: 20; font.weight: Font.Medium }
                    Text { text: "YOUR SAVED CONVERSATIONS"; color: Theme.faint; font.pixelSize: 8; font.letterSpacing: 1.5 }
                }
                Item { Layout.fillWidth: true }
                HudButton { text: "Close"; onClicked: page.historyOpen = false }
            }
            ListView { id: messages; objectName: "messageList"; Layout.fillWidth: true; Layout.fillHeight: true; model: backend.messages; clip: true; spacing: 15; ScrollBar.vertical: ScrollBar {}
                Text { anchors.centerIn: parent; visible: backend.messages.length === 0; text: "Your saved conversations will appear here."; color: Theme.faint; font.pixelSize: 12 }
                delegate: Rectangle { required property var modelData; width: messages.width-8; height: historyColumn.implicitHeight+28; radius: 10; color: modelData.role === "user" ? "#182b3a" : "#11202c"
                    ColumnLayout { id: historyColumn; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 8
                        Text { text: modelData.role === "user" ? "YOU" : "MACOOII"; color: modelData.role === "user" ? Theme.muted : "#8cdbed"; font.pixelSize: 9; font.letterSpacing: 1.5 }
                        TextEdit { Layout.fillWidth: true; text: modelData.content; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.family: "Figtree"; font.pixelSize: 13 }
                    }
                }
                Component.onCompleted: positionViewAtEnd()
            }
            Text { Layout.fillWidth: true; text: "History is stored locally. Retention and clearing controls are in Settings."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap }
        }
    }
    Rectangle { z: 10; anchors.centerIn: parent; width: Math.min(800,page.width-48); height: Math.min(590,page.height-48); visible: page.detailsOpen; radius: 16; color: "#101d2b"; border.color: "#375164"
        ColumnLayout { anchors.fill: parent; anchors.margins: 24; spacing: 16
            RowLayout { Layout.fillWidth: true
                Text { text: "Full response"; color: Theme.text; font.pixelSize: 20 }
                Item { Layout.fillWidth: true }
                HudButton { text: "Close"; onClicked: page.detailsOpen = false }
            }
            ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                TextArea { text: page.currentReply; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.family: "Figtree"; font.pixelSize: 14; background: null }
            }
        }
    }
}
