"""Local neural speech with explicitly downloaded, checksum-verified Kokoro assets."""
from __future__ import annotations

import hashlib
import threading
import wave
from pathlib import Path

import httpx

from .privacy import TaskContext

VOICES = {"bm_george": "George · British male", "bm_lewis": "Lewis · British male",
          "am_michael": "Michael · American male", "af_heart": "Heart · American female"}
ASSETS = {
    "kokoro-v1.0.onnx": (325505369, "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"


class NeuralVoice:
    def __init__(self, root: Path):
        self.folder = root / "models/neural-voice"
        self.model = None
        self.lock = threading.Lock()

    def ready(self):
        return all((self.folder / name).is_file() and (self.folder / name).stat().st_size == size
                   for name, (size, _) in ASSETS.items())

    def download(self, task: TaskContext, progress):
        self.folder.mkdir(parents=True, exist_ok=True)
        for name, (size, digest) in ASSETS.items():
            task.check()
            target = self.folder / name
            if target.is_file():
                with target.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() == digest:
                        continue
            temporary = self.folder / (name + ".part")
            try:
                received = 0
                checksum = hashlib.sha256()
                with httpx.Client(timeout=60, follow_redirects=True, trust_env=False) as client:
                    with client.stream("GET", BASE_URL + name) as response:
                        response.raise_for_status()
                        with temporary.open("wb") as stream:
                            for chunk in response.iter_bytes(256 * 1024):
                                task.check()
                                received += len(chunk)
                                if received > size:
                                    raise ValueError("Neural voice download exceeded the expected size.")
                                stream.write(chunk)
                                checksum.update(chunk)
                                label = "voice styles" if name.startswith("voices") else "voice model"
                                progress(f"Downloading {label} · {received * 100 // size}%")
                if received != size or checksum.hexdigest() != digest:
                    raise ValueError("Neural voice checksum did not match. Retry the download.")
                task.check()
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        return True

    def _load_model(self):
        if self.model is None:
            import onnxruntime as ort
            from kokoro_onnx import Kokoro

            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(self.folder / "kokoro-v1.0.onnx"), sess_options=options,
                                           providers=["CPUExecutionProvider"])
            self.model = Kokoro.from_session(session, str(self.folder / "voices-v1.0.bin"))

    def warm(self, task: TaskContext):
        """Load the model even when every fixed prompt is already cached."""
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            if not self.ready():
                raise ValueError("Download the natural voice model in Settings first.")
            self._load_model()
            task.check()
        finally:
            self.lock.release()

    def speak(self, text: str, voice: str, speed: float, task: TaskContext, output: Path):
        if voice not in VOICES or not 0.8 <= speed <= 1.2:
            raise ValueError("Choose a supported natural voice and speed.")
        if not self.ready():
            raise ValueError("Download the natural voice model in Settings first.")
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            self._load_model()
            task.check()
            samples, rate = self.model.create(text, voice=voice, speed=speed,
                                              lang="en-gb" if voice.startswith("bm_") else "en-us")
            task.check()
            import numpy as np

            if not samples.size or not np.isfinite(samples).all():
                raise ValueError("The neural voice returned invalid audio.")
            pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
            with wave.open(str(output), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(rate)
                stream.writeframes(pcm.tobytes())
            return output
        finally:
            self.lock.release()
