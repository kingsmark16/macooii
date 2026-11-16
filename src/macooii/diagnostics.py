"""Explicit CLI diagnostics for the installed build; never reads credentials or records audio."""
from __future__ import annotations

import importlib
import json
import tempfile
import time
from pathlib import Path

from .config import LOCAL_MODEL, data_dir
from .engine import Engine
from .privacy import TaskContext
from .providers import ollama_status
from .speech import Transcriber
from .storage import Store


def verify_voice(report: Path, command: bool = False, neural: bool = False) -> int:
    """Explicit audible check using disposable settings; never records a microphone."""
    import array
    import wave

    from PySide6.QtCore import QTimer
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtWidgets import QApplication

    from .bridge import Bridge

    app = QApplication([])
    result = {"playing": False, "finished": False, "pcm_peak": 0, "peak_visual_level": 0.0}
    events = []
    with tempfile.TemporaryDirectory(prefix="macooii-voice-check-") as folder:
        bridge = Bridge(Store(Path(folder)))
        bridge.voiceLevelChanged.connect(lambda: result.update(peak_visual_level=max(result["peak_visual_level"], bridge.voiceLevel)))
        if neural:
            from .neural_voice import NeuralVoice
            bridge.neural = NeuralVoice(data_dir())
        if command:
            save = bridge.engine.registry.create_note

            def save_note(args, task):
                events.append("action")
                return save(args, task)

            bridge.engine.registry.create_note = save_note

        def audio(path):
            with wave.open(path) as stream:
                pcm = array.array("h", stream.readframes(stream.getnframes()))
            result["pcm_peak"] = max((abs(value) for value in pcm), default=0)

        def state(value):
            if value == QMediaPlayer.PlaybackState.PlayingState:
                result["playing"] = True

        def status(value):
            if value == QMediaPlayer.MediaStatus.EndOfMedia:
                result["finished"] = True
                events.append("speech_finished")
                if not command or events.count("speech_finished") == 2:
                    app.quit()

        bridge.audioReady.connect(audio)
        bridge.speechQueued.connect(lambda path, task, completed: audio(path))
        bridge.player.playbackStateChanged.connect(state)
        bridge.player.mediaStatusChanged.connect(status)
        bridge.toast.connect(lambda message: result.update(message=message))
        QTimer.singleShot(100, lambda: bridge.send("/note Voice check | Public test note") if command else bridge.testVoice(""))
        QTimer.singleShot(30000 if command or neural else 15000, app.quit)
        app.exec()
        bridge.shutdown()
        bridge.pool.waitForDone(5000)
        result["voice_engine"] = bridge._voice_engine_used
    result["passed"] = result["playing"] and result["finished"] and result["pcm_peak"] > 100 and result["peak_visual_level"] > 0
    if command:
        result["events"] = events
        result["passed"] = result["passed"] and events == ["speech_finished", "action", "speech_finished"]
    if neural:
        result["passed"] = result["passed"] and result["voice_engine"] == "neural"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["passed"] else 1


def verify(report: Path, audio: Path | None = None, web: bool = False) -> int:
    result = {"checks": {}, "model": LOCAL_MODEL}
    for name in ("sounddevice", "numpy", "av", "ctranslate2", "onnxruntime", "faster_whisper",
                 "keyring.backends.Windows", "win32com.client", "playwright.sync_api", "docx", "pypdf"):
        try:
            importlib.import_module(name)
            result["checks"][name] = "passed"
        except Exception as exc:
            result["checks"][name] = type(exc).__name__
    try:
        with tempfile.TemporaryDirectory(prefix="macooii-runtime-check-") as directory:
            store = Store(Path(directory))
            engine = Engine(store, lambda: "")
            engine.run("/note Diagnostic | Public test note", TaskContext(lambda *args: "decline"), lambda x: None)
            result["checks"]["local_tools"] = "passed" if len(store.notes()) == 1 else "failed"
        result["ollama"] = ollama_status()
        settings = Store(data_dir())
        selected_model = settings.setting("whisper_model")
        transcriber = Transcriber(data_dir(), settings.setting("model_directory"), selected_model)
        result["speech_model"] = selected_model
        result["speech_model_ready"] = transcriber.ready()
        if audio:
            from faster_whisper.audio import decode_audio
            data = decode_audio(str(audio), sampling_rate=16000)
            started = time.monotonic()
            text = transcriber.transcribe(data, settings.setting("language"), TaskContext(lambda *args: "decline"))
            result["transcript"] = text
            result["transcription_seconds"] = round(time.monotonic() - started, 2)
            result["recognition"] = transcriber.last_result
            result["checks"]["transcription"] = "passed" if "notepad" in text.casefold() else "failed"
        if web:
            from .browser import Browser
            page = Browser().read("https://example.com", TaskContext(lambda *args: "decline"))
            result["checks"]["public_browser"] = "passed" if page["text"] else "failed"
    except Exception as exc:
        result["checks"]["runtime"] = type(exc).__name__
    result["passed"] = all(value == "passed" for value in result["checks"].values())
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result["passed"] else 1
