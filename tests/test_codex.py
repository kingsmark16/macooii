import io
import json
import queue
import time
from types import SimpleNamespace

import pytest

import macooii.codex_provider as module
import macooii.engine as engine_module
from macooii.codex_provider import CodexProvider, CodexRPC, server_names
from macooii.engine import Engine
from macooii.privacy import Cancelled, TaskContext
from macooii.providers import ProviderError, Reply, ToolCall


class RPC:
    instances = []
    answer = {"text": "Hello", "tool": "", "arguments_json": "{}"}

    def __init__(self, task, cwd):
        self.requests = []
        self.closed = False
        self.events = iter([
            {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": json.dumps(self.answer)}}},
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}])
        self.instances.append(self)

    def initialize(self):
        return {"connected": True, "plan": "plus"}

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "config/read":
            return {"layers": [{"config": {"mcp_servers": {"private_connector": {"enabled": True}}}}]}
        return {"thread": {"id": "thread-1"}}

    def receive(self, deadline):
        return next(self.events)

    def close(self):
        self.closed = True


def test_codex_is_ephemeral_tool_free_and_preserves_approved_messages(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", RPC)
    monkeypatch.setattr(module, "inherited_server_names", lambda: {"other_connector"})
    response = CodexProvider().reply([{"role": "user", "content": "hello"}], [], task)
    rpc = RPC.instances[-1]
    start = dict(rpc.requests)["thread/start"]
    assert start["ephemeral"] and start["environments"] == []
    assert start["sandbox"] == "read-only"
    assert all(not v["enabled"] for v in start["config"]["mcp_servers"].values())
    assert set(start["config"]["mcp_servers"]) == {"private_connector", "other_connector"}
    assert response.text == "Hello" and rpc.closed


def test_codex_decisions_return_to_macooii_instead_of_executing(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", RPC)
    monkeypatch.setattr(RPC, "answer", {"text": "", "tool": "create_note", "arguments_json": '{"title":"A","body":"B"}'})
    response = CodexProvider().reply([], [{"name": "create_note"}], task)
    assert response.calls[0].name == "create_note"
    assert response.calls[0].arguments == {"title": "A", "body": "B"}


def test_invalid_codex_tool_is_rejected(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", RPC)
    monkeypatch.setattr(RPC, "answer", {"text": "", "tool": "run_shell", "arguments_json": "{}"})
    with pytest.raises(ProviderError, match="invalid Macooii decision"):
        CodexProvider().reply([], [], task)


def test_api_key_login_is_not_accepted():
    rpc = object.__new__(CodexRPC)
    rpc.request = lambda method, params: {"account": {"type": "apiKey"}}
    rpc.send = lambda message: None
    with pytest.raises(ProviderError, match="ChatGPT login"):
        rpc.initialize()


def test_nested_mcp_layers_and_profiles_are_disabled():
    assert server_names({"profiles": {"x": {"mcp_servers": {"one": {}}}},
                         "layers": [{"config": {"mcp_servers": {"two": {}}}}]}) == {"one", "two"}


def test_codex_uses_its_own_recipient_for_private_context(store, monkeypatch):
    note_id = store.save_note("Private", "SECRET")
    store.set_setting("provider", "codex")
    inputs = []
    answers = iter([Reply(calls=[ToolCall("read_note", {"note_id": note_id})]), Reply("Declined")])

    def reply(messages, tools, task):
        inputs.append(json.dumps(messages))
        return next(answers)

    monkeypatch.setattr(engine_module, "CodexProvider", lambda **kwargs: SimpleNamespace(
        name="Codex", privacy_recipient="OpenAI Codex", is_cloud=True, reply=reply))
    prompts = []
    outcome = Engine(store, lambda: "").run("Read my note", TaskContext(lambda label, text: prompts.append(label) or "decline"), lambda x: None)
    assert prompts[0].startswith("OpenAI Codex\n")
    assert "SECRET" not in inputs[-1]
    assert outcome.sensitive


def test_rpc_cancellation_is_checked_without_waiting(task):
    rpc = object.__new__(CodexRPC)
    rpc.task = task
    task.cancelled.set()
    with pytest.raises(Cancelled):
        rpc.send({"method": "ignored"})


def test_cli_is_subscription_only_and_mcp_keys_are_not_misquoted(monkeypatch, task, tmp_path):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setattr(module, "codex_command", lambda: ["codex.exe"])
    monkeypatch.setattr(module, "inherited_server_names", lambda: {"blender", "a.dotted.name"})

    def spawn(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), poll=lambda: 0)

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    rpc = CodexRPC(task, str(tmp_path))
    rpc.close()
    assert "OPENAI_API_KEY" not in captured["env"]
    assert 'forced_login_method="chatgpt"' in captured["command"]
    assert "mcp_servers.blender.enabled=false" in captured["command"]
    assert not any('mcp_servers."' in value for value in captured["command"])
    assert "features.shell_tool=false" in captured["command"]


def test_codex_speech_does_not_use_gemini(qapp, store, monkeypatch):
    from macooii.bridge import Bridge
    from macooii.engine import Outcome

    store.set_setting("provider", "codex")
    store.set_setting("cloud_enabled", True)
    bridge = Bridge(store)
    monkeypatch.setattr("macooii.bridge.credentials.get_api_key", lambda: pytest.fail("Codex speech read Gemini credentials"))
    spoken = []
    bridge.blockSignals(True)
    monkeypatch.setattr("macooii.bridge.windows_speech", lambda text, task, output: spoken.append(text))
    bridge._speak(Outcome("Hello", "Codex"), TaskContext(lambda *a: "decline"),
                  SimpleNamespace(progress=SimpleNamespace(emit=lambda text: None)))
    assert spoken == ["Hello"]
    bridge.shutdown()


def test_server_initiated_native_tool_is_denied(task):
    rpc = object.__new__(CodexRPC)
    rpc.task = task
    rpc.events = queue.Queue()
    rpc.events.put({"id": 99, "method": "item/tool/call", "params": {"tool": "shell"}})
    rpc.process = SimpleNamespace(stdin=io.BytesIO())
    with pytest.raises(ProviderError, match="native tool"):
        rpc.receive(time.monotonic() + 2)
    assert json.loads(rpc.process.stdin.getvalue())["error"]["code"] == -32601


def test_codex_failure_falls_back_without_reading_api_credentials(store, monkeypatch):
    store.set_setting("provider", "codex")

    def unavailable(*args):
        raise ProviderError("Allowance temporarily unavailable")

    monkeypatch.setattr(engine_module, "CodexProvider", lambda **kwargs: SimpleNamespace(
        name="Codex", is_cloud=True, reply=unavailable))
    monkeypatch.setattr(engine_module, "OllamaProvider", lambda *args: SimpleNamespace(
        name="Local", is_cloud=False, reply=lambda *args: Reply("Local answer")))
    result = Engine(store, lambda: pytest.fail("Codex requested API credentials")).run(
        "Hello", TaskContext(lambda *args: "decline"), lambda status: None)
    assert result.provider == "Local" and result.text == "Local answer"


class PersistentRPC(RPC):
    def __init__(self, task, cwd):
        super().__init__(task, cwd)
        self.process = SimpleNamespace(poll=lambda: None)
        self.thread_count = 0

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "account/read":
            return {"account": {"type": "chatgpt"}}
        if method == "thread/start":
            self.thread_count += 1
            return {"thread": {"id": f"thread-{self.thread_count}"}}
        if method == "turn/start":
            self.events = iter([
                {"method": "item/completed", "params": {"threadId": params["threadId"], "item": {
                    "type": "agentMessage", "text": json.dumps(self.answer)}}},
                {"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"status": "completed"}}}])
        return {}


def test_ready_connection_reused_but_ephemeral_context_is_unloaded_each_time(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", PersistentRPC)
    provider = CodexProvider(persistent=True)
    provider.warm(task)
    rpc = provider.rpc
    assert not any(method == "turn/start" for method, _ in rpc.requests)
    provider.reply([{"role": "user", "content": "Private first task"}], [], task)
    provider.reply([{"role": "user", "content": "Unrelated second task"}], [], TaskContext(lambda *a: "decline"))
    assert provider.rpc is rpc and not rpc.closed
    starts = [p for m, p in rpc.requests if m == "thread/start"]
    assert len(starts) == 2 and all(p["ephemeral"] for p in starts)
    unloads = [p["threadId"] for m, p in rpc.requests if m == "thread/unsubscribe"]
    assert unloads == ["thread-1", "thread-2"]
    turns = [p for m, p in rpc.requests if m == "turn/start"]
    assert "Private first task" not in json.dumps(turns[1])
    assert rpc.task is not task
    provider.close()
    assert rpc.closed and provider.directory is None


def test_cancelled_persistent_request_closes_connection_instead_of_reusing_it(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", PersistentRPC)
    provider = CodexProvider(persistent=True)
    provider.warm(task)
    rpc = provider.rpc

    def receive(deadline):
        task.cancelled.set()
        task.check()

    rpc.receive = receive
    with pytest.raises(Cancelled):
        provider.reply([], [], task)
    assert rpc.closed and provider.rpc is None


def test_changed_codex_config_restarts_the_isolated_connection(monkeypatch, task):
    monkeypatch.setattr(module, "CodexRPC", PersistentRPC)
    provider = CodexProvider(persistent=True)
    provider.warm(task)
    old = provider.rpc
    monkeypatch.setattr(provider, "_config_stamp", lambda: ("changed", 2, 3))
    provider.reply([], [], task)
    assert old.closed and provider.rpc is not old
    provider.close()
