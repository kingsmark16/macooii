import ctypes
from ctypes import wintypes
from types import SimpleNamespace

from macooii.app import Hotkeys


def make_keys(store, monkeypatch):
    calls = []
    user32 = ctypes.windll.user32
    monkeypatch.setattr(user32, "RegisterHotKey", lambda *args: 1)
    monkeypatch.setattr(user32, "UnregisterHotKey", lambda *args: 1)
    bridge = SimpleNamespace(store=store, settingsChanged=SimpleNamespace(connect=lambda callback: None),
                             toast=SimpleNamespace(emit=lambda value: None),
                             startRecording=lambda: calls.append("start"),
                             stopRecording=lambda: calls.append("stop"))
    keys = Hotkeys(bridge, lambda: calls.append("show"))
    return keys, calls


def test_thread_dispatched_windows_hotkeys_are_handled(qapp, store, monkeypatch):
    keys, calls = make_keys(store, monkeypatch)
    message = wintypes.MSG()
    message.message = 0x0312  # WM_HOTKEY posted to the registering thread, not a top-level window.
    message.wParam = 1
    assert keys.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message)) == (True, 0)
    assert calls == ["show"]
    message.wParam = 2
    keys.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message))
    assert calls[-2:] == ["show", "start"]
    keys.close()


def test_releasing_a_modifier_ends_push_to_talk(qapp, store, monkeypatch):
    keys, calls = make_keys(store, monkeypatch)
    monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", lambda key: 0 if key == 0x11 else 0x8000)
    keys._released()
    assert calls == ["stop"]
    keys.close()
