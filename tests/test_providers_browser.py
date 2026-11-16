import json
import socket

import httpx
import pytest

from macooii.browser import public_url
from macooii.config import GEMINI_MODELS
from macooii.providers import GeminiProvider, OllamaProvider, ProviderError


def intercept(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: original(
        *args, **kwargs, transport=httpx.MockTransport(handler)))


def test_gemini_payload_preserves_function_signatures(monkeypatch, task):
    received = []

    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "list_apps", "args": {}}, "thoughtSignature": "preserve-me"}]}}]})

    intercept(monkeypatch, handler)
    provider = GeminiProvider("secret-key", GEMINI_MODELS[0])
    first = provider.reply([{"role": "user", "content": "List apps"}], [], task)
    provider.reply([{"role": "user", "content": "List apps"},
                    {"role": "assistant", "raw": first.raw},
                    {"role": "tool", "name": "list_apps", "result": {"apps": []}}], [], task)
    assert first.calls[0].name == "list_apps"
    assert received[1]["contents"][1]["parts"][0]["thoughtSignature"] == "preserve-me"
    assert received[1]["contents"][2]["parts"][0]["functionResponse"]["name"] == "list_apps"


def test_quota_error_never_echoes_remote_secret(monkeypatch, task):
    intercept(monkeypatch, lambda request: httpx.Response(429, json={"error": {"message": "PRIVATE SECRET"}}))
    with pytest.raises(ProviderError, match="quota") as caught:
        GeminiProvider("key", GEMINI_MODELS[0]).reply([{"role": "user", "content": "hello"}], [], task)
    assert "PRIVATE SECRET" not in str(caught.value)


def test_no_arbitrary_cloud_model(task):
    with pytest.raises(ProviderError, match="reviewed"):
        GeminiProvider("key", "paid-or-unreviewed")


def test_ollama_can_continue_cloud_tool_history(monkeypatch, task):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Done"}})

    intercept(monkeypatch, handler)
    OllamaProvider().reply([{"role": "user", "content": "Read it"},
                            {"role": "assistant", "content": "", "calls": [{"name": "read_note", "arguments": {"note_id": "123"}}]},
                            {"role": "tool", "name": "read_note", "result": {"text": "approved locally"}}], [], task)
    assert seen[0]["messages"][2]["tool_calls"][0]["function"]["name"] == "read_note"
    assert seen[0]["stream"] is False


def test_local_context_overflow_is_visible_before_network(monkeypatch, task):
    intercept(monkeypatch, lambda request: pytest.fail("An oversized local context reached the runtime"))
    with pytest.raises(ProviderError, match="Local context is full"):
        OllamaProvider().reply([{"role": "user", "content": "document " * 4000}], [], task)


@pytest.mark.parametrize("url", ["file:///C:/secret", "http://127.0.0.1", "http://192.168.1.1", "http://[::1]", "http://user:pass@example.com", "https://example.com:8080"])
def test_browser_rejects_local_urls(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_browser_rejects_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(ValueError, match="private"):
        public_url("https://example.org")
