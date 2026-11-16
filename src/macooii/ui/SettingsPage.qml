import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    function load() {
        const s = backend.settings
        mode.currentIndex = ["auto", "cloud", "local", "codex"].indexOf(s.provider)
        cloudModel.currentIndex = ["gemini-3.8-flash", "gemini-3.1-flash-lite"].indexOf(s.cloud_model)
        speechLanguage.currentIndex = ["auto", "en", "tl", "taglish"].indexOf(s.language)
        recognitionModel.currentIndex = s.whisper_model === "large-v3-turbo" ? 1 : 0
        voiceChoice.currentIndex = ["Charon", "Kore", "Puck"].indexOf(s.voice)
        cloudEnabled.checked = s.cloud_enabled
        speechEnabled.checked = s.speech_enabled
        cloudSpeech.checked = s.cloud_speech
        localCompute.currentIndex = ["cpu", "auto"].indexOf(s.local_compute)
        openShortcut.currentIndex = ["Ctrl+Alt+J", "Ctrl+Alt+K", "Ctrl+Alt+L"].indexOf(s.open_shortcut)
        talkShortcut.currentIndex = ["Ctrl+Alt+Space", "Ctrl+Alt+V", "Ctrl+Alt+T"].indexOf(s.talk_shortcut)
        const inputNames = backend.microphoneChoices.map(function(device) { return device.name })
        microphoneChoice.currentIndex = Math.max(0, inputNames.indexOf(s.microphone))
        speakerChoice.currentIndex = Math.max(0, backend.speakerChoices.map(function(device) { return device.id }).indexOf(s.speaker))
        localVoiceEngine.currentIndex = s.speech_engine === "windows" ? 1 : 0
        naturalVoiceChoice.currentIndex = Math.max(0, ["bm_george","bm_lewis","am_michael","af_heart"].indexOf(s.neural_voice))
        voiceSpeed.currentIndex = Math.max(0, [0.9,1.0,1.1].indexOf(s.voice_speed))
        voiceConversation.checked = s.voice_conversation
        quickAcknowledgment.checked = s.quick_acknowledgment
    }
    Component.onCompleted: load()
    Connections { target: backend; function onSettingsChanged() { page.load() } }
    ColumnLayout {
        width: page.availableWidth - 64
        x: 32
        spacing: 19
        Item { Layout.preferredHeight: 10 }
        Text { text: "Your assistant. Your settings."; color: Theme.text; font.pixelSize: 27; font.weight: Font.DemiBold }
        Text { text: "Use your ChatGPT plan through Codex, free-tier Gemini, or local AI."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: aiColumn.implicitHeight + 40; radius: 13; color: Theme.panel; border.color: Theme.border
            ColumnLayout { id: aiColumn; anchors.fill: parent; anchors.margins: 20; spacing: 14
                Text { text: "01  /  AI CONNECTION"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.4 }
                RowLayout { Layout.fillWidth: true; spacing: 16
                    ColumnLayout { Layout.fillWidth: true; spacing: 7
                        Text { text: "AI mode"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: mode; Layout.fillWidth: true; model: ["Gemini · local fallback", "Gemini only", "Local only", "Codex · ChatGPT plan + local fallback"]; enabled: !backend.busy }
                    }
                    ColumnLayout { Layout.fillWidth: true; spacing: 7
                        visible: mode.currentIndex !== 3
                        Text { text: "Cloud model"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: cloudModel; Layout.fillWidth: true; model: ["Gemini 3.8 Flash", "Gemini 3.1 Flash-Lite"]; enabled: !backend.busy }
                    }
                }
                Text { visible: mode.currentIndex === 3; Layout.fillWidth: true; text: "Codex uses your existing ChatGPT CLI login and plan allowance. No Gemini or OpenAI API key is needed. Plan limits apply. Voice uses your selected local voice in this mode."; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                RowLayout { visible: mode.currentIndex === 3; Layout.fillWidth: true
                    Text { text: backend.codexStatus; color: Theme.accent; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ActionButton { text: "Check Codex"; enabled: !backend.busy; onClicked: backend.checkCodex() }
                }
                RowLayout { Layout.fillWidth: true
                    visible: mode.currentIndex !== 3
                    Field { id: apiKey; objectName: "apiKeyField"; Layout.fillWidth: true; placeholderText: backend.hasKey ? "API key saved securely · enter a new key to replace" : "Paste your Gemini API key"; echoMode: TextInput.Password; enabled: !backend.busy }
                    ActionButton { text: "Get a free key ↗"; onClicked: backend.openUrl("https://aistudio.google.com/apikey") }
                    ActionButton { text: "Remove key"; visible: backend.hasKey; quiet: true; destructive: true; enabled: !backend.busy; onClicked: backend.removeKey() }
                }
                Toggle { id: cloudEnabled; visible: mode.currentIndex !== 3; text: "Enable Gemini with my free-tier project"; enabled: !backend.busy }
                Text { visible: mode.currentIndex !== 3; Layout.fillWidth: true; text: "Use a project with billing disabled. Free-tier prompts may be used to improve Google’s products. Quotas and eligibility can change. Personal files, notes, and memories still require per-task approval. Macooii cannot verify your project’s billing status."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.4 }
                ActionButton { visible: mode.currentIndex !== 3; text: "Review current free-tier terms ↗"; quiet: true; implicitHeight: 28; onClicked: backend.openUrl("https://ai.google.dev/gemini-api/docs/pricing") }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: voiceColumn.implicitHeight + 40; radius: 13; color: Theme.panel; border.color: Theme.border
            ColumnLayout { id: voiceColumn; anchors.fill: parent; anchors.margins: 20; spacing: 13
                Text { text: "02  /  VOICE & LANGUAGE"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.4 }
                RowLayout { Layout.fillWidth: true; spacing: 12
                    ColumnLayout { Layout.fillWidth: true
                        Text { text: "Local voice engine"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: localVoiceEngine; Layout.fillWidth: true; model: ["Natural neural voice · local", "Windows voice · basic fallback"]; enabled: !backend.busy }
                    }
                    ColumnLayout { Layout.fillWidth: true
                        Text { text: "Natural voice"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: naturalVoiceChoice; Layout.fillWidth: true; model: ["George · British male", "Lewis · British male", "Michael · American male", "Heart · American female"]; enabled: !backend.busy }
                    }
                }
                RowLayout { Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: backend.neuralVoiceReady ? "Natural voice model ready · no speech API charges" : "Natural voice download needed · about 337 MB"; color: backend.neuralVoiceReady ? Theme.accent : Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                    ActionButton { text: backend.neuralVoiceReady ? "Verify model" : "Download natural voice"; enabled: !backend.busy; onClicked: backend.downloadNaturalVoice() }
                }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Speaking pace"; color: Theme.muted; font.pixelSize: 12 }
                    Choice { id: voiceSpeed; Layout.fillWidth: true; model: ["Relaxed · 0.9×", "Natural · 1.0×", "Brisk · 1.1×"]; enabled: !backend.busy }
                }
                Toggle { id: voiceConversation; text: "Press-to-talk conversation · release to send automatically"; enabled: !backend.busy }
                Toggle { id: quickAcknowledgment; text: "Quick spoken acknowledgment while processing"; enabled: !backend.busy }
                Text { Layout.fillWidth: true; text: "Macooii briefly says \"One moment\" while recognition and AI run. Local speech models load in the background, and longer answers play in short pieces. The full answer still depends on recognition and AI speed."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.4 }
                Text { Layout.fillWidth: true; text: "Conversation mode sends recognized speech without a transcript review. Hold the microphone again to interrupt. The microphone is active only while held. The synthetic natural voices work best in English; Taglish pronunciation can vary. Save preferences before testing a different voice."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap }
                Text { text: "Reply speakers"; color: Theme.muted; font.pixelSize: 12 }
                RowLayout { Layout.fillWidth: true
                    Choice { id: speakerChoice; Layout.fillWidth: true; model: backend.speakerChoices.map(function(device) { return device.label }); enabled: !backend.busy }
                    ActionButton { text: "Test voice"; enabled: !backend.busy; onClicked: backend.testVoice(backend.speakerChoices[speakerChoice.currentIndex].id) }
                }
                RowLayout { Layout.fillWidth: true
                    Choice { id: microphoneChoice; Layout.fillWidth: true; model: backend.microphoneChoices.map(function(device) { return device.label }); enabled: !backend.busy && !backend.recording }
                    ActionButton { text: "Refresh microphones"; enabled: !backend.busy && !backend.recording; onClicked: backend.refreshMicrophones() }
                    ActionButton { text: "Test microphone (5s)"; enabled: !backend.busy && !backend.recording && backend.speechReady; onClicked: backend.testMicrophone(backend.microphoneChoices[microphoneChoice.currentIndex].name) }
                }
                RowLayout { Layout.fillWidth: true; spacing: 16
                    ColumnLayout { Layout.fillWidth: true; spacing: 7
                        Text { text: "Speech recognition"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: speechLanguage; Layout.fillWidth: true; model: ["Auto · detect language", "English", "Filipino", "Taglish · Filipino + English"]; enabled: !backend.busy }
                    }
                    ColumnLayout { Layout.fillWidth: true; spacing: 7
                        Text { text: "Cloud voice"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: voiceChoice; Layout.fillWidth: true; model: ["Charon · informative", "Kore · firm", "Puck · upbeat"]; enabled: !backend.busy }
                    }
                }
                Toggle { id: speechEnabled; text: "Read short replies aloud"; enabled: !backend.busy }
                Toggle { id: cloudSpeech; text: "Use bilingual cloud speech when available"; enabled: !backend.busy }
                Text { text: "Recognition model"; color: Theme.muted; font.pixelSize: 12 }
                Choice { id: recognitionModel; Layout.fillWidth: true; model: ["Small · faster · about 500 MB", "Large v3 Turbo · higher capacity · about 1.6 GB"]; enabled: !backend.busy }
                Text { Layout.fillWidth: true; text: "Speech recognition stays local. Choose Taglish for mixed Filipino and English. The larger model uses more RAM and may take longer. Save preferences before downloading a different model. Uncertain or poor-quality recordings are shown for review even in conversation mode. Prefer the Windows WASAPI entry for your microphone; the live level meter appears while recording."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.4 }
                RowLayout { Layout.fillWidth: true
                    Text { text: backend.speechReady ? "●  Selected recognition model ready" : "○  Download the selected recognition model"; color: backend.speechReady ? Theme.accent : Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                    ActionButton { text: "Storage…"; enabled: !backend.busy; onClicked: backend.chooseModelDirectory() }
                    ActionButton { text: backend.speechReady ? "Recheck / download" : "Download speech model"; enabled: !backend.busy; onClicked: backend.downloadSpeechModel() }
                }
                RowLayout { Layout.fillWidth: true; spacing: 16
                    ColumnLayout { Layout.fillWidth: true
                        Text { text: "Open Macooii"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: openShortcut; Layout.fillWidth: true; model: ["Ctrl+Alt+J", "Ctrl+Alt+K", "Ctrl+Alt+L"]; enabled: !backend.busy }
                    }
                    ColumnLayout { Layout.fillWidth: true
                        Text { text: "Hold to talk"; color: Theme.muted; font.pixelSize: 12 }
                        Choice { id: talkShortcut; Layout.fillWidth: true; model: ["Ctrl+Alt+Space", "Ctrl+Alt+V", "Ctrl+Alt+T"]; enabled: !backend.busy }
                    }
                }
            }
        }
        RowLayout { Layout.fillWidth: true
            ActionButton { text: "Save preferences"; primary: true; enabled: !backend.busy
                onClicked: {
                    backend.saveSettings(JSON.stringify({provider:["auto","cloud","local","codex"][mode.currentIndex], cloud_model:["gemini-3.8-flash","gemini-3.1-flash-lite"][cloudModel.currentIndex], language:["auto","en","tl","taglish"][speechLanguage.currentIndex], whisper_model:["small","large-v3-turbo"][recognitionModel.currentIndex], voice:["Charon","Kore","Puck"][voiceChoice.currentIndex], local_compute:["cpu","auto"][localCompute.currentIndex], microphone:backend.microphoneChoices[microphoneChoice.currentIndex].name, speaker:backend.speakerChoices[speakerChoice.currentIndex].id, speech_engine:["neural","windows"][localVoiceEngine.currentIndex], neural_voice:["bm_george","bm_lewis","am_michael","af_heart"][naturalVoiceChoice.currentIndex], voice_speed:[0.9,1.0,1.1][voiceSpeed.currentIndex], voice_conversation:voiceConversation.checked, quick_acknowledgment:quickAcknowledgment.checked, open_shortcut:openShortcut.currentText, talk_shortcut:talkShortcut.currentText, cloud_enabled:cloudEnabled.checked, speech_enabled:speechEnabled.checked, cloud_speech:cloudSpeech.checked}), apiKey.text)
                    apiKey.clear()
                }
            }
            Text { text: "Keys are stored in Windows Credential Manager."; color: Theme.faint; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: localColumn.implicitHeight + 40; radius: 13; color: Theme.panel; border.color: Theme.border
            ColumnLayout { id: localColumn; anchors.fill: parent; anchors.margins: 20; spacing: 13
                Text { text: "03  /  LOCAL AI FALLBACK"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.4 }
                Text { text: "Qwen3 4B Instruct through Ollama"; color: Theme.text; font.pixelSize: 16; font.weight: Font.Medium }
                Choice { id: localCompute; Layout.fillWidth: true; model: ["CPU · reliable fallback (default)", "Automatic GPU · requires a compatible runtime"]; enabled: !backend.busy }
                Text { Layout.fillWidth: true; text: "Install and start Ollama, then download the 2.5 GB model. The runtime needs additional storage. Downloading requires at least 8 GB free on its model drive. Performance depends on available RAM and GPU memory."; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.4 }
                RowLayout { Layout.fillWidth: true
                    Text { text: backend.localStatus; color: Theme.accent; font.pixelSize: 12; Layout.fillWidth: true }
                    ActionButton { text: "Check"; enabled: !backend.busy; onClicked: backend.refreshStatus() }
                    ActionButton { text: "Install Ollama ↗"; onClicked: backend.openUrl("https://ollama.com/download/windows") }
                    ActionButton { text: "Download local model"; enabled: !backend.busy; onClicked: backend.downloadLocalModel() }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: accessColumn.implicitHeight + 40; radius: 13; color: Theme.panel; border.color: Theme.border
            ColumnLayout { id: accessColumn; anchors.fill: parent; anchors.margins: 20; spacing: 14
                Text { text: "04  /  ACCESS YOU APPROVE"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.4 }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Approved folders"; color: Theme.text; font.pixelSize: 15; font.weight: Font.Medium; Layout.fillWidth: true }
                    ActionButton { text: "+ Add folder"; enabled: !backend.busy; onClicked: backend.addFolder() }
                }
                Text { visible: backend.settings.folders.length === 0; text: "No folders approved yet. Macooii cannot search your files."; color: Theme.faint; font.pixelSize: 12 }
                Repeater { model: backend.settings.folders
                    delegate: RowLayout { required property string modelData; Layout.fillWidth: true
                        Text { text: modelData; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideMiddle }
                        ActionButton { text: "Remove"; quiet: true; enabled: !backend.busy; onClicked: backend.removeFolder(modelData) }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                RowLayout { Layout.fillWidth: true
                    Text { text: "Registered applications"; color: Theme.text; font.pixelSize: 15; font.weight: Font.Medium; Layout.fillWidth: true }
                    ActionButton { text: "+ Add app"; enabled: !backend.busy; onClicked: backend.addApp() }
                }
                Repeater { model: Object.keys(backend.settings.apps)
                    delegate: RowLayout { required property string modelData; Layout.fillWidth: true
                        Text { text: modelData; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                        ActionButton { text: "Remove"; quiet: true; enabled: !backend.busy; onClicked: backend.removeApp(modelData) }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: dataColumn.implicitHeight + 40; radius: 13; color: Theme.panel; border.color: Theme.border
            ColumnLayout { id: dataColumn; anchors.fill: parent; anchors.margins: 20; spacing: 12
                Text { text: "05  /  LOCAL DATA"; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.4 }
                Text { text: backend.dataLocation; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
                Text { text: backend.diskStatus; color: Theme.faint; font.pixelSize: 11 }
                Text { Layout.fillWidth: true; text: "Chat and activity history expire after 30 days. Notes and explicitly saved memories stay until you delete them. Local data uses your Windows account’s file permissions; the database is not separately encrypted."; color: Theme.faint; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.4 }
                ActionButton { text: "Clear conversation history…"; destructive: true; enabled: !backend.busy; onClicked: backend.clearHistory() }
            }
        }
        Item { Layout.preferredHeight: 18 }
    }
}
