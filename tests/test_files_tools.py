from pathlib import Path

import pytest
from docx import Document
from pydantic import ValidationError
from pypdf import PdfWriter

from macooii.files import MAX_TEXT, allowed_path, extract_text
from macooii.tools import ToolRegistry, tool_error


def test_folder_boundary_and_revocation(store, task, tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    document = root / "proposal.txt"
    document.write_text("Private project details", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    store.set_setting("folders", [str(root)])
    tools = ToolRegistry(store)
    result = tools.execute("search_files", {"query": "proposal"}, task)
    assert result.private
    file_id = result.data["files"][0]["id"]
    assert tools.execute("read_file", {"file_id": file_id}, task).data["text"] == "Private project details"
    with pytest.raises(PermissionError):
        allowed_path(outside, [str(root)])
    with pytest.raises(PermissionError):
        allowed_path(root / ".." / "secret.txt", [str(root)])
    store.set_setting("folders", [])
    with pytest.raises(PermissionError):
        tools.execute("read_file", {"file_id": file_id}, task)


def test_real_docx_tables_and_truncated_text(tmp_path):
    document = Document()
    document.add_paragraph("Important project")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Budget"
    table.cell(0, 1).text = "100"
    path = tmp_path / "proposal.docx"
    document.save(path)
    text, truncated = extract_text(path)
    assert "Important project" in text and "Budget | 100" in text
    assert not truncated
    plain = tmp_path / "long.md"
    plain.write_text("x" * (MAX_TEXT + 10))
    text, truncated = extract_text(plain)
    assert len(text) == MAX_TEXT and truncated


def test_scanned_encrypted_and_unsupported_files(tmp_path):
    blank = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(blank)
    with pytest.raises(ValueError, match="OCR"):
        extract_text(blank)
    encrypted = tmp_path / "protected.pdf"
    writer.encrypt("secret")
    writer.write(encrypted)
    with pytest.raises(ValueError, match="Password"):
        extract_text(encrypted)
    with pytest.raises(ValueError, match="Supported"):
        extract_text(Path("example.exe"))


def test_tool_validation_and_private_errors(store, task):
    registry = ToolRegistry(store)
    with pytest.raises(ValueError, match="arbitrary"):
        registry.execute("run_shell", {"command": "anything"}, task)
    with pytest.raises(ValidationError):
        registry.execute("open_app", {"app": "Chrome", "command": "extra"}, task)
    with pytest.raises(ValueError, match="Unknown file"):
        registry.execute("read_file", {"file_id": "Fdeadbeef"}, task)
    assert "sensitive-path" not in tool_error(FileNotFoundError("sensitive-path"))


def test_unregistered_app_never_spawns(store, task, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("An unregistered app attempted to spawn")
    monkeypatch.setattr("macooii.tools.subprocess.Popen", forbidden)
    with pytest.raises(ValueError, match="not registered"):
        ToolRegistry(store).execute("open_app", {"app": "invented.exe"}, task)
