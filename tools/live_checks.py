"""Opt-in live smoke checks. Never record a microphone or use private files/API keys."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import httpx

from macooii.config import LOCAL_MODEL, data_dir
from macooii.privacy import TaskContext
from macooii.providers import OllamaProvider


def pull():
    last_percent = -10
    with httpx.Client(timeout=120, trust_env=False) as client:
        with client.stream("POST", "http://127.0.0.1:11434/api/pull", json={"model": LOCAL_MODEL, "stream": True}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                item = json.loads(line)
                if "error" in item:
                    raise RuntimeError(item["error"])
                if item.get("total"):
                    percent = int(item.get("completed", 0) / item["total"] * 100)
                    if percent >= last_percent + 10:
                        print(f"Model download: {percent}%", flush=True)
                        last_percent = percent
                elif item.get("status") == "success":
                    print("Model download complete", flush=True)


def model():
    started = time.monotonic()
    response = OllamaProvider().reply([{"role": "user", "content": "In one sentence in Taglish, explain what a personal assistant does."}], [], TaskContext(lambda *args: "decline"))
    print(json.dumps({"model_seconds": round(time.monotonic() - started, 2), "reply": response.text}, ensure_ascii=False), flush=True)


def speech():
    import pythoncom
    import win32com.client

    from macooii.speech import Transcriber

    destination = Path("output/voice-check.wav").resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    try:
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 22  # 22.05 kHz, 16-bit mono
        stream.Open(str(destination), 3)
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.AudioOutputStream = stream
        voice.Speak("Macooii, open Notepad and save a note about my project.")
        stream.Close()
    finally:
        pythoncom.CoUninitialize()
    from faster_whisper.audio import decode_audio
    audio = decode_audio(str(destination), sampling_rate=16000)
    started = time.monotonic()
    transcriber = Transcriber(data_dir())
    result = transcriber.transcribe(audio, "en", TaskContext(lambda *args: "decline"))
    cold = round(time.monotonic() - started, 2)
    started = time.monotonic()
    transcriber.transcribe(audio, "en", TaskContext(lambda *args: "decline"))
    print(json.dumps({"cold_transcription_seconds": cold,
                      "warm_transcription_seconds": round(time.monotonic() - started, 2), "text": result}), flush=True)


def agent():
    from macooii.engine import Engine
    from macooii.storage import Store

    with tempfile.TemporaryDirectory(prefix="macooii-agent-check-") as directory:
        store = Store(Path(directory))
        store.set_setting("provider", "local")
        engine = Engine(store, lambda: "")
        cases = ["Save this as a note. Title: English diagnostic. Body: The project is ready.",
                 "I-save mo ito bilang note. Title: Taglish diagnostic. Body: Tapos na ang project."]
        for index, request in enumerate(cases, 1):
            started = time.monotonic()
            outcome = engine.run(request, TaskContext(lambda *args: "decline"), lambda text: print(text, flush=True))
            passed = len(store.notes()) == index
            print(json.dumps({"case": index, "passed": passed, "seconds": round(time.monotonic() - started, 2),
                              "reply": outcome.text}, ensure_ascii=True), flush=True)
            if not passed:
                raise RuntimeError("Local agent did not complete the requested note action")


if __name__ == "__main__":
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=["pull", "model", "speech", "agent"])
    args = parser.parse_args()
    {"pull": pull, "model": model, "speech": speech, "agent": agent}[args.check]()
