import io
import json
import struct
import time
from types import SimpleNamespace

import pytest

from macooii.browser_capture import MAX_MESSAGE, next_capture, queue_capture, read_message, validate_capture
from macooii.engine import Engine
from macooii.privacy import TaskContext
from macooii.providers import ProviderError, Reply, ToolCall


@pytest.fixture
def capture():
    return {"type": "facebook_capture", "url": "https://www.facebook.com/professional_dashboard?token=private#view",
            "title": "Professional dashboard · QA sample", "text": "Last 28 days\nViews 1200\nFollowers 42"}


@pytest.mark.parametrize("url", ["https://facebook.com.attacker.test/", "http://facebook.com/", "https://example.com/", "https://user:pass@facebook.com/", "https://facebook.com:8080/"])
def test_capture_rejects_other_origins(capture, url):
    with pytest.raises(ValueError):
        validate_capture({**capture, "url": url})


def test_capture_strips_query_and_fragment_and_rejects_oversize(capture):
    result = validate_capture(capture)
    assert result["url"] == "https://www.facebook.com/professional_dashboard"
    with pytest.raises(ValueError):
        validate_capture({**capture, "text": "x" * 24001})


def test_capture_queue_is_consumed_once_and_expires(tmp_path, capture):
    identity = queue_capture(tmp_path, capture)
    assert next_capture(tmp_path)["text"] == capture["text"]
    assert next_capture(tmp_path) is None
    queue_capture(tmp_path, capture)
    import os
    for path in (tmp_path / "browser-inbox").glob("*.json"):
        os.utime(path, (time.time() - 700, time.time() - 700))
    assert next_capture(tmp_path) is None
    assert not (tmp_path / "browser-inbox" / (identity + ".json")).exists()


def test_native_frames_enforce_bounds(capture):
    body = json.dumps(capture).encode()
    assert read_message(io.BytesIO(struct.pack("=I", len(body)) + body)) == capture
    for data in (b"", struct.pack("=I", MAX_MESSAGE + 1), struct.pack("=I", 10) + b"{}"):
        with pytest.raises(ValueError):
            read_message(io.BytesIO(data))


def test_extension_only_has_user_initiated_permissions():
    from pathlib import Path
    manifest = json.loads(Path("browser-extension/manifest.json").read_text())
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "nativeMessaging"}
    assert not manifest.get("host_permissions")
    assert not manifest.get("content_scripts")


def test_capture_review_does_not_call_model_or_persist_raw_text(qapp, store, capture):
    from macooii.bridge import Bridge
    queue_capture(store.root, capture)
    bridge = Bridge(store)
    bridge._poll_capture()
    assert bridge.browserCapture["text"] == capture["text"]
    assert store.messages() == []
    bridge.dismissBrowserCapture()
    assert not bridge.browserCapture
    assert next_capture(store.root) is None
    bridge.shutdown()


def test_private_capture_is_not_sent_when_approval_declined(store, capture, monkeypatch):
    store.set_setting("provider", "codex")
    monkeypatch.setattr("macooii.engine.CodexProvider", lambda **kwargs: SimpleNamespace(
        name="Codex", is_cloud=True, privacy_recipient="OpenAI Codex",
        reply=lambda *args: pytest.fail("Private capture was sent")))
    with pytest.raises(ProviderError, match="capture was not sent"):
        Engine(store, lambda: pytest.fail("No API key needed")).summarize_capture(capture, TaskContext(lambda *args: "decline"), lambda x: None)


def test_capture_can_be_summarized_locally_without_cloud_payload(store, capture, monkeypatch):
    store.set_setting("provider", "codex")
    monkeypatch.setattr("macooii.engine.CodexProvider", lambda **kwargs: SimpleNamespace(
        name="Codex", is_cloud=True, privacy_recipient="OpenAI Codex",
        reply=lambda *args: pytest.fail("Cloud used after local handoff")))
    calls = []
    monkeypatch.setattr("macooii.engine.OllamaProvider", lambda *args: SimpleNamespace(
        name="Local", is_cloud=False, reply=lambda messages, tools, task: calls.append((messages, tools)) or Reply("Views: 1200.")))
    result = Engine(store, lambda: "").summarize_capture(capture, TaskContext(lambda *args: "local"), lambda x: None)
    assert result.provider == "Local" and result.sensitive
    assert calls[0][1] == []
    assert capture["text"] in calls[0][0][0]["content"].replace("\\n", "\n")


def test_summary_cannot_execute_tools_even_if_page_instructs_it(store, capture, monkeypatch):
    store.set_setting("provider", "local")
    monkeypatch.setattr("macooii.engine.OllamaProvider", lambda *args: SimpleNamespace(
        name="Local", is_cloud=False, reply=lambda *args: Reply("", [ToolCall("open_app", {"app": "Chrome"})])))
    with pytest.raises(Exception, match="No action was executed"):
        Engine(store, lambda: "").summarize_capture(capture, TaskContext(lambda *args: "decline"), lambda x: None)

