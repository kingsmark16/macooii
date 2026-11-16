import pytest

from macooii.engine import Engine
from macooii.privacy import TaskContext
from macooii.tools import ToolRegistry, ToolResult


class Actions:
    def __init__(self):
        self.calls = []

    def call(self, action, args, task):
        self.calls.append((action, args))
        if action == "play":
            return {"playing": True, "title": "Test music", "url": "https://www.youtube.com/watch?v=test", "ad_playing": False}
        if action == "control":
            return {"success": True, "action": args["action"]}
        return {"opened": True, **args}


@pytest.mark.parametrize("input_text,action", [("open youtube and play music", "play"),
    ("play relaxing music on youtube", "play"), ("open youtube", "open"),
    ("Open https://example.com", "open"), ("pause music", "control"), ("resume music", "control")])
def test_clear_browser_commands_execute_without_model(store, input_text, action, monkeypatch):
    registry = ToolRegistry(store)
    registry.actions = Actions()
    launches = []
    monkeypatch.setattr("macooii.tools.launch_regular_browser", lambda apps, url: launches.append(url))
    monkeypatch.setattr("macooii.tools.youtube_target", lambda query, task: {
        "title": query, "url": "https://www.youtube.com/watch?v=abcdefghijk&autoplay=1", "search_only": False})
    outcome = Engine(store, lambda: pytest.fail("No API needed"), registry).run(input_text, TaskContext(lambda *a: "decline"), lambda x: None)
    if action in {"open", "play"}:
        assert launches
        assert not registry.actions.calls
        if action == "play":
            assert "Requested playback" in outcome.text
            assert "Started YouTube" not in outcome.text
    else:
        assert registry.actions.calls[0][0] == action
    assert outcome.provider == "Local command"


def test_simple_confirmation_opens_named_registered_app(store, monkeypatch):
    store.set_setting("apps", {"Chrome": "fake.exe"})
    store.add_message("assistant", "Should I open Chrome?")
    registry = ToolRegistry(store)
    monkeypatch.setattr(registry, "open_app", lambda args, task: ToolResult(
        {"success": True, "app": args.app, "action": "focused"}))
    result = Engine(store, lambda: "", registry).run("Yes!", TaskContext(lambda *a: "decline"), lambda x: None)
    assert result.text == "Focused Chrome."


def test_webpage_cannot_authorize_playback(store):
    with pytest.raises(ValueError, match="explicit request"):
        Engine(store, lambda: "").authorize_write("play_youtube", {"query": "anything"}, "Summarize this article")


def test_personal_context_must_not_escape_via_media_search(store):
    registry = ToolRegistry(store)
    registry.actions = Actions()
    with pytest.raises(PermissionError):
        registry.execute("play_youtube", {"query": "private title"}, TaskContext(lambda *a: "decline", private_sources_used=True))
    assert not registry.actions.calls


def test_windows_voice_reads_actual_taglish_reply(qapp, store, monkeypatch):
    from types import SimpleNamespace

    from macooii.bridge import Bridge
    from macooii.engine import Outcome

    store.set_setting("provider", "codex")
    bridge = Bridge(store)
    bridge.blockSignals(True)
    spoken = []
    monkeypatch.setattr("macooii.bridge.windows_speech", lambda text, task, path: spoken.append(text))
    bridge._speak(Outcome("Sige, binuksan ko ang YouTube.", "Codex"), TaskContext(lambda *args: "decline"),
                  SimpleNamespace(progress=SimpleNamespace(emit=lambda text: None)))
    assert spoken == ["Sige, binuksan ko ang YouTube."]
    bridge.shutdown()


def test_missing_speaker_reports_error_without_switching_output(qapp, store, tmp_path):
    from macooii.bridge import Bridge

    store.set_setting("speaker", "removed-device")
    bridge = Bridge(store)
    messages = []
    bridge.toast.connect(messages.append)
    path = tmp_path / "unused.wav"
    path.write_bytes(b"unused")
    bridge._play_audio(str(path))
    assert "Voice output unavailable" in messages[-1]
    assert not path.exists()
    assert bridge.speakerChoices[-1]["id"] == "removed-device"
    bridge.shutdown()


