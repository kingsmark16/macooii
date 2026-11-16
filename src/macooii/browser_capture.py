"""User-initiated Facebook captures delivered over Chrome native messaging."""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .config import data_dir

EXTENSION_ID = "echjcjmpfcgiockeaofblhpjncanccfg"
HOST_NAME = "com.macooii.browser"
MAX_MESSAGE = 256_000
MAX_TEXT = 24_000


def validate_capture(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("type") != "facebook_capture":
        raise ValueError("Only a user-requested Facebook capture is supported.")
    url, title, text = (value.get(name) for name in ("url", "title", "text"))
    if not all(isinstance(item, str) for item in (url, title, text)):
        raise ValueError("The page capture is incomplete.")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if len(url) > 2000 or parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443} or not (host == "facebook.com" or host.endswith(".facebook.com")):
        raise ValueError("Read with Macooii currently supports HTTPS Facebook pages only.")
    if not text.strip() or len(text) > MAX_TEXT or len(title) > 300:
        raise ValueError("The page has no readable text or exceeds the capture limit.")
    return {"type": "facebook_capture", "url": urlunsplit(("https", parsed.netloc, parsed.path, "", "")),
            "title": title, "text": text.strip(), "truncated": bool(value.get("truncated")),
            "selection": bool(value.get("selection"))}


def queue_capture(root: Path, value: dict) -> str:
    capture = validate_capture(value)
    inbox = root / "browser-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for old in inbox.glob("*.json"):
        if time.time() - old.stat().st_mtime > 600:
            old.unlink(missing_ok=True)
    if len(list(inbox.glob("*.json"))) >= 5:
        raise ValueError("Review or dismiss pending captures in Macooii first.")
    identity = uuid.uuid4().hex
    temporary = inbox / (identity + ".tmp")
    target = inbox / (identity + ".json")
    temporary.write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
    return identity


def next_capture(root: Path) -> dict | None:
    inbox = root / "browser-inbox"
    for path in sorted(inbox.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            if time.time() - path.stat().st_mtime > 600 or path.stat().st_size > MAX_MESSAGE:
                continue
            return validate_capture(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
        finally:
            path.unlink(missing_ok=True)
    return None


def read_message(stream) -> dict:
    header = stream.read(4)
    if len(header) != 4:
        raise ValueError("Missing native message header")
    size = struct.unpack("=I", header)[0]
    if size > MAX_MESSAGE or size == 0:
        raise ValueError("Invalid native message length")
    chunks, remaining = [], size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError("Incomplete native message")
        chunks.append(chunk)
        remaining -= len(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


def write_message(stream, message: dict):
    body = json.dumps(message).encode("utf-8")
    stream.write(struct.pack("=I", len(body)) + body)
    stream.flush()


def native_main() -> int:
    if f"chrome-extension://{EXTENSION_ID}/" not in sys.argv[1:]:
        return 1
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    try:
        identity = queue_capture(data_dir(), read_message(sys.stdin.buffer))
        answer = {"ok": True, "id": identity, "message": "Sent locally. Open Macooii to review. Nothing was sent to an AI service."}
    except (ValueError, OSError):
        answer = {"ok": False, "message": "Capture could not be received. Check the Facebook tab and pending captures in Macooii."}
    write_message(sys.stdout.buffer, answer)
    return 0


def install_bridge(app_folder: Path):
    import winreg

    source = app_folder / "browser-bridge/MacooiiBrowserHost.exe"
    if not source.is_file():
        raise ValueError("Build or extract the complete Macooii folder before installing the browser bridge.")
    folder = data_dir() / "browser-bridge"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / source.name
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    manifest = folder / "com.macooii.browser.json"
    manifest.write_text(json.dumps({"name": HOST_NAME, "description": "Read a selected Facebook tab with Macooii",
        "path": str(destination.resolve()), "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"]}, indent=2), encoding="utf-8")
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
                                0, winreg.KEY_SET_VALUE | view) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest.resolve()))

