"""Short local speech chunks and a cache restricted to fixed public prompts."""
from __future__ import annotations

import hashlib
import re
import wave
from pathlib import Path

PROMPTS = {
    "receipt": "One moment.",
    "open_app": "Opening the application.",
    "open_website": "Opening the website.",
    "play_youtube": "Starting YouTube playback.",
    "control_media": "Updating playback.",
    "create_note": "Saving your note.",
}


def speech_chunks(text: str) -> list[str]:
    """Start with a short phrase; keep subsequent chunks large enough for natural cadence."""
    chunks = []
    remaining = text.strip()
    while remaining:
        limit = 100 if len(chunks) < 2 else 180
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Prefer sentence/clause boundaries, but never wait for a very long sentence.
        boundaries = [m.end() for m in re.finditer(r'[.!?;:,](?:["\u201d])?(?=\s)', remaining[:limit + 1])
                      if m.end() >= 24]
        sentences = [m.end() for m in re.finditer(r'[.!?](?:["\u201d])?(?=\s)', remaining[:limit + 1])
                     if m.end() >= 12]
        if not chunks and sentences:
            cut = sentences[0]
        else:
            cut = boundaries[-1] if boundaries else remaining.rfind(" ", 0, limit + 1)
        if cut <= 0:  # An unbroken URL/name should not be split in the middle.
            cut = remaining.find(" ")
            if cut < 0:
                chunks.append(remaining)
                break
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return chunks


class PromptCache:
    def __init__(self, root: Path):
        self.folder = root / "voice-prompts"

    def path(self, name: str, engine: str, voice: str, speed: float) -> Path:
        # Only entries from PROMPTS can be persisted; never cache conversations here.
        text = PROMPTS[name]
        key = f"v1\0{engine}\0{voice}\0{speed:.2f}\0{text}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.folder / (digest + ".wav")

    @staticmethod
    def ready(path: Path) -> bool:
        try:
            if not 44 < path.stat().st_size <= 512_000:
                return False
            with wave.open(str(path), "rb") as audio:
                return audio.getnframes() > 0 and audio.getframerate() >= 8000
        except (OSError, EOFError, wave.Error):
            return False
