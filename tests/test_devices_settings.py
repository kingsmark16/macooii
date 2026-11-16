import json

import pytest

from macooii.bridge import Bridge
from macooii.speech import Recorder, microphones


def test_microphone_enumeration_filters_outputs(monkeypatch):
    import sounddevice
    monkeypatch.setattr(sounddevice, "query_hostapis", lambda: [{"name": "WASAPI"}])
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [
        {"name": "Speakers", "hostapi": 0, "max_input_channels": 0},
        {"name": "USB microphone", "hostapi": 0, "max_input_channels": 1}])
    choices = microphones()
    assert choices[0]["name"] == ""
    assert len(choices) == 2
    assert choices[1]["id"] == 1
    assert "USB microphone" in choices[1]["label"]


def test_missing_selected_microphone_does_not_record_another(monkeypatch):
    monkeypatch.setattr("macooii.speech.microphones", lambda: [{"id": -1, "name": "", "label": "Default"}])
    with pytest.raises(ValueError, match="no longer available"):
        Recorder().start("Removed USB microphone")


def test_preferences_include_mic_compute_and_shortcuts(qapp, store):
    bridge = Bridge(store)
    settings = store.settings()
    settings.update(microphone="USB microphone · WASAPI", open_shortcut="Ctrl+Alt+K",
                    talk_shortcut="Ctrl+Alt+V", local_compute="cpu")
    bridge.saveSettings(json.dumps(settings), "")
    assert store.setting("microphone") == "USB microphone · WASAPI"
    assert store.setting("open_shortcut") == "Ctrl+Alt+K"
    assert store.setting("talk_shortcut") == "Ctrl+Alt+V"
    # A saved device remains visible until refreshed, rather than silently reverting to default.
    assert bridge.microphoneChoices[-1]["name"] == "USB microphone · WASAPI"
    bridge.shutdown()
