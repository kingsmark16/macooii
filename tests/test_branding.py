from macooii.config import data_dir
from macooii.engine import Engine
from macooii.privacy import TaskContext


def test_default_data_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("MACOOII_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert data_dir() == tmp_path / "Macooii"


def test_data_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MACOOII_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_assistant_name_accepts_commands(store):
    outcome = Engine(store, lambda: "").direct("Macooii, /help", TaskContext(lambda *a: "decline"))
    assert outcome and "Read with Macooii" in outcome.text
