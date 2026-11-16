import threading
from types import SimpleNamespace

import numpy as np

from macooii.bridge import Bridge
from macooii.engine import Outcome
from macooii.privacy import Cancelled, TaskContext


def test_conversation_sends_transcript_after_recording_job_finishes(qapp, qtbot, store, monkeypatch):
    store.set_setting("voice_conversation", True)
    store.set_setting("speech_enabled", False)
    bridge = Bridge(store)
    bridge._recording = True
    monkeypatch.setattr(bridge.recorder, "stop", lambda: np.zeros(16000))
    monkeypatch.setattr(bridge.transcriber, "transcribe", lambda *args: "/note Voice test | Public sample")
    bridge.stopRecording()
    qtbot.waitUntil(lambda: bool(store.notes()), timeout=5000)
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    assert store.notes()[0]["body"] == "Public sample"
    bridge.shutdown()


def test_review_mode_keeps_transcript_unsent(qapp, qtbot, store, monkeypatch):
    bridge = Bridge(store)
    bridge._recording = True
    transcript = []
    bridge.transcriptReady.connect(transcript.append)
    monkeypatch.setattr(bridge.recorder, "stop", lambda: np.zeros(16000))
    monkeypatch.setattr(bridge.transcriber, "transcribe", lambda *args: "/note Unsent | Public sample")
    bridge.stopRecording()
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    assert transcript == ["/note Unsent | Public sample"]
    assert not store.notes()
    assert not store.messages()
    bridge.shutdown()


def test_interrupt_starts_microphone_only_if_button_is_still_held(qapp, qtbot, store, monkeypatch):
    store.set_setting("voice_conversation", True)
    store.set_setting("speech_enabled", False)
    bridge = Bridge(store)
    started = threading.Event()

    def run(text, task, status):
        started.set()
        while not task.cancelled.wait(0.01):
            pass
        task.check()

    bridge.engine = SimpleNamespace(run=run)
    monkeypatch.setattr(bridge.transcriber, "ready", lambda: True)
    mic = []
    monkeypatch.setattr(bridge.recorder, "start", lambda device: mic.append(device))
    monkeypatch.setattr(bridge.recorder, "stop", lambda: np.zeros(0))
    bridge.send("Public test")
    qtbot.waitUntil(started.is_set, timeout=5000)
    bridge.startRecording()
    qtbot.waitUntil(lambda: bridge.recording, timeout=5000)
    assert mic == [""]
    bridge.shutdown()


def test_releasing_interrupt_before_old_job_finishes_does_not_open_microphone(qapp, qtbot, store, monkeypatch):
    store.set_setting("voice_conversation", True)
    bridge = Bridge(store)
    started, finish = threading.Event(), threading.Event()

    def run(text, task, status):
        started.set()
        finish.wait(2)
        task.check()
        return Outcome("unused")

    bridge.engine = SimpleNamespace(run=run)
    monkeypatch.setattr(bridge.recorder, "start", lambda *args: (_ for _ in ()).throw(AssertionError("Unexpected recording")))
    bridge.send("Public test")
    qtbot.waitUntil(started.is_set, timeout=5000)
    bridge.startRecording()
    bridge.stopRecording()
    finish.set()
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    qtbot.wait(50)
    assert not bridge.recording
    bridge.shutdown()


def test_cancelled_neural_generation_cannot_fall_back_to_spoken_audio(qapp, store, monkeypatch):
    bridge = Bridge(store)
    monkeypatch.setattr(bridge.neural, "ready", lambda: True)
    monkeypatch.setattr(bridge.neural, "speak", lambda *args: (_ for _ in ()).throw(Cancelled()))
    monkeypatch.setattr("macooii.bridge.windows_speech", lambda *args: (_ for _ in ()).throw(AssertionError("Spoke after cancel")))
    import pytest
    with pytest.raises(Cancelled):
        bridge._local_voice("Public text", TaskContext(lambda *args: "decline"), store.root / "unused.wav",
                            SimpleNamespace(progress=SimpleNamespace(emit=lambda text: None)))
    bridge.shutdown()
