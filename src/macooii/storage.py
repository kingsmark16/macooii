from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import DEFAULTS, default_apps


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "macooii.db"
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT,
                    sensitive INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, title TEXT, body TEXT,
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(id UNINDEXED, title, body);
                CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, body TEXT, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, action TEXT, status TEXT,
                    created TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(path UNINDEXED, body);
            """)
        with self.connection() as db:
            apps_initialized = db.execute("SELECT 1 FROM settings WHERE key='apps'").fetchone()
        if not apps_initialized:
            self.set_setting("apps", default_apps())
        self.prune()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def setting(self, key: str):
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else DEFAULTS.get(key)

    def set_setting(self, key: str, value):
        if key not in DEFAULTS:
            raise ValueError("Unknown setting")
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def settings(self) -> dict:
        return {key: self.setting(key) for key in DEFAULTS}

    def add_message(self, role: str, content: str, sensitive: bool = False):
        with self.connection() as db:
            cursor = db.execute("INSERT INTO messages(role,content,sensitive,created) VALUES (?,?,?,?)",
                                (role, content, int(sensitive), now()))
            return cursor.lastrowid

    def mark_sensitive(self, message_id: int, sensitive: bool):
        with self.connection() as db:
            db.execute("UPDATE messages SET sensitive=? WHERE id=?", (int(sensitive), message_id))

    def messages(self, limit: int = 80) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_history(self):
        with self.connection() as db:
            db.execute("DELETE FROM messages")

    def prune(self):
        cutoff = (datetime.now(UTC) - timedelta(days=int(self.setting("history_days")))).isoformat()
        with self.connection() as db:
            db.execute("DELETE FROM messages WHERE created < ?", (cutoff,))
            db.execute("DELETE FROM activity WHERE created < ?", (cutoff,))

    def save_note(self, title: str, body: str, note_id: str | None = None) -> str:
        note_id = note_id or uuid.uuid4().hex
        stamp = now()
        with self.connection() as db:
            db.execute("""INSERT INTO notes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE
                       SET title=excluded.title, body=excluded.body, updated=excluded.updated""",
                       (note_id, title, body, stamp, stamp))
            db.execute("DELETE FROM notes_fts WHERE id=?", (note_id,))
            db.execute("INSERT INTO notes_fts VALUES (?,?,?)", (note_id, title, body))
        return note_id

    def notes(self, query: str = "") -> list[dict]:
        with self.connection() as db:
            if query.strip():
                term = '"' + query.strip().replace('"', '""') + '"'
                rows = db.execute("SELECT n.* FROM notes n JOIN notes_fts f ON n.id=f.id "
                                  "WHERE notes_fts MATCH ? ORDER BY n.updated DESC LIMIT 100", (term,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM notes ORDER BY updated DESC LIMIT 200").fetchall()
        return [dict(row) for row in rows]

    def note(self, note_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not row:
            raise ValueError("Note not found")
        return dict(row)

    def delete_note(self, note_id: str):
        with self.connection() as db:
            db.execute("DELETE FROM notes WHERE id=?", (note_id,))
            db.execute("DELETE FROM notes_fts WHERE id=?", (note_id,))

    def remember(self, body: str, memory_id: str | None = None) -> str:
        memory_id = memory_id or uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO memories VALUES (?,?,?)", (memory_id, body, now()))
        return memory_id

    def memories(self) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM memories ORDER BY created DESC")]

    def forget(self, memory_id: str):
        with self.connection() as db:
            db.execute("DELETE FROM memories WHERE id=?", (memory_id,))

    def log(self, action: str, status: str):
        # Only tool names and status codes. Never store tool arguments or secrets in diagnostics.
        with self.connection() as db:
            db.execute("INSERT INTO activity(action,status,created) VALUES (?,?,?)", (action, status, now()))

    def activity(self) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 100")]

    def index_document(self, path: Path, body: str):
        with self.connection() as db:
            db.execute("DELETE FROM documents WHERE path=?", (str(path),))
            db.execute("INSERT INTO documents VALUES (?,?)", (str(path), body[:100_000]))

    def search_documents(self, query: str) -> list[str]:
        term = '"' + query.strip().replace('"', '""') + '"'
        with self.connection() as db:
            return [row[0] for row in db.execute("SELECT path FROM documents WHERE documents MATCH ? LIMIT 30",
                                                (term,))]

    def clear_index(self):
        with self.connection() as db:
            db.execute("DELETE FROM documents")
