"""Explicit local capture diagnostics. No command execution, uploads, or automatic audio files."""
from __future__ import annotations

import argparse
import io
import time
import wave
from pathlib import Path

import numpy as np
from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import data_dir, resource_path
from .privacy import Cancelled, TaskContext
from .speech import Recorder, Transcriber, microphones, prepare_audio
from .storage import Store


def wav_bytes(audio):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return output.getvalue()


class Signals(QObject):
    progress = Signal(str)
    result = Signal(str, str)
    error = Signal(str)
    finished = Signal()


class Compare(QRunnable):
    def __init__(self, transcriber, audio, task):
        super().__init__()
        self.transcriber, self.audio, self.task = transcriber, audio, task
        self.signals = Signals()

    def run(self):
        try:
            self.signals.progress.emit("Transcribing locally in English…")
            normal = self.transcriber.transcribe(self.audio, "en", self.task)
            self.signals.result.emit("normal", normal)
            self.task.check()
            self.signals.progress.emit("Comparing the same capture without VAD, gain adjustment, or vocabulary hints…")
            segments, _ = self.transcriber.model.transcribe(
                np.ascontiguousarray(self.audio, dtype=np.float32), language="en", task="transcribe",
                vad_filter=False, beam_size=5, temperature=0.0, condition_on_previous_text=False,
                initial_prompt=None, hotwords=None, word_timestamps=False)
            parts = []
            for segment in segments:
                self.task.check()
                parts.append(segment.text)
            self.task.check()
            self.signals.result.emit("baseline", " ".join(parts).strip())
        except Cancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(str(exc) if isinstance(exc, ValueError) else "The local recognition check failed.")
        finally:
            self.audio = None
            self.signals.finished.emit()


