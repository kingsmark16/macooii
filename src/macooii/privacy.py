from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field


class Cancelled(Exception):
    pass


class SharingDeclined(PermissionError):
    pass


@dataclass
class TaskContext:
    approve: Callable[[str, str], str]
    before_action: Callable[[str], None] | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    sensitive: bool = False
    private_sources_used: bool = False
    current_message_id: int | None = None
    approved: set[str] = field(default_factory=set)
    declined: set[str] = field(default_factory=set)
    source_records: dict = field(default_factory=dict)
    local_cards: list[dict] = field(default_factory=list)
    voice_acknowledged: bool = False
    voice_action_announced: bool = False
    # Store only displayed excerpts in approved, not a blanket folder permission.

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled("Task cancelled")

    def cloud_context(self, label: str, text: str, provider: str = "Google Gemini") -> str:
        return self._share(provider, label, text, allow_local=True)

    def external_context(self, provider: str, label: str, text: str) -> str:
        return self._share(provider, label, text, allow_local=False)

    def _share(self, provider: str, label: str, text: str, allow_local: bool) -> str:
        self.check()
        self.sensitive = True
        digest = hashlib.sha256((provider + "\0" + label + "\0" + text).encode()).hexdigest()
        if digest in self.declined:
            raise SharingDeclined("Sharing was already declined for this context. Continue without it or use Local mode.")
        if digest not in self.approved:
            choice = self.approve(provider + "\n" + label, text)
            self.check()
            if choice == "local" and allow_local:
                raise LocalRequested("Use local processing for this task")
            if choice != "approve":
                self.declined.add(digest)
                raise SharingDeclined("Sharing declined. This source was not sent. You can use Local mode instead.")
            self.approved.add(digest)
        return text


class LocalRequested(Exception):
    pass
