"""Explicit synthetic voice timing check; no microphone, cloud calls, or app actions."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from .config import data_dir
from .privacy import TaskContext

ANSWER = ("I can help with that. First, tell me which application you want to open. "
          "You can hold the microphone to give another command, or type your question in the command bar.")


def verify_response_speed(report: Path) -> int:
    from faster_whisper.audio import decode_audio
    from PySide6.QtCore import QTimer
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtWidgets import QApplication

    from .bridge import Bridge
    from .engine import Outcome
    from .neural_voice import NeuralVoice
    from .speech import Transcriber
    from .storage import Store
    from .voice_pipeline import speech_chunks

    app = QApplication([])
    source = Store(data_dir())
    result = {"microphone_used": False, "cloud_calls": False, "external_actions": False,
              "ai": "fixed public test reply, no AI inference", "playback": []}
    clock = {}
    with tempfile.TemporaryDirectory(prefix="macooii-response-check-") as folder:
        store = Store(Path(folder))
        for name in ("whisper_model", "language", "neural_voice", "voice_speed", "speaker"):
            store.set_setting(name, source.setting(name))
        store.set_setting("provider", "local")
        store.set_setting("voice_conversation", True)
        bridge = Bridge(store)
        bridge.neural = NeuralVoice(data_dir())
        bridge.transcriber = Transcriber(data_dir(), source.setting("model_directory"), source.setting("whisper_model"))
        task = TaskContext(lambda *args: "decline")
        recorded = Path(folder) / "public-input.wav"
        voice, speed = store.setting("neural_voice"), float(store.setting("voice_speed"))
        bridge.neural.speak("Macooii, open Notepad.", voice, speed, task, recorded)
        audio = decode_audio(str(recorded), sampling_rate=16000)
        reference = Path(folder) / "whole-reply.wav"
        start = time.perf_counter()
        bridge.neural.speak(ANSWER, voice, speed, task, reference)
        result["whole_reply_generation_seconds"] = round(time.perf_counter() - start, 3)
        reference.unlink()
        bridge.recorder.stop = lambda: audio
        render = bridge._local_voice

        def local_voice(text, task, path, signals):
            began = time.perf_counter()
            output = render(text, task, path, signals)
            if "release" in clock and "first_reply_chunk_generation_seconds" not in result:
                result["first_reply_chunk_generation_seconds"] = round(time.perf_counter() - began, 3)
            return output

        bridge._local_voice = local_voice

        def answer(text, task, status):
            clock["transcribed"] = time.perf_counter()
            result["transcript"] = text
            # Exercise the real bridge/voice pipeline without executing the test command.
            if task.cancelled.wait(0.6):
                task.check()
            return Outcome(ANSWER, "Public timing fixture")

        bridge.engine.run = answer

        def playing(state):
            if state != QMediaPlayer.PlaybackState.PlayingState or "release" not in clock:
                return
            kind = "answer" if bridge._task_answered else "acknowledgment"
            elapsed = round((time.perf_counter() - clock["release"]) * 1000, 1)
            result["playback"].append({"kind": kind, "milliseconds_after_release": elapsed})

        bridge.player.playbackStateChanged.connect(playing)
        bridge.voiceLevelChanged.connect(lambda: result.update(
            peak_audio_level=max(result.get("peak_audio_level", 0), bridge.voiceLevel)))
        bridge.toast.connect(lambda message: result.update(last_notice=message))
        poll = QTimer()
        poll.setInterval(20)

        def progress():
            if "release" not in clock:
                if bridge._warm_jobs:
                    return
                result["warmup_seconds"] = round(time.perf_counter() - clock["warmup"], 3)
                clock["release"] = time.perf_counter()
                bridge._recording = True
                bridge.stopRecording()
            elif (not bridge.busy and not bridge.speaking and not bridge._audio_queue
                  and bridge._audio_path is None):
                if bridge._task_answered or bridge.recognitionFeedback:
                    app.quit()

        poll.timeout.connect(progress)
        clock["warmup"] = time.perf_counter()
        bridge.prepareVoice()
        poll.start()
        QTimer.singleShot(90000, app.quit)
        app.exec()
        result["voice_engine"] = bridge._voice_engine_used
        result["speech_model"] = store.setting("whisper_model")
        result["recognition_cpu_threads"] = bridge.transcriber.cpu_threads
        result["language"] = store.setting("language")
        result["expected_answer_chunks"] = len(speech_chunks(ANSWER))
        if "transcribed" in clock:
            result["warm_transcription_seconds"] = round(clock["transcribed"] - clock["release"], 3)
        bridge.shutdown()
        bridge.pool.waitForDone(10000)
    receipts = [p for p in result["playback"] if p["kind"] == "acknowledgment"]
    replies = [p for p in result["playback"] if p["kind"] == "answer"]
    result["passed"] = (bool(receipts) and receipts[0]["milliseconds_after_release"] < 500
                        and len(replies) == result["expected_answer_chunks"]
                        and result["voice_engine"] == "neural" and result.get("peak_audio_level", 0) > 0)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["passed"] else 1
