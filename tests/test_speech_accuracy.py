from types import SimpleNamespace

import numpy as np
import pytest

from macooii.bridge import Bridge
from macooii.privacy import TaskContext
from macooii.speech import Recorder, Transcriber, prepare_audio, resample_microphone


def test_native_rate_resampling_preserves_duration_and_pitch_without_phase_cancellation():
    time = np.arange(48000, dtype=np.float32) / 48000
    signal = np.sin(2 * np.pi * 1000 * time) * 0.2
    result = resample_microphone(np.stack([signal, -signal], axis=1), 48000)
    assert abs(len(result) - 16000) < 2
    assert np.sqrt(np.mean(result * result)) > 0.1
    assert abs(np.argmax(np.abs(np.fft.rfft(result))) - 1000) < 2


def test_audio_conditioning_rejects_silence_and_removes_dc_without_clipping():
    with pytest.raises(ValueError, match="too quiet"):
        prepare_audio(np.zeros(16000, dtype=np.float32))
    signal = 0.2 + np.sin(np.arange(16000) * 0.15).astype(np.float32) * 0.01
    result = prepare_audio(signal)
    assert abs(np.mean(result)) < 1e-5
    assert np.sqrt(np.mean(result * result)) > 0.02
    assert np.max(np.abs(result)) <= 0.98


def test_recorder_uses_native_wasapi_default_and_reports_dropped_audio(monkeypatch):
    import sounddevice as sd

    options = {}
    monkeypatch.setattr(sd, "query_hostapis", lambda: [{"name": "Windows WASAPI", "default_input_device": 9}])
    monkeypatch.setattr(sd, "query_devices", lambda *args: {"default_samplerate": 48000, "max_input_channels": 2})
    monkeypatch.setattr(sd, "check_input_settings", lambda **kwargs: None)

    def stream(**kwargs):
        options.update(kwargs)
        return SimpleNamespace(start=lambda: None, stop=lambda: None, close=lambda: None)

    monkeypatch.setattr(sd, "InputStream", stream)
    recorder = Recorder()
    recorder.start()
    data = np.sin(np.arange(48000) * 0.1).astype(np.float32).reshape(-1, 1) * 0.1
    options["callback"](data, len(data), None, SimpleNamespace(input_overflow=True))
    result = recorder.stop()
    assert options["device"] == 9 and options["samplerate"] == 48000
    assert len(result) == 16000
    assert recorder.last_quality["dropped_audio"]


def test_taglish_transcription_preserves_transcribe_task_and_marks_uncertain_words(tmp_path):
    transcriber = Transcriber(tmp_path)
    options = {}

    def transcribe(audio, **kwargs):
        options.update(kwargs)
        segment = SimpleNamespace(text="Buksan ang Chrome", avg_logprob=-1.2,
                                  words=[SimpleNamespace(probability=0.3)])
        return iter([segment]), SimpleNamespace(language="tl", language_probability=1.0)

    transcriber.model = SimpleNamespace(transcribe=transcribe)
    text = transcriber.transcribe(np.sin(np.arange(16000) * 0.1).astype(np.float32) * 0.1, "taglish", TaskContext(lambda *args: "decline"))
    assert text == "Buksan ang Chrome"
    assert options["language"] == "tl" and options["task"] == "transcribe"
    assert transcriber.last_result["needs_review"]


@pytest.mark.parametrize("reason", ["uncertain", "clipping", "dropped_audio", "test"])
def test_poor_or_test_transcripts_are_not_auto_sent(qapp, qtbot, store, monkeypatch, reason):
    store.set_setting("voice_conversation", True)
    bridge = Bridge(store)
    bridge._recording = True
    bridge._microphone_test = reason == "test"
    bridge.recorder.last_quality = {reason: True} if reason != "uncertain" else {}
    bridge.transcriber.last_result = {"needs_review": reason == "uncertain"}
    monkeypatch.setattr(bridge.recorder, "stop", lambda: np.ones(16000))
    monkeypatch.setattr(bridge.transcriber, "transcribe", lambda *args: "Open Chrome")
    bridge.engine = SimpleNamespace(run=lambda *args: pytest.fail("Uncertain command was auto-executed"))
    transcripts = []
    bridge.transcriptReady.connect(transcripts.append)
    bridge.stopRecording()
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    qtbot.wait(50)
    assert transcripts == ["Open Chrome"]
    assert not store.messages()
    assert "review" in bridge.recognitionFeedback.casefold()
    bridge.shutdown()


def test_model_download_reuses_complete_ranges_and_verifies_hash(tmp_path):
    import hashlib

    from macooii.model_setup import parallel_model

    payload = b"public model fixture"
    parts = tmp_path / "download-parts"
    parts.mkdir()
    (parts / "000000000000.chunk").write_bytes(payload)
    client = SimpleNamespace(stream=lambda *args, **kwargs: pytest.fail("Downloaded a complete range twice"))
    target = tmp_path / "model.bin"
    parallel_model(client, "https://example.com/model", target, len(payload), hashlib.sha256(payload).hexdigest())
    assert target.read_bytes() == payload
    assert not parts.exists()


def test_corrupt_model_ranges_cannot_become_a_ready_model(tmp_path):
    import hashlib

    from macooii.model_setup import parallel_model

    parts = tmp_path / "download-parts"
    parts.mkdir()
    (parts / "000000000000.chunk").write_bytes(b"corrupt")
    client = SimpleNamespace(stream=lambda *args, **kwargs: pytest.fail("Fixture already has a range"))
    with pytest.raises(ValueError, match="checksum"):
        parallel_model(client, "https://example.com/model", tmp_path / "model.bin", 7, hashlib.sha256(b"correct").hexdigest())
    assert not (tmp_path / "model.bin").exists()
