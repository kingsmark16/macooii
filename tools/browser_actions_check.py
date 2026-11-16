"""Explicit live YouTube workflow check. Opens an owned window and plays audio, then closes it."""
import json
import tempfile
from pathlib import Path

from macooii.browser_actions import ActionBrowser
from macooii.privacy import TaskContext

with tempfile.TemporaryDirectory(prefix="macooii-media-check-") as folder:
    browser = ActionBrowser(Path(folder))
    try:
        task = TaskContext(lambda *args: "decline")
        print(json.dumps(browser.call("play", {"query": "relaxing music"}, task)), flush=True)
        print(json.dumps(browser.call("control", {"action": "pause"}, task)), flush=True)
        print(json.dumps(browser.call("control", {"action": "resume"}, task)), flush=True)
        print(json.dumps(browser.call("control", {"action": "stop"}, task)), flush=True)
    finally:
        browser.close()
