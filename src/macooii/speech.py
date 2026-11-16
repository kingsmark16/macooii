from __future__ import annotations

import base64
import os
import re
import threading
import wave
from pathlib import Path

import httpx

from .config import SPEECH_MODELS, TTS_MODELS
from .privacy import Cancelled, TaskContext
from .providers import ProviderError, safe_http_error


def microphones() -> list[dict]:
    import sounddevice as sd
    hosts = sd.query_hostapis()
    result = [{"id": -1, "name": "", "label": "Windows default input"}]
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            name = f"{device['name']} · {hosts[device['hostapi']]['name']}"
            result.append({"id": index, "name": name, "label": name})
    return result[:1] + sorted(result[1:], key=lambda item: ("WASAPI" not in item["label"], item["label"]))


def prepare_audio(audio):
    """Reject missing signal, remove DC and apply bounded gain without clipping."""
    import numpy as np
    data = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(data) < 1600:
        raise ValueError("Hold the microphone button a little longer, then speak.")
    if not np.isfinite(data).all():
        raise ValueError("The microphone returned invalid audio. Try another input device.")
    data = data - np.mean(data)
    rms = float(np.sqrt(np.mean(data * data)))
    if rms < 0.0003:
        raise ValueError("The microphone signal is too quiet. Move closer or select the correct microphone in Settings.")
    peak = float(np.max(np.abs(data)))
    gain = min(4.0, 0.1 / rms, 0.98 / max(peak, 1e-6))
    return np.ascontiguousarray(data * gain, dtype=np.float32)


def resample_microphone(audio, sample_rate):
    import av
    import numpy as np
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 2:
        # Avoid cancellation from opposite-phase stereo microphone channels.
        channel = int(np.argmax(np.mean(data * data, axis=0))) if len(data) else 0
        data = data[:, channel]
    data = np.ascontiguousarray(data.reshape(-1))
    if sample_rate == 16000 or not len(data):
        return data
    frame = av.AudioFrame.from_ndarray(data[None, :], format="flt", layout="mono")
    frame.sample_rate = sample_rate
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    frames = resampler.resample(frame) + resampler.resample(None)
    return np.concatenate([item.to_ndarray().reshape(-1) for item in frames]).astype(np.float32)


class Recorder:
    def __init__(self):
        self.stream = None
        self.frames = []
        self.samples = 0
        self.sample_rate = 16000
        self.level = 0.0
        self.overflows = 0
        self.last_quality = {}
        self.input_name = ""

    def start(self, selected: str = ""):
        import sounddevice as sd
        device_id = None
        if selected:
            match = next((device for device in microphones() if device["name"] == selected), None)
            if match is None:
                raise ValueError("The selected microphone is no longer available.")
            device_id = match["id"]
        else:
            # Prefer the current WASAPI default, rather than the legacy MME mapper.
            host = next((host for host in sd.query_hostapis() if host["name"] == "Windows WASAPI"), None)
            if host and host["default_input_device"] >= 0:
                device_id = host["default_input_device"]
        device = sd.query_devices(device_id, "input")
        self.input_name = str(device.get("name", "Selected microphone"))
        self.sample_rate = int(device["default_samplerate"])
        channels = 1
        try:
            sd.check_input_settings(device=device_id, samplerate=self.sample_rate, channels=channels, dtype="float32")
        except Exception:
            channels = min(2, int(device["max_input_channels"]))
            sd.check_input_settings(device=device_id, samplerate=self.sample_rate, channels=channels, dtype="float32")
        self.frames = []
        self.samples = 0
        self.level = 0.0
        self.overflows = 0
        self.last_quality = {}

        def callback(data, frames, time_info, status):
            # At most 60 seconds of audio is held in RAM, never written to the chat database.
            import numpy as np
            if getattr(status, "input_overflow", False):
                self.overflows += 1
            self.level = float(np.max(np.abs(data))) if data.size else 0.0
            remaining = self.sample_rate * 60 - self.samples
            if remaining > 0:
                self.frames.append(data[:remaining].copy())
                self.samples += min(frames, remaining)

        self.stream = sd.InputStream(device=device_id, samplerate=self.sample_rate, channels=channels,
                                     latency="high", blocksize=0,
                                     dtype="float32", callback=callback)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            self.stream = None
            raise

    def stop(self):
        import numpy as np
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
        raw = np.concatenate(self.frames) if self.frames else np.array([], dtype=np.float32)
        self.frames = []
        peak = float(np.max(np.abs(raw))) if raw.size else 0.0
        rms = float(np.sqrt(np.mean(raw * raw))) if raw.size else 0.0
        self.last_quality = {"peak": peak, "rms_db": round(20 * float(np.log10(max(rms, 1e-8))), 1),
                             "clipping": bool(raw.size and np.mean(np.abs(raw) >= 0.99) > 0.01),
                             "dropped_audio": self.overflows > 0, "sample_rate": self.sample_rate}
        self.level = 0.0
        return resample_microphone(raw, self.sample_rate)


