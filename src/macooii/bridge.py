from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
from PySide6.QtCore import Property, QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from . import credentials
from .browser_capture import next_capture
from .codex_provider import codex_status
from .config import GEMINI_MODELS, LOCAL_MODEL, OPEN_SHORTCUTS, SPEECH_MODELS, TALK_SHORTCUTS
from .engine import Engine, Outcome
from .neural_voice import VOICES, NeuralVoice
from .privacy import Cancelled, LocalRequested, TaskContext
from .providers import ProviderError, ollama_status
from .speech import Recorder, Transcriber, cloud_speech, microphones, speech_excerpt, windows_speech
from .storage import Store
from .voice_pipeline import PROMPTS, PromptCache, speech_chunks


class JobSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    progress = Signal(str)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.signals = JobSignals()
        self.function = function

    def run(self):
        try:
            result = self.function(self.signals)
            self.signals.result.emit(result)
        except Cancelled:
            self.signals.error.emit("Cancelled. No further actions will run.")
        except ProviderError as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:
            # Do not surface remote payloads, credentials, or OS exception paths in diagnostics.
            self.signals.error.emit(str(exc) if isinstance(exc, ValueError) else
                                    "The operation could not finish. Check your setup and try again.")
        finally:
            self.signals.finished.emit()


class Bridge(QObject):
    messagesChanged = Signal()
    dataChanged = Signal()
    settingsChanged = Signal()
    stateChanged = Signal()
    statusChanged = Signal()
    cardsChanged = Signal()
    approvalChanged = Signal()
    approvalRequested = Signal(str, str)
    transcriptReady = Signal(str)
    showRequested = Signal()
    toast = Signal(str)
    audioReady = Signal(str)
    announcementReady = Signal(str, object)
    speechQueued = Signal(str, object, object)
    browserCaptureChanged = Signal()
    microphoneLevelChanged = Signal()
    recognitionChanged = Signal()
    microphoneTestRequested = Signal()
    voiceStateChanged = Signal()
    voiceLevelChanged = Signal()

    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.engine = Engine(store, credentials.get_api_key)
        self.browser_actions = self.engine.registry.actions
        self.recorder = Recorder()
        self.neural = NeuralVoice(store.root)
        self.prompt_cache = PromptCache(store.root)
        self.transcriber = Transcriber(store.root, store.setting("model_directory"), store.setting("whisper_model"))
        self._recognition_feedback = ""
        self.mic_timer = QTimer(self)
        self.mic_timer.setInterval(60)
        self.mic_timer.timeout.connect(self.microphoneLevelChanged.emit)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._jobs = []
        self._warm_jobs = []
        self._warm_task = None
        self._shutting_down = False
        self._continuing_voice_task = None
        self._busy = False
        self._recording = False
        self._talk_held = False
        self._record_after_cancel = False
        self._pending_voice_text = ""
        self._microphone_test = False
        self._status = "Ready when you are"
        self._cards = []
        self._pending_approval = {}
        self._approval_event = threading.Event()
        self._approval_choice = "decline"
        self._task: TaskContext | None = None
        self._ollama = {"running": False, "ready": False}
        self._key_present = False
        self._codex_status = "Use Check Codex to verify your ChatGPT login"
        self._microphones = [{"id": -1, "name": "", "label": "Windows default input"}]
        self._audio_path = None
        self._voice_engine_used = "none"
        self._audio_done = None
        self._audio_task = None
        self._audio_queue = []
        self._browser_capture = {}
        cache = store.root / "speech-cache"
        if cache.exists():
            for stale in cache.glob("macooii-????????????????.wav"):
                try:
                    stale.unlink()
                except OSError:
                    pass
        self._active_user_id = None
        self._task_answered = False
        self.player = QMediaPlayer(self)
        self._voice_level = 0.0
        self.audio_buffers = QAudioBufferOutput(self)
        self.player.setAudioBufferOutput(self.audio_buffers)
        self.audio_buffers.audioBufferReceived.connect(self._voice_buffer)
        self.player.playbackStateChanged.connect(self._voice_state)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.audio_output.setMuted(False)
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.settingsChanged)
        self.player.setAudioOutput(self.audio_output)
        self.announcementReady.connect(self._play_announcement)
        self.speechQueued.connect(self._queue_audio)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._playback_error)
        self.approvalRequested.connect(self._show_approval)
        self.audioReady.connect(self._play_audio)
        self.prune_timer = QTimer(self)
        self.prune_timer.setInterval(60 * 60 * 1000)
        self.prune_timer.timeout.connect(self._prune)
        self.prune_timer.start()
        self.capture_timer = QTimer(self)
        self.capture_timer.setInterval(1000)
        self.capture_timer.timeout.connect(self._poll_capture)
        self.capture_timer.start()
        try:
            self._key_present = bool(credentials.get_api_key())
        except Exception:
            pass

    @Slot()
    def _prune(self):
        self.store.prune()
        self.messagesChanged.emit()
        self.dataChanged.emit()

    @Property("QVariantMap", notify=browserCaptureChanged)
    def browserCapture(self):
        return self._browser_capture

    @Slot()
    def _poll_capture(self):
        if self._busy or self._recording or self._browser_capture:
            return
        try:
            capture = next_capture(self.store.root)
        except OSError:
            return
        if capture:
            self._browser_capture = capture
            self.browserCaptureChanged.emit()
            self.showRequested.emit()

    @Slot()
    def dismissBrowserCapture(self):
        self._browser_capture = {}
        self.browserCaptureChanged.emit()

    @Slot()
    def summarizeBrowserCapture(self):
        if self._busy or self._recording or not self._browser_capture:
            return
        capture = self._browser_capture
        self.dismissBrowserCapture()
        self.stopAudio()
        self._cards = []
        self.cardsChanged.emit()
        self._task = TaskContext(self._ask)
        task = self._task
        self._active_user_id = self.store.add_message("user", "Summarize the Facebook tab I selected: " + capture["title"], True)
        task.current_message_id = self._active_user_id
        self._task_answered = False
        self.messagesChanged.emit()

        def work(signals):
            outcome = self.engine.summarize_capture(capture, task, signals.progress.emit)
            task.check()
            signals.result.emit(outcome)
            if self.store.setting("speech_enabled"):
                self._speak(outcome, task, signals)
            return None

        self._start_job(work, self._received, self._task_error)

    @Property("QVariantList", notify=messagesChanged)
    def messages(self):
        return self.store.messages()

    @Property("QVariantList", notify=dataChanged)
    def notes(self):
        return self.store.notes()

    @Property("QVariantList", notify=dataChanged)
    def memories(self):
        return self.store.memories()

    @Property("QVariantList", notify=dataChanged)
    def activity(self):
        return self.store.activity()

    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        return self.store.settings()

    @Property(bool, notify=stateChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=stateChanged)
    def recording(self):
        return self._recording

    @Property(bool, notify=voiceStateChanged)
    def speaking(self):
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @Property(float, notify=voiceLevelChanged)
    def voiceLevel(self):
        return self._voice_level

    def _voice_state(self, state):
        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._voice_level = 0.0
            self.voiceLevelChanged.emit()
        self.voiceStateChanged.emit()

    def _voice_buffer(self, buffer):
        import numpy as np
        if not buffer.isValid() or not buffer.byteCount():
            return
        kind = buffer.format().sampleFormat()
        formats = {QAudioFormat.SampleFormat.Float: ("<f4", 1),
                   QAudioFormat.SampleFormat.Int16: ("<i2", 32768),
                   QAudioFormat.SampleFormat.Int32: ("<i4", 2147483648),
                   QAudioFormat.SampleFormat.UInt8: ("u1", 128)}
        if kind not in formats:
            return
        dtype, divisor = formats[kind]
        values = np.frombuffer(buffer.constData(), dtype=dtype).astype(np.float32)
        if kind == QAudioFormat.SampleFormat.UInt8:
            values -= 128
        rms = float(np.sqrt(np.mean((values / divisor) ** 2)))
        self._voice_level = min(1.0, max(0.0, rms * 7)) if math.isfinite(rms) else 0.0
        self.voiceLevelChanged.emit()

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property("QVariantList", notify=cardsChanged)
    def cards(self):
        return self._cards

    @Property("QVariantMap", notify=approvalChanged)
    def pendingApproval(self):
        return self._pending_approval

    @Property(bool, notify=settingsChanged)
    def hasKey(self):
        return self._key_present

    @Property(bool, notify=settingsChanged)
    def speechReady(self):
        return self.transcriber.ready()

    @Property(float, notify=microphoneLevelChanged)
    def microphoneLevel(self):
        peak = max(float(getattr(self.recorder, "level", 0)), 1e-6)
        return max(0.0, min(1.0, (20 * math.log10(peak) + 60) / 60))

    @Property(bool, notify=microphoneLevelChanged)
    def microphoneClipping(self):
        return getattr(self.recorder, "level", 0) >= 0.99

    @Property(str, notify=recognitionChanged)
    def recognitionFeedback(self):
        return self._recognition_feedback

    @Property(str, notify=settingsChanged)
    def localStatus(self):
        if self._ollama.get("ready"):
            return "Qwen3 4B is ready"
        return "Ollama running · model needed" if self._ollama.get("running") else "Ollama not detected"

    @Property(str, notify=settingsChanged)
    def codexStatus(self):
        return self._codex_status

    @Slot()
    def checkCodex(self):
        if self._busy:
            return
        self._task = TaskContext(self._ask)

        def received(value):
            self._codex_status = "ChatGPT login connected · " + str(value.get("plan", "plan"))
            self.settingsChanged.emit()

        self._start_job(lambda signals: codex_status(), received)

    @Property(str, notify=settingsChanged)
    def diskStatus(self):
        return f"{shutil.disk_usage(self.store.root).free / 1024**3:.1f} GB free on data drive"

    @Property(str, constant=True)
    def dataLocation(self):
        return str(self.store.root)

    @Property("QVariantList", notify=settingsChanged)
    def microphoneChoices(self):
        choices = list(self._microphones)
        selected = self.store.setting("microphone")
        if selected and not any(item["name"] == selected for item in choices):
            choices.append({"id": -2, "name": selected, "label": selected + " (refresh to check)"})
        return choices

    @Property("QVariantList", notify=settingsChanged)
    def speakerChoices(self):
        choices = [{"id": "", "label": "Windows default speakers"}]
        choices += [{"id": bytes(device.id().toHex()).decode("ascii"), "label": device.description()}
                    for device in QMediaDevices.audioOutputs()]
        selected = self.store.setting("speaker")
        if selected and not any(choice["id"] == selected for choice in choices):
            choices.append({"id": selected, "label": "Selected output unavailable"})
        return choices

    @Slot()
    def refreshMicrophones(self):
        if self._busy or self._recording:
            return
        self._task = TaskContext(self._ask)

        def received(choices):
            self._microphones = choices
            self.settingsChanged.emit()
            if len(choices) == 1:
                self.toast.emit("No microphone inputs detected. Check Windows audio settings.")

        self._start_job(lambda signals: microphones(), received)

    @Slot(str)
    def _set_status(self, value):
        self._status = value
        self.statusChanged.emit()

    def _start_job(self, function, on_result=None, on_error=None):
        if self._busy:
            self.toast.emit("Finish or cancel the current task first.")
            return
        self._busy = True
        self.stateChanged.emit()
        job = Job(function)
        self._jobs.append(job)
        job.signals.progress.connect(self._set_status)
        if on_result:
            job.signals.result.connect(on_result)
        job.signals.error.connect(on_error or self.toast.emit)

        def finished():
            if job in self._jobs:
                self._jobs.remove(job)
            self._busy = False
            self._pending_approval = {}
            self.approvalChanged.emit()
            self.stateChanged.emit()
            self.dataChanged.emit()
            self.settingsChanged.emit()
            self._set_status("Ready when you are")
            pending = self._pending_voice_text
            self._pending_voice_text = ""
            if self._record_after_cancel:
                self._record_after_cancel = False
                QTimer.singleShot(0, lambda: self.startRecording() if self._talk_held else None)
            elif pending and self._task and not self._task.cancelled.is_set():
                voice_task = self._task

                def resume_voice():
                    if voice_task.cancelled.is_set() or self._task is not voice_task:
                        return
                    self._continuing_voice_task = voice_task
                    try:
                        self.send(pending)
                    finally:
                        self._continuing_voice_task = None

                QTimer.singleShot(0, resume_voice)

        job.signals.finished.connect(finished)
        self.pool.start(job)

    def _ask(self, label: str, text: str) -> str:
        self._approval_event.clear()
        self._approval_choice = "decline"
        self.approvalRequested.emit(label, text)
        while not self._approval_event.wait(0.1):
            if self._task:
                self._task.check()
        return self._approval_choice

    @Slot(str, str)
    def _show_approval(self, label, text):
        if not self._task or self._task.cancelled.is_set():
            self._approval_event.set()
            return
        provider, _, title = label.partition("\n")
        self._pending_approval = {"label": title or label, "text": text, "provider": provider,
                                  "allowLocal": provider in {"Google Gemini", "OpenAI Codex"}}
        self.approvalChanged.emit()
        self._set_status("Waiting for your approval")
        self.showRequested.emit()

    @Slot(str)
    def resolveApproval(self, choice):
        self._approval_choice = choice if choice in {"approve", "decline", "local"} else "decline"
        self._pending_approval = {}
        self.approvalChanged.emit()
        self._approval_event.set()

    @Slot(str)
    def send(self, text):
        text = text.strip()
        if not text or self._busy or self._recording:
            return
        if len(text) > 20_000:
            self.toast.emit("Please keep a request under 20,000 characters.")
            return
        continuing = self._continuing_voice_task
        if not continuing:
            if self._task:
                self._task.cancelled.set()
            self.stopAudio()
        self._recognition_feedback = ""
        self.recognitionChanged.emit()
        self._cards = []
        self.cardsChanged.emit()
        self._task = continuing or TaskContext(self._ask)
        task = self._task
        # Hold the user turn private until this task finishes and its sensitivity is known.
        self._active_user_id = self.store.add_message("user", text, True)
        task.current_message_id = self._active_user_id
        self._task_answered = False
        self.messagesChanged.emit()

        def work(signals):
            if self.store.setting("speech_enabled"):
                task.before_action = lambda name: self._announce_action(name, task, signals)
            outcome = self.engine.run(text, task, signals.progress.emit)
            task.check()
            signals.result.emit(outcome)
            if self.store.setting("speech_enabled"):
                self._speak(outcome, task, signals)
            return None

        self._start_job(work, self._received, self._task_error)
        # Clear commands often have their own action announcement before this timer.
        QTimer.singleShot(250, lambda: self._acknowledge(task) if not self._task_answered else None)

    @Slot(object)
    def _received(self, outcome):
        if outcome is None:
            return
        self._task_answered = True
        self.store.mark_sensitive(self._active_user_id, outcome.sensitive)
        self.store.add_message("assistant", outcome.text, outcome.sensitive)
        self._cards = outcome.cards
        self.messagesChanged.emit()
        self.cardsChanged.emit()
        self.dataChanged.emit()

    @Slot(str)
    def _task_error(self, message):
        if self._task:
            self._cards = self._task.local_cards
            self.cardsChanged.emit()
        if not self._task_answered:
            self.store.add_message("assistant", message, True)
            self.messagesChanged.emit()
        else:
            self.toast.emit(message)

    def _speak(self, outcome: Outcome, task: TaskContext, signals):
        text = speech_excerpt(outcome.speech_text or outcome.text)
        if not text:
            return
        task.check()
        settings = self.store.settings()
        key = credentials.get_api_key() if settings["cloud_enabled"] and settings["provider"] not in {"local", "codex"} else ""
        cloud_allowed = key and settings["cloud_speech"] and settings["provider"] not in {"local", "codex"}
        if cloud_allowed and outcome.sensitive and not (outcome.provider == "Gemini" and task.approved):
            try:
                task.cloud_context("Spoken reply text", text)
            except (PermissionError, LocalRequested):
                cloud_allowed = False
        if cloud_allowed:
            signals.progress.emit("Preparing spoken reply")
            path = self._speech_path()
            try:
                cloud_speech(text, key, settings["tts_model"], settings["voice"], task, path)
                task.check()
                self.speechQueued.emit(str(path), task, threading.Event())
                return
            except Cancelled:
                path.unlink(missing_ok=True)
                raise
            except Exception:
                path.unlink(missing_ok=True)
                signals.progress.emit("Cloud speech unavailable · using Windows voice")
        task.check()
        if os.name == "nt":
            previous = None
            for chunk in speech_chunks(text):
                task.check()
                path = self._speech_path()
                try:
                    self._local_voice(chunk, task, path, signals)
                    task.check()
                    completed = threading.Event()
                    self.speechQueued.emit(str(path), task, completed)
                    # Keep at most two generated chunks ahead of playback. Synthesis of
                    # the next chunk overlaps the current audio instead of delaying it.
                    if previous:
                        self._wait_for_audio(previous, task, 60)
                    previous = completed
                except BaseException:
                    path.unlink(missing_ok=True)
                    raise

    def _speech_path(self):
        directory = self.store.root / "speech-cache"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / ("macooii-" + os.urandom(8).hex() + ".wav")

    @Property(bool, notify=settingsChanged)
    def neuralVoiceReady(self):
        return self.neural.ready()

    @Slot()
    def downloadNaturalVoice(self):
        if self._busy or self._recording:
            return
        self._task = TaskContext(self._ask)
        task = self._task
        def received(result):
            self.toast.emit("Natural voice is ready. Choose a voice and Test voice in Settings.")
            QTimer.singleShot(0, self.prepareVoice)

        self._start_job(lambda signals: self.neural.download(task, signals.progress.emit), received)

    def _local_voice(self, text, task, path, signals):
        if self.store.setting("speech_engine") == "neural" and self.neural.ready():
            signals.progress.emit("Preparing natural voice locally")
            try:
                result = self.neural.speak(text, self.store.setting("neural_voice"),
                                           float(self.store.setting("voice_speed")), task, path)
                self._voice_engine_used = "neural"
                return result
            except Cancelled:
                raise
            except Exception:
                task.check()
                signals.progress.emit("Natural voice unavailable · using Windows voice")
                self.toast.emit("Natural voice could not generate this reply. Windows voice is being used.")
        self._voice_engine_used = "windows"
        return windows_speech(text, task, path)

    def _prompt_path(self, name):
        settings = self.store.settings()
        engine = "neural" if settings["speech_engine"] == "neural" and self.neural.ready() else "windows"
        return self.prompt_cache.path(name, engine, settings["neural_voice"] if engine == "neural" else "default",
                                      float(settings["voice_speed"]) if engine == "neural" else 1.0), engine

    def _prepare_prompt(self, name, task, signals):
        cached, engine = self._prompt_path(name)
        if self.prompt_cache.ready(cached):
            return cached
        path = self._speech_path()
        try:
            self._local_voice(PROMPTS[name], task, path, signals)
            task.check()
            # A failed neural synthesis must not permanently cache its Windows fallback
            # under the neural key. Reuse the already generated fallback for this action.
            if self._voice_engine_used != engine:
                cached = self.prompt_cache.path(name, "windows", "default", 1.0)
            cached.parent.mkdir(parents=True, exist_ok=True)
            path.replace(cached)
            return cached
        finally:
            path.unlink(missing_ok=True)

    @Slot()
    def prepareVoice(self):
        """Warm local assets on a separate worker; this never opens the microphone."""
        if self._shutting_down:
            return
        if self._warm_task:
            self._warm_task.cancelled.set()
        task = self._warm_task = TaskContext(lambda *args: "decline")
        transcriber = self.transcriber

        def warm(signals):
            if self.store.setting("speech_enabled") and os.name == "nt":
                self._prepare_prompt("receipt", task, signals)
            # Connection setup reads login/config only, without sending a user turn.
            try:
                self.engine.prepare_codex(task)
            except ProviderError:
                pass  # A failed prewarm must not prevent local recognition from warming.
            if self.store.setting("speech_engine") == "neural" and self.neural.ready():
                try:
                    self.neural.warm(task)
                except ValueError:
                    pass  # Voice generation retains its explicit Windows fallback.
            if transcriber.ready():
                transcriber.warm(task)
            for name in PROMPTS:
                task.check()
                if self._busy or self._recording or not self.store.setting("speech_enabled"):
                    break
                if os.name == "nt":
                    self._prepare_prompt(name, task, signals)

        job = Job(warm)
        self._warm_jobs.append(job)

        def finished():
            if job in self._warm_jobs:
                self._warm_jobs.remove(job)
            self.settingsChanged.emit()

        job.signals.finished.connect(finished)
        self.pool.start(job)

    def _acknowledge(self, task):
        if (self._shutting_down or self._task is not task or task.cancelled.is_set()
                or task.voice_acknowledged or task.voice_action_announced or self._pending_approval
                or not self.store.setting("speech_enabled") or not self.store.setting("quick_acknowledgment")):
            return
        cached, engine = self._prompt_path("receipt")
        # Never hold up transcription/reasoning to synthesize a receipt.
        if not self.prompt_cache.ready(cached):
            return
        path = self._speech_path()
        try:
            shutil.copyfile(cached, path)
        except OSError:
            path.unlink(missing_ok=True)
            return
        task.voice_acknowledged = True
        self._voice_engine_used = engine
        self._queue_audio(str(path), task, threading.Event())

    @staticmethod
    def _wait_for_audio(completed, task, timeout):
        deadline = time.monotonic() + timeout
        while not completed.wait(0.05):
            task.check()
            if time.monotonic() >= deadline:
                raise ValueError("Voice playback did not finish. Check Settings > Test voice, then retry.")
        task.check()
        if not getattr(completed, "played", False):
            raise ValueError("Voice playback could not finish. Check Settings > Test voice, then retry.")

    def _announce_action(self, name, task, signals):
        task.voice_action_announced = True
        signals.progress.emit(PROMPTS[name])
        path = self._speech_path()
        completed = threading.Event()
        try:
            cached = self._prepare_prompt(name, task, signals)
            if cached:
                shutil.copyfile(cached, path)
            else:
                self._local_voice(PROMPTS[name], task, path, signals)
            task.check()
            self.speechQueued.emit(str(path), task, completed)
            self._wait_for_audio(completed, task, 20)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @Slot(str, object)
    def _play_announcement(self, path, completed):
        self._play_audio(path)
        if self._audio_path is None:
            if self._task:
                self._task.cancelled.set()
            completed.set()
        else:
            self._audio_done = completed

    @Slot(str)
    def testVoice(self, speaker=""):
        if self._busy:
            self.toast.emit("Finish or stop the current task first.")
            return
        self.store.set_setting("speech_enabled", True)
        self.store.set_setting("speaker", speaker)
        self.settingsChanged.emit()
        self._task = TaskContext(self._ask)
        task = self._task

        def work(signals):
            signals.progress.emit("Preparing voice test")
            path = self._speech_path()
            try:
                self._local_voice("Hello, I'm Macooii. I'm ready when you are. Hold the microphone, speak naturally, and release when you're finished.", task, path, signals)
                task.check()
                self.audioReady.emit(str(path))
            except BaseException:
                path.unlink(missing_ok=True)
                raise

        self._start_job(work)

    @Slot(str)
    def _play_audio(self, path):
        self.stopAudio()
        self._begin_audio(path)

    @Slot(str, object, object)
    def _queue_audio(self, path, task, completed):
        if (self._shutting_down or task.cancelled.is_set() or self._task is not task
                or not self.store.setting("speech_enabled")):
            Path(path).unlink(missing_ok=True)
            completed.set()
            return
        self._audio_queue.append((path, task, completed))
        self._advance_audio()

    def _advance_audio(self):
        if self._audio_path is not None:
            return
        while self._audio_queue:
            path, task, completed = self._audio_queue.pop(0)
            if task.cancelled.is_set() or self._task is not task or self._shutting_down:
                Path(path).unlink(missing_ok=True)
                completed.set()
                continue
            self._begin_audio(path, task, completed)
            if self._audio_path is not None:
                return
            completed.set()

    def _begin_audio(self, path, task=None, completed=None):
        if self._task and self._task.cancelled.is_set():
            Path(path).unlink(missing_ok=True)
            return
        selected = self.store.setting("speaker")
        outputs = QMediaDevices.audioOutputs()
        device = next((output for output in outputs if bytes(output.id().toHex()).decode("ascii") == selected), None) if selected else QMediaDevices.defaultAudioOutput()
        if device is None or device.isNull():
            Path(path).unlink(missing_ok=True)
            self.toast.emit("Voice output unavailable. Select working speakers in Settings, then Test voice.")
            return
        self.audio_output.setDevice(device)
        self.audio_output.setVolume(1.0)
        self.audio_output.setMuted(False)
        self._audio_path = Path(path)
        self._audio_task = task
        self._audio_done = completed
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _media_status(self, status):
        if status in {QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia}:
            self._finish_audio(status == QMediaPlayer.MediaStatus.EndOfMedia)
            QTimer.singleShot(0, self._advance_audio)

    def _playback_error(self, error, message):
        self.toast.emit("Voice playback failed: " + message)
        self._finish_audio(False)
        QTimer.singleShot(0, self._advance_audio)

    @Slot()
    def stopAudio(self):
        queued, self._audio_queue = self._audio_queue, []
        self._finish_audio(False)
        for path, _task, completed in queued:
            Path(path).unlink(missing_ok=True)
            completed.set()

    def _finish_audio(self, played):
        self.player.stop()
        self.player.setSource(QUrl())
        if self._audio_done:
            completed = self._audio_done
            self._audio_done = None
            completed.played = played
            # Finish processing the audio event before releasing the action worker.
            QTimer.singleShot(0, completed.set)
        if self._audio_path:
            try:
                self._audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._audio_path = None
        self._audio_task = None

    @Slot()
    def toggleSpeech(self):
        enabled = not self.store.setting("speech_enabled")
        self.store.set_setting("speech_enabled", enabled)
        if not enabled:
            self.stopAudio()
            if self._task_answered and self._busy and self._task:
                self._task.cancelled.set()
                self._approval_choice = "decline"
                self._approval_event.set()
        self.settingsChanged.emit()
        if enabled:
            self.prepareVoice()

    @Slot()
    def cancel(self):
        self._microphone_test = False
        self._talk_held = False
        self._record_after_cancel = False
        self._pending_voice_text = ""
        if self._task:
            self._task.cancelled.set()
        self._approval_choice = "decline"
        self._approval_event.set()
        self._pending_approval = {}
        self.approvalChanged.emit()
        self.stopAudio()
        if self._recording:
            self.mic_timer.stop()
            self.recorder.stop()
            self._recording = False
            self.stateChanged.emit()
        if self._busy:
            self._set_status("Stopping · waiting for the current operation to return")

    @Slot()
    def startRecording(self):
        if self._recording:
            return
        self._talk_held = True
        self._microphone_test = False
        if self._busy:
            if self.store.setting("voice_conversation"):
                self.cancel()
                self._talk_held = self._record_after_cancel = True
                self._set_status("Interrupting · keep holding to start speaking")
            else:
                self._talk_held = False
            return
        if not self.speechReady:
            self._talk_held = False
            self.toast.emit("Download the speech model in Settings first.")
            return
        self.stopAudio()
        self._recognition_feedback = ""
        self.recognitionChanged.emit()
        try:
            self.recorder.start(self.store.setting("microphone"))
            self._recording = True
            self.mic_timer.start()
            self.stateChanged.emit()
            self._set_status("Listening · " + getattr(self.recorder, "input_name", "Selected microphone") + " · release to transcribe")
        except Exception:
            self.toast.emit("Microphone unavailable. Check Windows microphone access and your default input device.")

    @Slot()
    def stopRecording(self):
        self._talk_held = False
        self._record_after_cancel = False
        if not self._recording:
            return
        self.mic_timer.stop()
        test_capture = self._microphone_test
        self._microphone_test = False
        try:
            audio = self.recorder.stop()
        except Exception:
            self._recording = False
            self.stateChanged.emit()
            self._set_status("Ready when you are")
            self.toast.emit("Recording stopped because the microphone became unavailable.")
            return
        self._recording = False
        quality = dict(getattr(self.recorder, "last_quality", {}))
        self.stateChanged.emit()
        self._task = TaskContext(self._ask)
        task = self._task

        def work(signals):
            signals.progress.emit("Transcribing locally · English / Taglish")
            return self.transcriber.transcribe(audio, self.store.setting("language"), task)

        def received(text):
            if text:
                uncertain = bool(getattr(self.transcriber, "last_result", {}).get("needs_review"))
                issues = []
                if test_capture:
                    issues.append("Microphone test: review only")
                if quality.get("clipping"):
                    issues.append("The microphone audio was distorted")
                if quality.get("dropped_audio"):
                    issues.append("The microphone dropped audio")
                if quality.get("rms_db", 0) < -42:
                    issues.append("The microphone signal was quiet")
                if uncertain:
                    issues.append("Recognition is uncertain")
                if self.store.setting("voice_conversation") and not issues:
                    self._pending_voice_text = text
                else:
                    self.transcriptReady.emit(text)
                    self._recognition_feedback = (". ".join(issues) + ". Review the transcript before sending.") if issues else "Transcript ready. Review it, then send."
                    self.recognitionChanged.emit()
                    self.toast.emit(self._recognition_feedback)
            else:
                self.toast.emit("No speech detected. Try a clearer recording.")

        self._start_job(work, received)
        if self.store.setting("voice_conversation") and not test_capture and len(audio) >= 1600:
            self._acknowledge(task)

    @Slot(str)
    def testMicrophone(self, selected=""):
        if self._busy or self._recording:
            return
        self.store.set_setting("microphone", selected)
        self.settingsChanged.emit()
        self.startRecording()
        if self._recording:
            self._microphone_test = True
            self.microphoneTestRequested.emit()
            self._set_status("Microphone test · " + getattr(self.recorder, "input_name", "Selected microphone") + " · speak for five seconds")
            QTimer.singleShot(5000, lambda: self.stopRecording() if self._recording and self._microphone_test else None)

    @Slot()
    def toggleVoiceConversation(self):
        if self._recording:
            return
        enabled = not self.store.setting("voice_conversation")
        self.store.set_setting("voice_conversation", enabled)
        self._pending_voice_text = ""
        if enabled:
            self.store.set_setting("speech_enabled", True)
        else:
            self._record_after_cancel = False
            self._talk_held = False
        self.settingsChanged.emit()
        self.toast.emit("Voice conversation on: release the microphone to send. Hold again to interrupt." if enabled else
                        "Voice conversation off: review each transcript before sending.")

    @Slot(str, str)
    def saveSettings(self, payload, api_key):
        if self._busy or self._recording:
            self.toast.emit("Finish the current task before changing settings.")
            return
        try:
            data = json.loads(payload)
            if data.get("provider") not in {"auto", "cloud", "local", "codex"}:
                raise ValueError("Choose a valid AI mode.")
            if data.get("speech_engine", "neural") not in {"neural", "windows"} or data.get("neural_voice", "bm_george") not in VOICES:
                raise ValueError("Choose a valid local voice.")
            speed = float(data.get("voice_speed", 1.0))
            if not 0.8 <= speed <= 1.2:
                raise ValueError("Choose a voice speed between 0.8 and 1.2.")
            if data.get("cloud_model") not in GEMINI_MODELS:
                raise ValueError("Choose a reviewed cloud model.")
            if data.get("language") not in {"auto", "en", "tl", "taglish"}:
                raise ValueError("Choose a valid speech language.")
            if data.get("whisper_model", self.store.setting("whisper_model")) not in SPEECH_MODELS:
                raise ValueError("Choose a supported speech recognition model.")
            if data.get("voice") not in {"Charon", "Kore", "Puck"}:
                raise ValueError("Choose a valid voice.")
            if data.get("local_compute") not in {"cpu", "auto"}:
                raise ValueError("Choose a valid local compute mode.")
            if data.get("open_shortcut") not in OPEN_SHORTCUTS or data.get("talk_shortcut") not in TALK_SHORTCUTS:
                raise ValueError("Choose valid shortcuts.")
            if not isinstance(data.get("microphone"), str) or len(data["microphone"]) > 500:
                raise ValueError("Choose a valid microphone.")
            for name in ("provider", "cloud_model", "language", "voice", "local_compute", "microphone",
                         "open_shortcut", "talk_shortcut"):
                self.store.set_setting(name, data[name])
            self.store.set_setting("speaker", str(data.get("speaker", "")))
            self.store.set_setting("speech_engine", data.get("speech_engine", "neural"))
            self.store.set_setting("neural_voice", data.get("neural_voice", "bm_george"))
            self.store.set_setting("voice_speed", speed)
            self.store.set_setting("voice_conversation", bool(data.get("voice_conversation", False)))
            self.store.set_setting("quick_acknowledgment", bool(data.get("quick_acknowledgment", True)))
            selected_model = data.get("whisper_model", self.store.setting("whisper_model"))
            if selected_model != self.transcriber.model_size:
                self.store.set_setting("whisper_model", selected_model)
                self.transcriber = Transcriber(self.store.root, self.store.setting("model_directory"), selected_model)
            for name in ("cloud_enabled", "speech_enabled", "cloud_speech"):
                self.store.set_setting(name, bool(data[name]))
            if api_key.strip():
                credentials.set_api_key(api_key)
                self._key_present = True
            self.settingsChanged.emit()
            self.toast.emit("Settings saved on this computer.")
            self.prepareVoice()
        except Exception:
            self.toast.emit("Settings could not be saved. Check the selected options and Windows credential storage.")

    @Slot()
    def removeKey(self):
        if self._busy:
            return
        try:
            credentials.set_api_key("")
            self._key_present = False
            self.store.set_setting("cloud_enabled", False)
            self.settingsChanged.emit()
            self.toast.emit("API key removed. Cloud AI is disabled.")
        except Exception:
            self.toast.emit("Windows could not remove the stored credential.")

    @Slot()
    def addFolder(self):
        if self._busy:
            return
        value = QFileDialog.getExistingDirectory(None, "Approve a folder for Macooii")
        if value:
            folder = str(Path(value).resolve())
            folders = self.store.setting("folders")
            if folder not in folders:
                self.store.set_setting("folders", folders + [folder])
                self.settingsChanged.emit()

    @Slot(str)
    def removeFolder(self, folder):
        if self._busy:
            return
        self.store.set_setting("folders", [f for f in self.store.setting("folders") if f != folder])
        self.store.clear_index()
        self.settingsChanged.emit()

    @Slot()
    def chooseModelDirectory(self):
        if self._busy:
            return
        value = QFileDialog.getExistingDirectory(None, "Choose speech model storage")
        if value:
            self.store.set_setting("model_directory", str(Path(value).resolve()))
            self.transcriber = Transcriber(self.store.root, self.store.setting("model_directory"), self.store.setting("whisper_model"))
            self.settingsChanged.emit()

    @Slot()
    def addApp(self):
        if self._busy:
            return
        value, _ = QFileDialog.getOpenFileName(None, "Register an application", "", "Windows apps (*.exe)")
        if value:
            path = Path(value).resolve()
            apps = self.store.setting("apps")
            name = path.stem
            if name in apps and Path(apps[name]) != path:
                name += " (2)"
            apps[name] = str(path)
            self.store.set_setting("apps", apps)
            self.settingsChanged.emit()

    @Slot(str)
    def removeApp(self, name):
        if self._busy:
            return
        apps = self.store.setting("apps")
        apps.pop(name, None)
        self.store.set_setting("apps", apps)
        self.settingsChanged.emit()

    @Slot(str, str, str, result=str)
    def saveNote(self, title, body, note_id):
        if not title.strip() or not body.strip():
            self.toast.emit("Add a title and some text first.")
            return ""
        saved_id = self.store.save_note(title.strip()[:160], body[:50_000], note_id or None)
        self.dataChanged.emit()
        self.toast.emit("Note saved locally.")
        return saved_id

    @Slot(str)
    def deleteNote(self, note_id):
        if QMessageBox.question(None, "Delete note?", "Delete this note from Macooii?") == QMessageBox.StandardButton.Yes:
            self.store.delete_note(note_id)
            self.dataChanged.emit()

    @Slot(str)
    def exportNote(self, note_id):
        try:
            note = self.store.note(note_id)
            value, _ = QFileDialog.getSaveFileName(None, "Export note", "note.md", "Markdown (*.md);;Text (*.txt)")
            if value:
                path = Path(value)
                # QFileDialog requests overwrite confirmation. The exact path is chosen by the user.
                path.write_text("# " + note["title"] + "\n\n" + note["body"], encoding="utf-8")
                self.toast.emit("Note exported.")
        except (OSError, ValueError):
            self.toast.emit("The note could not be exported to that location.")

    @Slot(str, str)
    def saveMemory(self, body, memory_id):
        if body.strip():
            self.store.remember(body.strip()[:2000], memory_id or None)
            self.dataChanged.emit()
            self.toast.emit("Preference saved locally.")

    @Slot(str)
    def deleteMemory(self, memory_id):
        self.store.forget(memory_id)
        self.dataChanged.emit()

    @Slot()
    def clearHistory(self):
        if self._busy:
            return
        if QMessageBox.question(None, "Clear conversation?", "Delete local conversation history?") == QMessageBox.StandardButton.Yes:
            self.store.clear_history()
            self._cards = []
            self.messagesChanged.emit()
            self.cardsChanged.emit()

    @Slot(str)
    def openUrl(self, value):
        url = QUrl(value)
        if url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)

    @Slot()
    def refreshStatus(self):
        if self._busy:
            return
        self._task = TaskContext(self._ask)

        def received(value):
            self._ollama = value
            self.settingsChanged.emit()

        self._start_job(lambda signals: ollama_status(), received)

    @Slot()
    def downloadLocalModel(self):
        if self._busy:
            return
        self._task = TaskContext(self._ask)
        task = self._task

        def work(signals):
            if not ollama_status()["running"]:
                raise ValueError("Install and start Ollama first, then download the local model.")
            model_root = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama"))
            model_root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(model_root).free < 8 * 1024**3:
                raise ValueError("Keep at least 8 GB free on the Ollama model drive before downloading.")
            with httpx.Client(timeout=httpx.Timeout(60, connect=5), trust_env=False) as client:
                with client.stream("POST", "http://127.0.0.1:11434/api/pull",
                                   json={"model": LOCAL_MODEL, "stream": True}) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        task.check()
                        if not line:
                            continue
                        data = json.loads(line)
                        if "error" in data:
                            raise ValueError("Ollama could not download the model. Check its connection and storage.")
                        total = data.get("total", 0)
                        percent = f" · {int(data.get('completed', 0) / total * 100)}%" if total else ""
                        signals.progress.emit("Downloading Qwen3 4B" + percent)
            return ollama_status()

        def received(value):
            self._ollama = value
            self.settingsChanged.emit()
            self.toast.emit("Local AI model is ready.")

        self._start_job(work, received)

    @Slot()
    def downloadSpeechModel(self):
        if self._busy:
            return
        self._task = TaskContext(self._ask)
        task = self._task

        def work(signals):
            destination = self.transcriber.cache
            destination.mkdir(parents=True, exist_ok=True)
            needed = 5 if self.transcriber.model_size == "large-v3-turbo" else 3
            if shutil.disk_usage(destination).free < needed * 1024**3:
                raise ValueError(f"Keep at least {needed} GB free on the speech model drive before downloading.")
            signals.progress.emit("Downloading multilingual speech model · " + ("about 1.6 GB" if self.transcriber.model_size == "large-v3-turbo" else "about 500 MB"))
            args = [sys.executable, "--download-speech", str(destination)] if getattr(sys, "frozen", False) else [
                sys.executable, "-m", "macooii.model_setup", str(destination)]
            args.append(self.transcriber.model_size)
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen(args, stdout=log, stderr=log, creationflags=flags)
                try:
                    while process.poll() is None:
                        task.check()
                        time.sleep(0.1)
                    if process.returncode:
                        raise ValueError("Speech model download failed. Check internet access and available storage, then retry.")
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
            return True

        def received(value):
            self.settingsChanged.emit()
            self.toast.emit("Speech model ready. Hold the microphone button to speak.")
            QTimer.singleShot(0, self.prepareVoice)

        self._start_job(work, received)

    def shutdown(self):
        self._shutting_down = True
        if self._warm_task:
            self._warm_task.cancelled.set()
        self.mic_timer.stop()
        self.capture_timer.stop()
        self._browser_capture = {}
        self.cancel()
        self.player.stop()
        self.stopAudio()
        self.browser_actions.close()
        close = getattr(self.engine, "close", None)
        if close:
            close()


