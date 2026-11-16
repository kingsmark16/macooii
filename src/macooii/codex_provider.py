"""Subscription-backed Codex inference over the official local app-server protocol."""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
from pathlib import Path

from .privacy import TaskContext
from .providers import SYSTEM_PROMPT, ProviderError, Reply, ToolCall

DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "code_mode", "apps", "plugins", "connectors", "multi_agent",
    "js_repl", "computer_use", "browser_use", "view_image", "image_generation", "memory_tool",
    "memories", "hooks", "codex_hooks", "plugin_hooks", "apply_patch_freeform", "daemon_auto_start",
)


def server_names(config):
    names = set()
    if isinstance(config, dict):
        for key, value in config.items():
            if key in {"mcp_servers", "mcpServers"} and isinstance(value, dict):
                names.update(value)
            names.update(server_names(value))
    elif isinstance(config, list):
        for value in config:
            names.update(server_names(value))
    return names


def inherited_server_names():
    path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    if not path.exists():
        return set()
    try:
        return server_names(tomllib.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as exc:
        raise ProviderError("Codex configuration could not be isolated. Check your CLI configuration.", False) from exc


def codex_command() -> list[str]:
    executable = shutil.which("codex.exe")
    if executable:
        return [executable]
    npm = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai/codex"
    candidates = list(npm.glob("node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"))
    if candidates:
        return [str(candidates[0])]
    node = shutil.which("node.exe") or shutil.which("node")
    if node and (npm / "bin/codex.js").is_file():
        return [node, str(npm / "bin/codex.js")]
    native = shutil.which("codex")
    if native and Path(native).suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return [native]
    raise ProviderError("Codex CLI is not installed. Install it and sign in with ChatGPT, then retry.")


class CodexRPC:
    def __init__(self, task: TaskContext, cwd: str):
        self.task = task
        env = os.environ.copy()
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
            env.pop(name, None)
        command = codex_command() + ["app-server", "--listen", "stdio://", "-c", 'model_provider="openai"',
                                     "-c", 'forced_login_method="chatgpt"', "-c", 'web_search="disabled"',
                                     "-c", 'history.persistence="none"', "-c", "project_doc_max_bytes=0",
                                     "-c", "features.skip_host_skill_discovery=true"]
        for feature in DISABLED_FEATURES:
            command += ["-c", f"features.{feature}=false"]
        for name in inherited_server_names():
            # The CLI dotted-key parser treats quote characters literally. Non-bare names
            # are disabled through thread/start's JSON config below instead.
            if re.fullmatch(r"[A-Za-z0-9_-]+", name):
                command += ["-c", f"mcp_servers.{name}.enabled=false"]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, cwd=cwd, env=env, shell=False,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.events = queue.Queue()
        self.counter = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except (ValueError, UnicodeError):
                    continue
        except (OSError, ValueError):
            pass
        finally:
            self.events.put(None)

    def send(self, message):
        self.task.check()
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def receive(self, deadline):
        while time.monotonic() < deadline:
            self.task.check()
            try:
                event = self.events.get(timeout=0.1)
            except queue.Empty:
                continue
            if event is None:
                raise ProviderError("Codex stopped unexpectedly. Check your Codex installation and ChatGPT login.")
            if "method" in event and "id" in event:
                # No server-initiated tool, approval, or connector request may bypass Macooii.
                self.send({"id": event["id"], "error": {"code": -32601, "message": "Macooii does not allow native Codex tools"}})
                raise ProviderError("Codex requested a native tool. The request was blocked; use Macooii tools.", False)
            return event
        raise ProviderError("Codex timed out. Try again or use Local mode.")

    def request(self, method, params, timeout=25):
        self.counter += 1
        identity = self.counter
        self.send({"id": identity, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            event = self.receive(deadline)
            if event.get("id") == identity:
                if "error" in event:
                    raise ProviderError(f"Codex rejected {method}. Check CLI compatibility and ChatGPT access.")
                return event.get("result", {})

    def initialize(self):
        self.request("initialize", {"clientInfo": {"name": "macooii_desktop", "title": "Macooii", "version": "0.8.0"},
                                    "capabilities": {"experimentalApi": True}})
        self.send({"method": "initialized"})
        account = self.request("account/read", {"refreshToken": False}).get("account")
        if not account or account.get("type") != "chatgpt":
            raise ProviderError("Codex needs a ChatGPT login. Run codex login and choose your subscription account.", False)
        return {"connected": True, "plan": account.get("planType", "ChatGPT")}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()


class CodexProvider:
    name = "Codex · ChatGPT plan"
    privacy_recipient = "OpenAI Codex"
    is_cloud = True

    def __init__(self, persistent=False):
        self.persistent = persistent
        self.lock = threading.Lock()
        self.rpc = None
        self.directory = None
        self.settings = None
        self.config_stamp = None

    @staticmethod
    def _config_stamp():
        path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
        try:
            stat = path.stat()
            return str(path), stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return str(path), None, None

    def _close(self):
        rpc, self.rpc = self.rpc, None
        directory, self.directory = self.directory, None
        try:
            if rpc:
                rpc.close()
        finally:
            if directory:
                directory.cleanup()

    def close(self):
        with self.lock:
            self._close()

    def _ready(self, task):
        stamp = self._config_stamp()
        if self.rpc and (self.config_stamp != stamp or self.rpc.process.poll() is not None):
            self._close()
        if self.rpc:
            self.rpc.task = task
            account = self.rpc.request("account/read", {"refreshToken": False}).get("account")
            if not account or account.get("type") != "chatgpt":
                raise ProviderError("Codex needs a ChatGPT login. Run codex login and choose your subscription account.", False)
        else:
            self.directory = tempfile.TemporaryDirectory(prefix="macooii-codex-")
            self.rpc = CodexRPC(task, self.directory.name)
            self.rpc.initialize()
            # Clear inherited MCP enablement explicitly; empty tables merge with user config.
            config = self.rpc.request("config/read", {"includeLayers": True})
            servers = server_names(config) | inherited_server_names()
            self.settings = {"web_search": "disabled", "model_reasoning_effort": "low",
                             "mcp_servers": {name: {"enabled": False} for name in servers}}
            self.config_stamp = stamp
        return self.rpc, self.directory.name

    def warm(self, task):
        """Prepare the protocol connection without an AI turn or user content."""
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            self._ready(task)
            task.check()
        except BaseException:
            self._close()
            raise
        finally:
            if self.rpc:
                self.rpc.task = TaskContext(lambda *args: "decline")
            self.lock.release()

    def reply(self, messages, tools, task):
        while not self.lock.acquire(timeout=0.1):
            task.check()
        try:
            task.check()
            rpc, cwd = self._ready(task)
            schema = {"type": "object", "properties": {"text": {"type": "string"},
                      "tool": {"type": "string", "enum": ["", *[t["name"] for t in tools]]},
                      "arguments_json": {"type": "string"}},
                      "required": ["text", "tool", "arguments_json"], "additionalProperties": False}
            instructions = SYSTEM_PROMPT + "\nYou are a decision-only component. Do not invoke any native Codex tools. " \
                "Return the required JSON: set tool to a Macooii tool name and arguments_json to its JSON object, " \
                "or set tool to an empty string and text to the final answer. Never execute an action yourself."
            thread = rpc.request("thread/start", {"cwd": cwd, "modelProvider": "openai", "ephemeral": True,
                                 "environments": [], "sandbox": "read-only", "approvalPolicy": "untrusted",
                                 "baseInstructions": instructions, "developerInstructions": "Use only the supplied Macooii tool catalog.",
                                 "config": self.settings}).get("thread", {})
            if not thread.get("id"):
                raise ProviderError("Codex could not start an isolated Macooii conversation.")
            clean = [{key: value for key, value in m.items() if key in {"role", "content", "name", "result", "calls"}}
                     for m in messages]
            payload = json.dumps({"conversation": clean, "macooii_tools": tools}, ensure_ascii=False)
            rpc.request("turn/start", {"threadId": thread["id"], "input": [{"type": "text", "text": payload}],
                                      "effort": "low", "outputSchema": schema})
            deadline = time.monotonic() + 120
            answer = ""
            while True:
                event = rpc.receive(deadline)
                method, params = event.get("method"), event.get("params", {})
                if params.get("threadId", thread["id"]) != thread["id"]:
                    continue
                if method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
                    answer = params["item"].get("text", "")
                if method == "turn/completed":
                    turn = params.get("turn", {})
                    if turn.get("status") != "completed":
                        raise ProviderError("Codex could not complete this request. Check your plan allowance and retry.")
                    break
            try:
                result = json.loads(answer)
                tool = result["tool"]
                arguments = json.loads(result["arguments_json"] or "{}")
                if not isinstance(arguments, dict) or tool not in {"", *[t["name"] for t in tools]}:
                    raise ValueError("Invalid decision")
                reply = Reply(result["text"], [ToolCall(tool, arguments)] if tool else [])
            except (ValueError, KeyError, TypeError) as exc:
                raise ProviderError("Codex returned an invalid Macooii decision; no action was executed.", False) from exc
            if self.persistent:
                # Unload each ephemeral conversation; never reuse its private context.
                rpc.request("thread/unsubscribe", {"threadId": thread["id"]})
            return reply
        except BaseException:
            self._close()
            raise
        finally:
            if not self.persistent:
                self._close()
            elif self.rpc:
                self.rpc.task = TaskContext(lambda *args: "decline")
            self.lock.release()


def codex_status():
    task = TaskContext(lambda *args: "decline")
    with tempfile.TemporaryDirectory(prefix="macooii-codex-check-") as cwd:
        rpc = CodexRPC(task, cwd)
        try:
            return rpc.initialize()
        finally:
            rpc.close()
