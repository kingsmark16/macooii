import numpy as np
from PySide6.QtCore import QByteArray, QObject, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat, QMediaPlayer
from PySide6.QtQml import QQmlApplicationEngine

from macooii.bridge import Bridge
from macooii.config import resource_path


def test_visual_level_uses_actual_pcm_and_resets_when_speech_stops(qapp, store):
    bridge = Bridge(store)
    format = QAudioFormat()
    format.setChannelCount(1)
    format.setSampleRate(24000)
    format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    pcm = (np.sin(np.arange(1024) * 0.2) * 12000).astype("<i2").tobytes()
    bridge._voice_buffer(QAudioBuffer(QByteArray(pcm), format))
    assert 0 < bridge.voiceLevel <= 1
    bridge._voice_state(QMediaPlayer.PlaybackState.StoppedState)
    assert bridge.voiceLevel == 0
    assert not bridge.speaking
    bridge.shutdown()


def test_history_is_secondary_and_recent_response_remains_readable(qapp, qtbot, store):
    store.add_message("assistant", "Old saved response")
    bridge = Bridge(store)
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    qapp.setFont(QFont("Figtree"))
    qml = QQmlApplicationEngine()
    warnings = []
    qml.warnings.connect(lambda values: warnings.extend(str(value) for value in values))
    qml.rootContext().setContextProperty("backend", bridge)
    qml.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
    window = qml.rootObjects()[0]
    page = window.findChild(QObject, "assistantPage")
    assert not page.property("historyOpen")
    assert page.property("currentReply") == ""
    bridge._recording = True
    bridge.recorder.level = 1.0
    bridge.stateChanged.emit()
    bridge.microphoneLevelChanged.emit()
    assert page.property("signalColor").name() == "#ff9e93"
    bridge._recording = False
    bridge.stateChanged.emit()
    store.add_message("user", "Public test request")
    store.add_message("assistant", "New complete answer")
    bridge.messagesChanged.emit()
    assert page.property("currentReply") == "New complete answer"
    page.setProperty("historyOpen", True)
    qtbot.wait(300)
    assert page.property("historyOpen")
    bridge._pending_approval = {"label": "QA approval", "provider": "OpenAI Codex", "text": "Public test payload"}
    bridge.approvalChanged.emit()
    assert not page.property("historyOpen")
    assert not warnings
    window.setVisible(False)
    bridge.shutdown()
    qml.deleteLater()
