"""Play an explicit public speech check; never records a microphone."""
from pathlib import Path

from macooii.diagnostics import verify_voice

if __name__ == "__main__":
    raise SystemExit(verify_voice(Path("output/voice-playback.json")))
