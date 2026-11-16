import threading
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtMultimedia import QMediaPlayer

from macooii.bridge import Bridge
from macooii.engine import Outcome
from macooii.privacy import TaskContext
from macooii.voice_pipeline import PROMPTS, PromptCache, speech_chunks


def wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\0\0" * 2400)
    return path


def test_chunking_keeps_words_in_order_and_starts_with_short_audio():
    text = "I can help with that. " + "Here is the next part of the answer, with useful details. " * 8
    chunks = speech_chunks(text)
    assert " ".join(chunks).split() == text.split()
    assert len(chunks[0]) <= 100
    assert all(len(chunk) <= 180 for chunk in chunks)
    assert speech_chunks("") == []
    assert speech_chunks("unbroken" * 30) == ["unbroken" * 30]


def test_prompt_cache_is_restricted_to_public_phrases(tmp_path):
    cache = PromptCache(tmp_path)
    with pytest.raises(KeyError):
        cache.path("Private conversation text", "neural", "bm_george", 1.0)
    a = cache.path("receipt", "neural", "bm_george", 1.0)
    assert a != cache.path("receipt", "neural", "bm_lewis", 1.0)
    assert a != cache.path("receipt", "neural", "bm_george", 1.1)
    assert not cache.ready(a)
    wav(a)
    assert cache.ready(a)


def test_cached_receipt_plays_without_synthesis_and_only_once(qapp, store, monkeypatch):
    bridge = Bridge(store)
    monkeypatch.setattr(bridge.neural, "ready", lambda: True)
    monkeypatch.setattr(bridge, "_local_voice", lambda *a: pytest.fail("Receipt regenerated"))
    wav(bridge._prompt_path("receipt")[0])
    task = bridge._task = TaskContext(lambda *a: "decline")
    queued = []
    monkeypatch.setattr(bridge, "_queue_audio", lambda path, *args: queued.append(path))
    bridge._acknowledge(task)
    bridge._acknowledge(task)
    assert len(queued) == 1 and task.voice_acknowledged
    Path(queued[0]).unlink()
    bridge.shutdown()


@pytest.mark.parametrize("condition", ["disabled", "cancelled", "action", "approval", "stale"])
def test_receipt_is_suppressed_when_inappropriate(qapp, store, monkeypatch, condition):
    bridge = Bridge(store)
    wav(bridge._prompt_path("receipt")[0])
    task = bridge._task = TaskContext(lambda *a: "decline")
    if condition == "disabled":
        store.set_setting("quick_acknowledgment", False)
    elif condition == "cancelled":
        task.cancelled.set()
    elif condition == "action":
        task.voice_action_announced = True
    elif condition == "approval":
        bridge._pending_approval = {"text": "Review this first"}
    else:
        bridge._task = TaskContext(lambda *a: "decline")
    monkeypatch.setattr(bridge, "_queue_audio", lambda *a: pytest.fail("Unexpected receipt"))
    bridge._acknowledge(task)
    bridge.shutdown()


def test_receipt_does_not_wait_for_transcription(qapp, qtbot, store, monkeypatch):
    store.set_setting("voice_conversation", True)
    bridge = Bridge(store)
    wav(bridge._prompt_path("receipt")[0])
    release = threading.Event()
    monkeypatch.setattr(bridge.recorder, "stop", lambda: np.ones(16000))
    monkeypatch.setattr(bridge.transcriber, "transcribe", lambda *a: release.wait(2) and "")
    heard = []
    monkeypatch.setattr(bridge, "_queue_audio", lambda path, *a: heard.append(path))
    bridge._recording = True
    bridge.stopRecording()
    assert heard and bridge.busy and not release.is_set()
    release.set()
    qtbot.waitUntil(lambda: not bridge.busy)
    Path(heard[0]).unlink()
    bridge.shutdown()


def test_audio_queue_preserves_order_and_cancel_discards_remaining_chunks(qapp, qtbot, store, monkeypatch):
    bridge = Bridge(store)
    task = bridge._task = TaskContext(lambda *a: "decline")
    started = []

    def begin(path, task, completed):
        started.append(Path(path).name)
        bridge._audio_path = Path(path)
        bridge._audio_done = completed

    monkeypatch.setattr(bridge, "_begin_audio", begin)
    paths = [wav(store.root / f"chunk-{i}.wav") for i in range(3)]
    done = [threading.Event() for _ in paths]
    for path, completed in zip(paths, done, strict=True):
        bridge._queue_audio(str(path), task, completed)
    assert started == ["chunk-0.wav"]
    bridge._media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    qtbot.waitUntil(lambda: len(started) == 2)
    assert done[0].played and done[0].is_set()
    bridge.cancel()
    qtbot.waitUntil(done[1].is_set)
    assert done[2].is_set() and not getattr(done[2], "played", False)
    assert not any(path.exists() for path in paths)
    assert started == ["chunk-0.wav", "chunk-1.wav"]
    bridge.shutdown()


def test_late_audio_from_old_task_cannot_play_in_new_task(qapp, store):
    bridge = Bridge(store)
    old = TaskContext(lambda *a: "decline")
    bridge._task = TaskContext(lambda *a: "decline")
    path = wav(store.root / "late.wav")
    completed = threading.Event()
    bridge._queue_audio(str(path), old, completed)
    assert completed.is_set() and not path.exists()
    assert bridge._audio_path is None
    bridge.shutdown()


def test_first_reply_chunk_is_queued_before_next_chunk_is_synthesized(qapp, store, monkeypatch):
    store.set_setting("provider", "codex")
    bridge = Bridge(store)
    task = bridge._task = TaskContext(lambda *a: "decline")
    events = []

    def synth(text, task, path, signals):
        events.append(("render", text))
        wav(path)

    def queue(path, task, completed):
        events.append(("queued", path))
        completed.played = True
        completed.set()
        Path(path).unlink()

    monkeypatch.setattr(bridge, "_local_voice", synth)
    bridge.speechQueued.disconnect(bridge._queue_audio)
    bridge.speechQueued.connect(queue)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda *a: None))
    bridge._speak(Outcome("I can help with that. " + "Here are several helpful details to explain your answer. " * 5), task, signals)
    assert [item[0] for item in events[:4]] == ["render", "queued", "render", "queued"]
    assert len(events[0][1]) <= 100
    bridge.shutdown()


def test_restart_with_cached_prompts_still_warms_neural_model(qapp, qtbot, store, monkeypatch):
    bridge = Bridge(store)
    monkeypatch.setattr(bridge.neural, "ready", lambda: True)
    for name in PROMPTS:
        wav(bridge._prompt_path(name)[0])
    warmed = []
    monkeypatch.setattr(bridge.neural, "warm", lambda task: warmed.append("neural model loaded"))
    monkeypatch.setattr(bridge, "_local_voice", lambda *a: pytest.fail("Cached prompt regenerated"))
    monkeypatch.setattr(bridge.transcriber, "ready", lambda: False)
    bridge.prepareVoice()
    qtbot.waitUntil(lambda: not bridge._warm_jobs)
    assert warmed == ["neural model loaded"]
    assert not bridge.recording and not bridge.busy and not bridge.speaking
    bridge.shutdown()