class Transcriber:
    def __init__(self, root: Path, model_directory: str = "", model_size: str = "small"):
        self.root = root
        self.cache = Path(model_directory) if model_directory else root / "models"
        self.model = None
        self.lock = threading.Lock()
        if model_size not in SPEECH_MODELS:
            raise ValueError("Select a supported speech recognition model.")
        self.model_size = model_size
        self.cpu_threads = max(1, min(6, (os.cpu_count() or 8) // 2))
        self.last_result = {}

    def model_path(self):
        matches = sorted(self.cache.glob(f"models--*--faster-whisper-{self.model_size}/snapshots/*/model.bin"),
                         key=lambda path: path.stat().st_mtime, reverse=True)
        return next((path.parent for path in matches if (path.parent / "config.json").is_file()
                     and (path.parent / "tokenizer.json").is_file()), None)

    def ready(self) -> bool:
        return self.model_path() is not None

    def download(self):
        from .model_setup import download
        download(str(self.cache), self.model_size)

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            try:
                folder = self.model_path()
                if folder is None:
                    raise ValueError("Model is not ready")
                self.model = WhisperModel(str(folder), device="cpu", compute_type="int8", cpu_threads=self.cpu_threads,
                                          download_root=str(self.cache), local_files_only=True)
            except Exception as exc:
                raise ValueError("Download the speech model in Settings before using push-to-talk.") from exc

    def warm(self, task: TaskContext):
        """Load existing local assets without opening the microphone or downloading anything."""
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            self._load_model()
            task.check()
        finally:
            self.lock.release()

    def transcribe(self, audio, language: str, task: TaskContext) -> str:
        self.last_result = {}
        audio = prepare_audio(audio)
        task.check()
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            self._load_model()
            selected = "tl" if language == "taglish" else None if language == "auto" else language
            segments, info = self.model.transcribe(audio, language=selected,
                task="transcribe", vad_filter=True, beam_size=5, temperature=0.0,
                condition_on_previous_text=False, word_timestamps=True,
                vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 400, "threshold": 0.35},
                hotwords="Macooii, Chrome, YouTube, Facebook, Notepad",
                initial_prompt="Taglish: Filipino at English, mixed naturally." if language == "taglish" else None)
            parts = []
            scores, words = [], []
            for segment in segments:
                task.check()
                parts.append(segment.text)
                scores.append(segment.avg_logprob)
                words.extend(word.probability for word in (segment.words or []))
            confidence = sum(words) / len(words) if words else 0.0
            uncertain = bool(parts) and (confidence < 0.6 or any(score < -0.9 for score in scores)
                or (language == "auto" and (info.language not in {"en", "tl"} or info.language_probability < 0.5)))
            self.last_result = {"language": info.language, "confidence": round(confidence, 2), "needs_review": uncertain}
        finally:
            self.lock.release()
        task.check()
        return " ".join(parts).strip()


def speech_excerpt(text: str) -> str:
    text = text.split("\n\nSources\n")[0]
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[[^\]]*\]|[`*#]", "", text)
    text = text.strip()
    if len(text) > 600:
        text = text[:600].rsplit(" ", 1)[0] + ". The full answer is on screen."
    return text


def cloud_speech(text: str, key: str, model: str, voice: str, task: TaskContext, output: Path) -> Path:
    if model not in TTS_MODELS:
        raise ProviderError("Speech model is outside the reviewed model list.")
    task.check()
    payload = {"contents": [{"parts": [{"text": text,
                "speech_metadata": {"speaker": "Macooii", "style": "Calm, warm, clear personal assistant."}}]}],
               "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                   "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    with httpx.Client(timeout=45, trust_env=False) as client:
        response = client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                               headers={"x-goog-api-key": key}, json=payload)
    task.check()
    safe_http_error(response, "Cloud speech")
    for part in response.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData")
        if inline:
            audio = base64.b64decode(inline["data"])
            if audio[:4] == b"RIFF":
                output.write_bytes(audio)
            else:
                mime = inline.get("mimeType", "")
                match = re.search(r"rate=(\d+)", mime)
                rate = int(match[1]) if match else 24000
                with wave.open(str(output), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(rate)
                    stream.writeframes(audio)
            return output
    raise ProviderError("Cloud speech returned no audio.")


def windows_speech(text: str, task: TaskContext, output: Path) -> Path:
    import pythoncom
    from win32com.client.dynamic import Dispatch
    pythoncom.CoInitialize()
    stream = None
    opened = False
    try:
        task.check()
        # Late binding avoids generated COM-wrapper imports failing in the packaged app.
        stream = Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 22
        stream.Open(str(output), 3)
        opened = True
        voice = Dispatch("SAPI.SpVoice")
        voice.AudioOutputStream = stream
        voice.Volume = 100
        voice.Speak(text, 1 | 16)  # asynchronous, plain text (never interpret reply text as XML)
        while not voice.WaitUntilDone(50):
            if task.cancelled.is_set():
                voice.Speak("", 3)
                task.check()
        task.check()
    except Cancelled:
        raise
    except Exception as exc:
        raise ValueError("Windows speech generation failed. Restart Macooii and try Settings → Test voice.") from exc
    finally:
        if stream is not None and opened:
            stream.Close()
        pythoncom.CoUninitialize()
    with wave.open(str(output), "rb") as audio:
        if audio.getnframes() == 0:
            raise ValueError("Windows speech generated an empty recording.")
    return output
