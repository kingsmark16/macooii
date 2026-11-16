from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .browser import Browser
from .browser_actions import ActionBrowser
from .browser_launcher import launch_regular_browser, youtube_target
from .files import allowed_path, extract_text, find_files
from .privacy import Cancelled, SharingDeclined, TaskContext
from .storage import Store


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Empty(Arguments):
    pass


class Query(Arguments):
    query: str = Field(min_length=1, max_length=300)


class FileId(Arguments):
    file_id: str = Field(pattern=r"^F[0-9a-f]{8}$")


class NoteId(Arguments):
    note_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class NoteWrite(Arguments):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=50_000)


class AppName(Arguments):
    app: str = Field(min_length=1, max_length=100)


class URL(Arguments):
    url: str = Field(min_length=8, max_length=2000)


class MusicQuery(Arguments):
    query: str = Field(default="relaxing music", min_length=1, max_length=300)


class MediaControl(Arguments):
    action: Literal["pause", "resume", "stop"]


@dataclass
class ToolResult:
    data: dict
    private: bool = False
    label: str = ""


@dataclass
class Tool:
    args: type[Arguments]
    description: str
    method: str
    kind: Literal["read", "write"] = "read"


class ToolRegistry:
    def __init__(self, store: Store, browser: Browser | None = None):
        self.store = store
        self.browser = browser or Browser()
        self.actions = ActionBrowser(store.root)
        self.regular_media = False
        self.handles: dict[str, Path] = {}
        self.tools = {
            "list_apps": Tool(Empty, "List locally registered applications.", "list_apps"),
            "open_app": Tool(AppName, "Open or focus an explicitly registered application by name.", "open_app", "write"),
            "search_files": Tool(Query, "Find files by filename and previously indexed contents in approved folders.", "search_files"),
            "read_file": Tool(FileId, "Read extracted text from a file ID returned by search_files.", "read_file"),
            "search_web": Tool(Query, "Search public web pages. Results are links, not yet read source articles.", "search_web"),
            "read_web": Tool(URL, "Read a public article and return source text for a grounded summary.", "read_web"),
            "list_notes": Tool(Empty, "List saved note IDs and titles.", "list_notes"),
            "read_note": Tool(NoteId, "Read a saved local note.", "read_note"),
            "create_note": Tool(NoteWrite, "Save a new local note explicitly requested by the user.", "create_note", "write"),
            "list_memories": Tool(Empty, "Read explicitly saved user preferences. Requires consent before cloud use.", "list_memories"),
            "open_website": Tool(URL, "Request opening a public website in the user's regular signed-in browser. This does not control or read its tabs.", "open_website", "write"),
            "play_youtube": Tool(MusicQuery, "Find a public video and request playback in the user's regular Chrome profile. Check search_only: search fallback needs manual selection. Actual playback is not verified.", "play_youtube", "write"),
            "control_media": Tool(MediaControl, "Pause, resume or stop the YouTube player opened by Macooii.", "control_media", "write"),
        }

    def schemas(self) -> list[dict]:
        schemas = []
        for name, tool in self.tools.items():
            schema = tool.args.model_json_schema()
            schema.pop("title", None)
            for item in schema.get("properties", {}).values():
                item.pop("title", None)
            schemas.append({"name": name, "description": tool.description, "parameters": schema})
        return schemas

    def execute(self, name: str, arguments: dict, task: TaskContext) -> ToolResult:
        task.check()
        if name not in self.tools:
            raise ValueError("This capability is not available. Macooii cannot run arbitrary commands.")
        tool = self.tools[name]
        validated = tool.args.model_validate(arguments)
        task.check()
        try:
            if task.before_action and name in {"open_app", "open_website", "play_youtube", "control_media", "create_note"}:
                task.before_action(name)
                task.check()
            result = getattr(self, tool.method)(validated, task)
            self.store.log(name, "completed")
            return result
        except Cancelled:
            self.store.log(name, "cancelled")
            raise
        except Exception:
            self.store.log(name, "failed")
            raise

    def list_apps(self, args: Empty, task: TaskContext) -> ToolResult:
        return ToolResult({"apps": list(self.store.setting("apps"))})

    def open_website(self, args: URL, task: TaskContext) -> ToolResult:
        if task.private_sources_used:
            task.external_context("Public website", "Requested browser navigation", args.url)
        task.check()
        launch_regular_browser(self.store.setting("apps"), args.url)
        return ToolResult({"launch_requested": True, "url": args.url, "browser": "regular"})

    def play_youtube(self, args: MusicQuery, task: TaskContext) -> ToolResult:
        if task.private_sources_used:
            task.external_context("YouTube", "Music/video search query", args.query)
        target = youtube_target(args.query, task)
        task.check()
        launch_regular_browser(self.store.setting("apps"), target["url"])
        self.regular_media = True
        return ToolResult({**target, "playback_requested": not target["search_only"], "playing": None, "browser": "regular"})

    def control_media(self, args: MediaControl, task: TaskContext) -> ToolResult:
        if self.regular_media:
            raise ValueError("Playback is in your regular Chrome profile. Use YouTube's playback buttons; Macooii cannot verify playback controls in that window.")
        return ToolResult(self.actions.call("control", args.model_dump(), task))

    def open_app(self, args: AppName, task: TaskContext) -> ToolResult:
        apps = self.store.setting("apps")
        aliases = {"explorer": "file explorer", "files": "file explorer", "google chrome": "chrome"}
        requested = aliases.get(args.app.casefold(), args.app.casefold())
        selected = next(((name, path) for name, path in apps.items() if name.casefold() == requested), None)
        if not selected:
            raise ValueError("That app is not registered. Add it in Settings or use /apps to see registered names.")
        name, value = selected
        path = Path(value).resolve(strict=True)
        if path.suffix.casefold() != ".exe":
            raise ValueError("Registered apps must be executable .exe files.")
        task.check()
        if path.name.casefold() in {"chrome.exe", "msedge.exe"}:
            launch_regular_browser(self.store.setting("apps"), executable=path)
            return ToolResult({"success": True, "app": name, "action": "launch_requested"})
        focused = False
        if os.name == "nt":
            import win32api
            import win32con
            import win32gui
            import win32process

            windows = []
            win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd) if win32gui.IsWindowVisible(hwnd) else None, None)
            for hwnd in windows:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = win32api.OpenProcess(0x1000, False, pid)
                    try:
                        process_path = Path(win32process.GetModuleFileNameEx(process, 0)).resolve()
                    finally:
                        process.Close()
                    if process_path == path:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        focused = True
                        break
                except Exception:
                    continue
        if not focused:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.Popen([str(path)], shell=False, creationflags=flags)
        return ToolResult({"success": True, "app": name, "action": "focused" if focused else "launch_requested"})

    def search_files(self, args: Query, task: TaskContext) -> ToolResult:
        results = []
        for path in find_files(args.query, self.store, task):
            file_id = next((key for key, item in self.handles.items() if item == path), None)
            file_id = file_id or "F" + uuid.uuid4().hex[:8]
            self.handles[file_id] = path
            record = {"id": file_id, "name": path.name, "path": str(path)}
            results.append(record)
        task.local_cards.extend({"kind": "file", **item} for item in results)
        return ToolResult({"files": results, "limit": 30, "scan_limit": 15000}, True, "Local file search results")

    def read_file(self, args: FileId, task: TaskContext) -> ToolResult:
        if args.file_id not in self.handles:
            raise ValueError("Unknown file ID. Search for the file first.")
        path = allowed_path(self.handles[args.file_id], self.store.setting("folders"))
        text, truncated = extract_text(path)
        task.check()
        self.store.index_document(path, text)
        return ToolResult({"id": args.file_id, "name": path.name, "path": str(path),
                           "text": text, "truncated": truncated}, True, "Document excerpt")

    def search_web(self, args: Query, task: TaskContext) -> ToolResult:
        if task.private_sources_used:
            task.external_context("Bing web search", "Search query after reading personal context", args.query)
        data = self.browser.search(args.query, task)
        for result in data["results"]:
            task.local_cards.append({"kind": "web", "name": result["title"], "url": result["url"]})
        return ToolResult(data)

    def read_web(self, args: URL, task: TaskContext) -> ToolResult:
        if task.private_sources_used:
            task.external_context("Public website", "URL requested after reading personal context", args.url)
        data = self.browser.read(args.url, task)
        source_id = f"S{len(task.source_records) + 1}"
        task.source_records[source_id] = {"id": source_id, "name": data["title"], "url": data["url"], "kind": "web"}
        return ToolResult({"source_id": source_id, **data})

    def list_notes(self, args: Empty, task: TaskContext) -> ToolResult:
        return ToolResult({"notes": [{"id": n["id"], "title": n["title"]} for n in self.store.notes()]},
                          True, "Saved note titles")

    def read_note(self, args: NoteId, task: TaskContext) -> ToolResult:
        return ToolResult(self.store.note(args.note_id), True, "Saved note")

    def create_note(self, args: NoteWrite, task: TaskContext) -> ToolResult:
        note_id = self.store.save_note(args.title, args.body)
        return ToolResult({"saved": True, "note_id": note_id, "title": args.title})

    def list_memories(self, args: Empty, task: TaskContext) -> ToolResult:
        return ToolResult({"memories": self.store.memories()}, True, "Explicitly saved preferences")


def tool_error(exc: Exception) -> str:
    if isinstance(exc, SharingDeclined):
        return str(exc)
    if isinstance(exc, ValidationError):
        return "Invalid tool arguments. Use the declared fields and valid IDs."
    if isinstance(exc, OSError):
        return "The file or resource is missing or inaccessible. Check your selection and permissions."
    if isinstance(exc, ValueError):
        return str(exc)
    return "This operation failed. Check the selected file, application, or connection and try again."
