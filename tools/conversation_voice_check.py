"""Synthetic speech → real local transcription → auto-send → spoken test reply; no microphone or app actions."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from faster_whisper.audio import decode_audio
from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from macooii.bridge import Bridge
from macooii.config import data_dir
from macooii.engine import Outcome
from macooii.neural_voice import NeuralVoice
from macooii.privacy import TaskContext
from macooii.speech import Transcriber
from macooii.storage import Store


def main():
    app = QApplication([])
    neural = NeuralVoice(data_dir())
    recording = Path("output/voice-conversation-input.wav")
    neural.speak("Macooii, open Notepad.", "bm_george", 1.0, TaskContext(lambda *args: "decline"), recording)
    audio = decode_audio(str(recording), sampling_rate=16000)
    report = {"played": False, "microphone_used": False, "external_actions": False}
    with tempfile.TemporaryDirectory(prefix="macooii-conversation-qa-") as folder:
        store = Store(Path(folder))
        store.set_setting("provider", "local")
        store.set_setting("voice_conversation", True)
        store.set_setting("language", "en")
        bridge = Bridge(store)
        bridge.neural = neural
        bridge.transcriber = Transcriber(data_dir())
        bridge.recorder.stop = lambda: audio

        def run(text, task, status):
            report["transcript_sent"] = text
            return Outcome("I heard your request. Voice conversation is ready.", "Local test")

        bridge.engine = SimpleNamespace(run=run)

        def status(value):
            if value == QMediaPlayer.MediaStatus.EndOfMedia:
                report["played"] = True
                app.quit()

        bridge.player.mediaStatusChanged.connect(status)

        def begin():
            bridge._recording = True
            bridge.stopRecording()

        QTimer.singleShot(100, begin)
        QTimer.singleShot(60000, app.quit)
        app.exec()
        report["voice_engine"] = bridge._voice_engine_used
        bridge.shutdown()
        bridge.pool.waitForDone(5000)
    report["passed"] = report["played"] and "notepad" in report.get("transcript_sent", "").casefold() and report["voice_engine"] == "neural"
    Path("output/voice-conversation-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
