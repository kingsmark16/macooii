from datetime import UTC, datetime, timedelta

from macooii.storage import Store


def test_note_edit_search_delete_and_restart(store):
    note_id = store.save_note("Project", "A useful proposal")
    assert store.notes("proposal")[0]["id"] == note_id
    store.save_note("Project updated", "Different content", note_id)
    assert not store.notes("proposal")
    restarted = Store(store.root)
    assert restarted.note(note_id)["body"] == "Different content"
    assert len(restarted.notes()) == 1
    restarted.delete_note(note_id)
    assert not restarted.notes()


def test_explicit_memory_update_delete_persist(store):
    identity = store.remember("I prefer Taglish")
    store.remember("I prefer English", identity)
    assert Store(store.root).memories()[0]["body"] == "I prefer English"
    store.forget(identity)
    assert not store.memories()


def test_history_retention_keeps_notes_and_memories(store):
    store.save_note("Keep", "Persist me")
    store.remember("Remember me")
    store.add_message("user", "Old chat")
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    with store.connection() as db:
        db.execute("UPDATE messages SET created=?", (old,))
    store.prune()
    assert not store.messages()
    assert store.notes() and store.memories()


def test_settings_and_fts_are_parameterized(store):
    store.save_note("SQL", "normal")
    assert store.notes("' OR 1=1 --") == []
    store.set_setting("folders", ["C:/Example"])
    assert Store(store.root).setting("folders") == ["C:/Example"]


def test_sensitive_message_marker(store):
    identity = store.add_message("assistant", "private", True)
    assert store.messages()[0]["sensitive"]
    store.mark_sensitive(identity, False)
    assert not store.messages()[0]["sensitive"]


def test_removing_all_apps_stays_revoked_after_restart(store):
    store.set_setting("apps", {})
    assert Store(store.root).setting("apps") == {}
