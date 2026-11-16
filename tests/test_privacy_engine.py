import json
import threading

import pytest

import macooii.engine as engine_module
from macooii.engine import Engine
from macooii.privacy import Cancelled, LocalRequested, TaskContext
from macooii.providers import ProviderError, Reply, ToolCall
from macooii.tools import ToolRegistry


class FakeProvider:
    name = "Fake cloud"
    is_cloud = True

    def __init__(self, replies):
        self.replies = iter(replies)
        self.inputs = []

    def reply(self, messages, tools, task):
        self.inputs.append(json.loads(json.dumps(messages)))
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


def cloud_engine(store, monkeypatch, replies):
    store.set_setting("cloud_enabled", True)
    fake = FakeProvider(replies)
    monkeypatch.setattr(engine_module, "GeminiProvider", lambda *args: fake)
    return Engine(store, lambda: "fake-key"), fake


def test_context_approval_is_exact_and_expires_per_task():
    seen = []
    ctx = TaskContext(lambda label, text: seen.append(text) or "approve")
    ctx.cloud_context("file", "first excerpt")
    ctx.cloud_context("file", "first excerpt")
    ctx.cloud_context("file", "changed excerpt")
    assert seen == ["first excerpt", "changed excerpt"]
    fresh = TaskContext(lambda *args: "decline")
    with pytest.raises(PermissionError):
        fresh.cloud_context("file", "first excerpt")
    with pytest.raises(LocalRequested):
        TaskContext(lambda *args: "local").cloud_context("file", "text")


def test_declined_private_tool_result_never_reaches_cloud(store, monkeypatch):
    note_id = store.save_note("SECRET TITLE", "SECRET BODY")
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[ToolCall("read_note", {"note_id": note_id})]), Reply("Declined")])
    outcome = engine.run("Summarize my note", TaskContext(lambda *args: "decline"), lambda x: None)
    outbound = json.dumps(fake.inputs)
    assert "SECRET BODY" not in outbound and "SECRET TITLE" not in outbound
    assert outcome.sensitive


def test_approved_excerpt_reaches_cloud_after_display(store, monkeypatch):
    note_id = store.save_note("Private", "EXACT EXCERPT")
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[ToolCall("read_note", {"note_id": note_id})]), Reply("Summary")])
    displayed = []
    outcome = engine.run("Summarize my note", TaskContext(lambda label, text: displayed.append(text) or "approve"), lambda x: None)
    assert "EXACT EXCERPT" in displayed[0]
    assert "EXACT EXCERPT" in json.dumps(fake.inputs[1])
    assert outcome.sensitive


def test_private_history_excluded_from_new_cloud_request(store, monkeypatch):
    store.add_message("user", "PRIVATE OLD QUESTION", True)
    store.add_message("assistant", "PRIVATE OLD ANSWER", True)
    store.add_message("user", "Public question", False)
    engine, fake = cloud_engine(store, monkeypatch, [Reply("Hello")])
    engine.run("Hello", TaskContext(lambda *a: "decline"), lambda x: None)
    assert "PRIVATE" not in json.dumps(fake.inputs)
    assert "Public question" in json.dumps(fake.inputs)


def test_local_conversation_keeps_private_history(store, monkeypatch):
    store.add_message("user", "My code word is papaya", True)
    store.add_message("assistant", "Understood", True)
    local = FakeProvider([Reply("papaya")])
    local.is_cloud = False
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: local)
    Engine(store, lambda: "").run("What was my code word?", TaskContext(lambda *a: "decline"), lambda x: None)
    assert "papaya" in json.dumps(local.inputs)


def test_current_user_turn_is_not_duplicated_in_local_history(store, monkeypatch):
    identity = store.add_message("user", "Hello", True)
    local = FakeProvider([Reply("Hi")])
    local.is_cloud = False
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: local)
    task = TaskContext(lambda *a: "decline", current_message_id=identity)
    Engine(store, lambda: "").run("Hello", task, lambda x: None)
    assert sum(message.get("content") == "Hello" for message in local.inputs[0]) == 1


