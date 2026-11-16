from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Macooii"
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.1-flash-lite")
TTS_MODELS = ("gemini-3.8-flash-lite-tts",)
LOCAL_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
OPEN_SHORTCUTS = ("Ctrl+Alt+J", "Ctrl+Alt+K", "Ctrl+Alt+L")
TALK_SHORTCUTS = ("Ctrl+Alt+Space", "Ctrl+Alt+V", "Ctrl+Alt+T")
SPEECH_MODELS = {"small": "Systran/faster-whisper-small",
                 "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo"}
DEFAULTS = {
    "provider": "auto",
    "cloud_enabled": False,
    "cloud_model": GEMINI_MODELS[0],
    "tts_model": TTS_MODELS[0],
    "voice": "Charon",
    "speech_enabled": True,
    "speech_engine": "neural",
    "neural_voice": "bm_george",
    "voice_speed": 1.0,
    "voice_conversation": False,
    "quick_acknowledgment": True,
    "speaker": "",
    "cloud_speech": True,
    "language": "auto",
    "folders": [],
    "apps": {},
    "history_days": 30,
    "whisper_model": "small",
    "model_directory": "",
    "ollama_model": LOCAL_MODEL,
    "local_compute": "cpu",
    "microphone": "",
    "open_shortcut": OPEN_SHORTCUTS[0],
    "talk_shortcut": TALK_SHORTCUTS[0],
}


def data_dir() -> Path:
    override = os.environ.get("MACOOII_DATA_DIR")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Macooii"


def resource_path(name: str) -> Path:
    return Path(__file__).parent / "ui" / name


def default_apps() -> dict[str, str]:
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    apps = {"Notepad": str(windows / "System32/notepad.exe"),
            "File Explorer": str(windows / "explorer.exe")}
    candidates = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"]
    for candidate in candidates:
        if candidate.is_file():
            apps["Chrome"] = str(candidate)
            break
    return {name: path for name, path in apps.items() if Path(path).is_file()}
