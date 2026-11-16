from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine

from macooii.bridge import Bridge
from macooii.config import resource_path
from macooii.engine import Outcome


@pytest.mark.parametrize("provider", ["auto", "codex"])
def test_all_screens_load_without_qml_warnings(qapp, qtbot, store, provider):
    store.set_setting("provider", provider)
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    qapp.setFont(QFont("Figtree"))
    bridge = Bridge(store)
    qml = QQmlApplicationEngine()
    warnings = []
    qml.warnings.connect(lambda values: warnings.extend(str(x) for x in values))
    qml.rootContext().setContextProperty("backend", bridge)
    qml.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
    assert qml.rootObjects()
    window = qml.rootObjects()[0]
    for index in range(5):
        window.setProperty("currentPage", index)
        qtbot.wait(40)
    store.set_setting("speech_enabled", False)
    bridge.send("/help")
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    window.setProperty("currentPage", 0)
    qtbot.wait(100)
    assert len(store.messages()) == 2
    assert not warnings
    window.setVisible(False)
    bridge.shutdown()
    qml.deleteLater()


def test_note_editor_updates_existing_note(qapp, store):
    bridge = Bridge(store)
    identity = bridge.saveNote("First", "Original", "")
    assert identity
    bridge.saveNote("Updated", "New content", identity)
    assert len(store.notes()) == 1
    assert store.note(identity)["body"] == "New content"
    bridge.shutdown()


def test_async_command_and_private_history(qapp, qtbot, store):
    store.set_setting("speech_enabled", False)
    bridge = Bridge(store)
    bridge.send("/note My idea | Private thought")
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    assert len(store.notes()) == 1
    assert len(store.messages()) == 2
    assert all(row["sensitive"] for row in store.messages())
    bridge.shutdown()


def test_approval_handoff_and_decline(qapp, qtbot, store):
    store.set_setting("speech_enabled", False)
    bridge = Bridge(store)

    def run(text, task, status):
        task.cloud_context("Private source", "EXACT PRIVATE EXCERPT")
        return Outcome("Summary", "Gemini", True)

    bridge.engine = SimpleNamespace(run=run)
    bridge.send("Summarize my document")
    qtbot.waitUntil(lambda: bool(bridge.pendingApproval), timeout=5000)
    assert bridge.pendingApproval["text"] == "EXACT PRIVATE EXCERPT"
    bridge.resolveApproval("approve")
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    assert store.messages()[-1]["content"] == "Summary"
    bridge.shutdown()


def test_cancel_while_awaiting_approval(qapp, qtbot, store):
    store.set_setting("speech_enabled", False)
    bridge = Bridge(store)

    def run(text, task, status):
        task.cloud_context("Private", "secret")
        return Outcome("Should never appear")

    bridge.engine = SimpleNamespace(run=run)
    bridge.send("Summarize")
    qtbot.waitUntil(lambda: bool(bridge.pendingApproval), timeout=5000)
    bridge.cancel()
    qtbot.waitUntil(lambda: not bridge.busy, timeout=5000)
    assert "Should never appear" not in str(store.messages())
    bridge.shutdown()


def test_mute_does_not_cancel_unfinished_research(qapp, store):
    from macooii.privacy import TaskContext
    bridge = Bridge(store)
    bridge._task = TaskContext(lambda *args: "decline")
    bridge._busy = True
    bridge._task_answered = False
    bridge.toggleSpeech()
    assert not store.setting("speech_enabled")
    assert not bridge._task.cancelled.is_set()
    bridge._busy = False
    bridge.shutdown()