def test_private_local_history_still_gates_outbound_web_queries(store, monkeypatch):
    class NoBrowser:
        def search(self, *args):
            pytest.fail("Private conversation context escaped through web search")

    store.add_message("user", "My private code word is papaya", True)
    local = FakeProvider([Reply(calls=[ToolCall("search_web", {"query": "papaya"})]), Reply("Not shared")])
    local.is_cloud = False
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: local)
    registry = ToolRegistry(store, NoBrowser())
    Engine(store, lambda: "", registry).run("Research this", TaskContext(lambda *a: "decline"), lambda x: None)
    assert "Sharing declined" in json.dumps(local.inputs[-1])


def test_local_switch_reuses_result_and_does_not_resend_cloud(store, monkeypatch):
    note_id = store.save_note("Private", "LOCAL ONLY")
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[ToolCall("read_note", {"note_id": note_id})])])
    local = FakeProvider([Reply("Local summary")])
    local.is_cloud = False
    local.name = "Local"
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: local)
    result = engine.run("Summarize my note", TaskContext(lambda *args: "local"), lambda x: None)
    assert len(fake.inputs) == 1
    assert "LOCAL ONLY" in json.dumps(local.inputs)
    assert result.provider == "Local"


def test_quota_fallback_does_not_replay_completed_write(store, monkeypatch):
    call = ToolCall("create_note", {"title": "Useful", "body": "saved once"})
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[call]), ProviderError("quota")])
    local = FakeProvider([Reply(calls=[call]), Reply("Done")])
    local.is_cloud = False
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: local)
    engine.run("Save this as a note", TaskContext(lambda *args: "decline"), lambda x: None)
    assert len(store.notes()) == 1


def test_page_instructions_cannot_authorize_writes(store, monkeypatch):
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[ToolCall("create_note", {"title": "Injected", "body": "bad"})]), Reply("Read only")])
    engine.run("Research a topic", TaskContext(lambda *args: "approve"), lambda x: None)
    assert store.notes() == []
    assert "explicit request" in json.dumps(fake.inputs[-1])


def test_cancelled_task_never_executes_next_tool(store, monkeypatch):
    event = threading.Event()
    task = TaskContext(lambda *args: "approve", cancelled=event)
    task.cancelled.set()
    with pytest.raises(Cancelled):
        Engine(store, lambda: "").run("/note title | body", task, lambda x: None)
    assert store.notes() == []


@pytest.mark.parametrize("input_text,expected", [
    ("Remember that I prefer Taglish", "I prefer Taglish"),
    ("Tandaan mo na blue ang favorite ko", "blue ang favorite ko"),
    ("/remember Explain every detail", "Explain every detail"),
    ("Macooii, remember that I prefer English", "I prefer English"),
    ("Paki tandaan mo na blue ang favorite ko", "blue ang favorite ko"),
])
def test_explicit_memory_is_local_without_model(store, input_text, expected):
    result = Engine(store, lambda: "").run(input_text, TaskContext(lambda *args: pytest.fail("No cloud consent needed")), lambda x: None)
    assert store.memories()[0]["body"] == expected
    assert result.sensitive


def test_search_cards_stay_local_on_decline(store, monkeypatch, tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "PRIVATE-proposal.txt").write_text("private")
    store.set_setting("folders", [str(root)])
    engine, fake = cloud_engine(store, monkeypatch, [Reply(calls=[ToolCall("search_files", {"query": "proposal"})]), Reply("Choose locally")])
    result = engine.run("Find proposal", TaskContext(lambda *a: "decline"), lambda x: None)
    assert "PRIVATE-proposal" not in json.dumps(fake.inputs)
    assert result.cards[0]["name"] == "PRIVATE-proposal.txt"


def test_source_ids_are_verified_against_retrieved_records(store, monkeypatch):
    engine, fake = cloud_engine(store, monkeypatch, [Reply("Claim [S99]")])
    result = engine.run("Question", TaskContext(lambda *a: "decline"), lambda x: None)
    assert "[unverified source]" in result.text


def test_tool_validation_denies_made_up_app_authorization(store):
    engine = Engine(store, lambda: "", ToolRegistry(store))
    with pytest.raises(ValueError):
        engine.authorize_write("open_app", {"app": "Chrome"}, "Research browser comparisons")


def test_repeated_declined_payload_does_not_prompt_again():
    prompts = []
    task = TaskContext(lambda *args: prompts.append(args) or "decline")
    for _ in range(2):
        with pytest.raises(PermissionError):
            task.cloud_context("file", "private")
    assert len(prompts) == 1