class MicrophoneCheck(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Macooii — Microphone check")
        self.resize(900, 680)
        self.setMinimumSize(760, 580)
        self.setStyleSheet("""
            QWidget { background:#0b1219; color:#e5eff4; font:14px 'Figtree'; }
            QPushButton,QComboBox { background:#16362f; border:1px solid #2b6657; border-radius:7px; padding:10px; }
            QPushButton:disabled { color:#607884; background:#15212a; border-color:#263743; }
            QPlainTextEdit { background:#121e28; border:1px solid #2a3d49; border-radius:8px; padding:10px; }
            QProgressBar { border:1px solid #2a3d49; border-radius:5px; background:#121e28; }
            QProgressBar::chunk { background:#35c9aa; }
        """)
        self.recorder = Recorder()
        store = Store(data_dir())
        self.transcriber = Transcriber(data_dir(), store.setting("model_directory"), store.setting("whisper_model"))
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.task = TaskContext(lambda *args: "decline")
        self.audio = None
        self.recording = self.busy = False
        self.jobs = []
        self.buffer = None
        self.output = QAudioOutput(self)
        selected = store.setting("speaker")
        outputs = QMediaDevices.audioOutputs()
        device = next((item for item in outputs if bytes(item.id().toHex()).decode() == selected), None) if selected else QMediaDevices.defaultAudioOutput()
        if device:
            self.output.setDevice(device)
        self.output.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda error, message: self.status.setText("Replay error: " + message))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("What is the microphone actually hearing?")
        title.setStyleSheet("font-size:24px; font-weight:600; color:#b8f3df")
        layout.addWidget(title)
        instructions = QLabel("Click Record when ready. Wait for RECORDING, then say:\n“Open the browser and search for documentation.”\nThis test runs no commands. Audio stays in memory; saving a WAV is optional.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.devices = microphones()
        self.device = QComboBox()
        for item in self.devices:
            self.device.addItem(item["label"], item["name"])
        index = self.device.findData(store.setting("microphone"))
        self.device.setCurrentIndex(max(0, index))
        layout.addWidget(self.device)
        controls = QHBoxLayout()
        self.record_button = QPushButton("Record 8 seconds")
        self.stop_button = QPushButton("Finish recording")
        self.replay_button = QPushButton("Replay captured audio")
        self.discard_button = QPushButton("Discard")
        self.save_button = QPushButton("Save captured WAV…")
        for button in (self.record_button, self.stop_button, self.replay_button, self.discard_button, self.save_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.boost = QCheckBox("Boost quiet replay volume (up to 4×). Saved WAV stays at the captured level.")
        self.boost.setChecked(True)
        layout.addWidget(self.boost)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setMaximumHeight(12)
        layout.addWidget(self.level)
        self.metadata = QLabel("No test audio captured yet.")
        self.metadata.setTextFormat(Qt.TextFormat.PlainText)
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        layout.addWidget(QLabel("Macooii recognition — English"))
        self.normal = QPlainTextEdit()
        self.normal.setReadOnly(True)
        layout.addWidget(self.normal)
        layout.addWidget(QLabel("Comparison — same audio, no VAD/gain/hints"))
        self.baseline = QPlainTextEdit()
        self.baseline.setReadOnly(True)
        layout.addWidget(self.baseline)
        self.status = QLabel("Ready. Replay is the important check: do you hear your full sentence clearly?")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.tick)
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.setInterval(5 * 60 * 1000)
        self.expiry.timeout.connect(self.discard)
        self.record_button.clicked.connect(self.record)
        self.stop_button.clicked.connect(self.finish_recording)
        self.replay_button.clicked.connect(self.replay)
        self.discard_button.clicked.connect(self.discard)
        self.save_button.clicked.connect(self.save)
        self.buttons()

    def buttons(self):
        self.record_button.setEnabled(not self.recording and not self.busy)
        self.device.setEnabled(not self.recording and not self.busy)
        self.stop_button.setEnabled(self.recording)
        self.replay_button.setEnabled(self.audio is not None and not self.recording)
        self.save_button.setEnabled(self.audio is not None and not self.recording)
        self.discard_button.setEnabled(self.audio is not None or self.recording or self.busy)

    def stop_playback(self):
        self.player.stop()
        self.player.setSource(QUrl())
        if self.buffer is not None:
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None

    def record(self):
        self.discard()
        self.task = TaskContext(lambda *args: "decline")
        try:
            self.recorder.start(self.device.currentData())
        except Exception as exc:
            self.status.setText("Microphone could not start: " + str(exc))
            return
        self.recording = True
        self.started = time.monotonic()
        self.status.setText("RECORDING — say the test sentence now.")
        self.metadata.setText("Input: " + self.recorder.input_name)
        self.timer.start()
        self.buttons()

    def tick(self):
        remaining = max(0, 8 - (time.monotonic() - self.started))
        self.level.setValue(int(min(1, max(0, self.recorder.level)) ** 0.4 * 100))
        self.status.setText(f"RECORDING — {remaining:.1f} seconds remaining")
        if remaining <= 0:
            self.finish_recording()

    def accept_audio(self, audio, quality, name):
        self.audio = np.asarray(audio, dtype=np.float32).copy()
        self.metadata.setText(f"Input: {name} | Capture: {quality.get('sample_rate', 16000)} Hz | "
            f"Received: {len(audio) / 16000:.2f} s | Signal: {quality.get('rms_db', 0)} dBFS | "
            f"Clipped: {quality.get('clipping', False)} | Dropped audio: {quality.get('dropped_audio', False)}")
        self.expiry.start()
        self.buttons()

    def finish_recording(self):
        if not self.recording:
            return
        self.timer.stop()
        self.recording = False
        try:
            audio = self.recorder.stop()
        except Exception as exc:
            self.status.setText("Capture failed: " + str(exc))
            self.buttons()
            return
        self.accept_audio(audio, self.recorder.last_quality, self.recorder.input_name)
        self.busy = True
        job = Compare(self.transcriber, self.audio, self.task)
        self.jobs.append(job)
        job.signals.progress.connect(self.status.setText)
        job.signals.result.connect(self.result)
        job.signals.error.connect(self.status.setText)

        def finished():
            self.busy = False
            if job in self.jobs:
                self.jobs.remove(job)
            self.buttons()

        job.signals.finished.connect(finished)
        self.buttons()
        self.pool.start(job)

    def result(self, kind, text):
        if self.task.cancelled.is_set():
            return
        (self.normal if kind == "normal" else self.baseline).setPlainText(text or "[No speech detected]")
        if kind == "baseline":
            self.status.setText("Finished. Replay the recording and compare both transcripts with what you actually said. Nothing was sent or executed.")

    def replay(self):
        if self.audio is None:
            return
        self.stop_playback()
        audio = self.audio
        if self.boost.isChecked():
            try:
                audio = prepare_audio(audio)
            except ValueError:
                pass
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(wav_bytes(audio)))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer, QUrl("microphone-test.wav"))
        self.player.play()

    def save(self):
        if self.audio is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save this microphone test only if you want to keep or share it",
                                              str(Path.home() / "Desktop/Macooii-microphone-test.wav"), "WAV audio (*.wav)")
        if path:
            try:
                Path(path).write_bytes(wav_bytes(self.audio))
                self.status.setText("Saved the test WAV you selected. It has not been uploaded or shared.")
            except OSError:
                self.status.setText("Could not save the WAV. Choose a writable folder and try again.")

    def discard(self):
        self.task.cancelled.set()
        self.timer.stop()
        self.expiry.stop()
        if self.recording:
            self.recorder.stop()
            self.recording = False
        self.stop_playback()
        self.audio = None
        self.normal.clear()
        self.baseline.clear()
        self.level.setValue(0)
        self.metadata.setText("Test audio discarded.")
        self.status.setText("Ready to record. Tests expire after five minutes or when you discard/close this window.")
        self.buttons()

    def closeEvent(self, event):
        self.discard()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description="Local microphone check; records only after clicking Record")
    parser.add_argument("--qa-audio", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--verify-playback", action="store_true")
    options = parser.parse_args()
    app = QApplication([])
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    app.setFont(QFont("Figtree", 10))
    window = MicrophoneCheck()
    window.show()
    if options.qa_audio:
        from faster_whisper.audio import decode_audio
        window.accept_audio(decode_audio(str(options.qa_audio), sampling_rate=16000), {"sample_rate": 16000}, "Generated QA audio")
    if options.screenshot:
        def capture():
            window.grab().save(str(options.screenshot))
            app.quit()
        QTimer.singleShot(400, capture)
    report = {"playing": False, "finished": False}
    if options.verify_playback:
        def state(value):
            if value == QMediaPlayer.PlaybackState.PlayingState:
                report["playing"] = True
        def status(value):
            if value == QMediaPlayer.MediaStatus.EndOfMedia:
                report["finished"] = True
                app.quit()
        window.player.playbackStateChanged.connect(state)
        window.player.mediaStatusChanged.connect(status)
        QTimer.singleShot(200, window.replay)
        QTimer.singleShot(10000, app.quit)
    result = app.exec()
    window.discard()
    window.pool.waitForDone(60000)
    if options.verify_playback:
        print(report, flush=True)
        return 0 if all(report.values()) else 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
