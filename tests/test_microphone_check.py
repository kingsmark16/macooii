import io
import wave
from types import SimpleNamespace

import numpy as np

from macooii.microphone_check import Compare, MicrophoneCheck, wav_bytes
from macooii.privacy import TaskContext


def test_replay_wav_preserves_sample_rate_and_duration():
    audio = np.sin(np.arange(16000) * 0.2).astype(np.float32) * 0.1
    with wave.open(io.BytesIO(wav_bytes(audio))) as stream:
        assert stream.getframerate() == 16000
        assert stream.getnframes() == 16000
        assert stream.getnchannels() == 1
        decoded = np.frombuffer(stream.readframes(16000), dtype="<i2") / 32767
    assert np.max(np.abs(decoded - audio)) < 0.00004


def test_comparison_uses_same_audio_without_preprocessing_or_hints(qapp):
    audio = np.sin(np.arange(16000) * 0.2).astype(np.float32) * 0.03
    calls, outputs = [], []

    def baseline(data, **kwargs):
        calls.append((data.copy(), kwargs))
        return iter([SimpleNamespace(text="Open YouTube")]), None

    transcriber = SimpleNamespace(transcribe=lambda *args: "Open YouTube", model=SimpleNamespace(transcribe=baseline))
    job = Compare(transcriber, audio, TaskContext(lambda *args: "decline"))
    job.signals.result.connect(lambda kind, text: outputs.append((kind, text)))
    job.run()
    assert outputs == [("normal", "Open YouTube"), ("baseline", "Open YouTube")]
    assert np.array_equal(calls[0][0], audio)
    assert calls[0][1]["language"] == "en"
    assert calls[0][1]["vad_filter"] is False and calls[0][1]["hotwords"] is None


def test_diagnostic_audio_is_not_saved_automatically_and_discard_clears_it(qapp, store, monkeypatch):
    monkeypatch.setattr("macooii.microphone_check.data_dir", lambda: store.root)
    monkeypatch.setattr("macooii.microphone_check.microphones", lambda: [{"label": "Test default", "name": "", "id": -1}])
    window = MicrophoneCheck()
    window.accept_audio(np.zeros(16000, dtype=np.float32), {"sample_rate": 48000}, "Synthetic microphone")
    assert window.replay_button.isEnabled()
    assert not list(store.root.rglob("*.wav"))
    assert not store.messages()
    window.discard()
    assert window.audio is None
    assert not window.replay_button.isEnabled()
    assert not window.expiry.isActive()
    window.close()