def test_acknowledgment_finishes_before_action(store, monkeypatch):
    registry = ToolRegistry(store)
    events = []
    task = TaskContext(lambda *args: "decline", before_action=lambda name: events.append("spoken " + name))
    monkeypatch.setattr(registry, "create_note", lambda args, task: events.append("saved") or ToolResult({}))
    registry.execute("create_note", {"title": "Test", "body": "Public text"}, task)
    assert events == ["spoken create_note", "saved"]


def test_cancelling_acknowledgment_prevents_action(store, monkeypatch):
    from macooii.privacy import Cancelled

    registry = ToolRegistry(store)
    task = TaskContext(lambda *args: "decline")
    task.before_action = lambda name: task.cancelled.set()
    monkeypatch.setattr(registry, "create_note", lambda *args: pytest.fail("Action ran after cancellation"))
    with pytest.raises(Cancelled):
        registry.execute("create_note", {"title": "Test", "body": "Public text"}, task)


def test_audio_completion_processes_ui_event_before_releasing_action(qapp, store):
    import threading

    from PySide6.QtMultimedia import QMediaPlayer

    from macooii.bridge import Bridge

    bridge = Bridge(store)
    completed = threading.Event()
    bridge._audio_done = completed
    bridge._media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert completed.played
    assert not completed.is_set()
    qapp.processEvents()
    assert completed.is_set()
    bridge.shutdown()


def test_regular_browser_launch_does_not_use_automation_profile(tmp_path, monkeypatch):
    from macooii.browser_launcher import launch_regular_browser

    executable = tmp_path / "chrome.exe"
    executable.touch()
    calls = []
    monkeypatch.setattr("macooii.browser_launcher.subprocess.Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr("macooii.browser_launcher.public_url", lambda url: url)
    launch_regular_browser({"Chrome": str(executable)}, "https://example.com")
    assert calls[0][0] == [str(executable.resolve()), "https://example.com"]
    assert calls[0][1]["shell"] is False
    launch_regular_browser({}, executable=executable)
    assert calls[1][0] == [str(executable), "--new-window"]


def test_private_website_navigation_needs_approval_before_browser_launch(store, monkeypatch):
    registry = ToolRegistry(store)
    monkeypatch.setattr("macooii.tools.launch_regular_browser", lambda *args: pytest.fail("Launched before approval"))
    task = TaskContext(lambda *args: "decline", private_sources_used=True)
    with pytest.raises(PermissionError):
        registry.execute("open_website", {"url": "https://example.com"}, task)


def test_youtube_link_comes_from_organic_search_result():
    import json

    from macooii.browser_launcher import youtube_result

    organic = {"videoRenderer": {"videoId": "abcdefghijk", "title": {"runs": [{"text": "Example Track"}]}}}
    ad = {"adSlotRenderer": {"videoRenderer": {"videoId": "aaaaaaaaaaa"}}}
    data = {"contents": {"twoColumnSearchResultsRenderer": {"primaryContents": {"items": [ad, organic]}}}}
    result = youtube_result("var ytInitialData = " + json.dumps(data), "https://www.youtube.com/results", "query")
    assert result["url"] == "https://www.youtube.com/watch?v=abcdefghijk&autoplay=1"
    assert result["title"] == "Example Track"
    assert not result["search_only"]


def test_unavailable_youtube_result_reports_search_fallback(store, monkeypatch):
    from macooii.browser_launcher import youtube_result

    fallback = youtube_result("Human check", "https://www.youtube.com/results?search_query=music", "music")
    assert fallback["search_only"]
    registry = ToolRegistry(store)
    monkeypatch.setattr("macooii.tools.youtube_target", lambda *args: fallback)
    monkeypatch.setattr("macooii.tools.launch_regular_browser", lambda *args: None)
    result = Engine(store, lambda: pytest.fail("No model needed"), registry).run(
        "open youtube and play music", TaskContext(lambda *args: "decline"), lambda *args: None)
    assert "Select a result to play" in result.text
    assert "Started" not in result.text


def test_regular_youtube_playback_does_not_claim_control_success(store):
    registry = ToolRegistry(store)
    registry.regular_media = True
    with pytest.raises(ValueError, match="cannot verify playback controls"):
        registry.execute("control_media", {"action": "pause"}, TaskContext(lambda *args: "decline"))

