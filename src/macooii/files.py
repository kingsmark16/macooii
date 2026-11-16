from __future__ import annotations

import os
from pathlib import Path

from .privacy import TaskContext
from .storage import Store

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT = 24_000
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "$recycle.bin", "system volume information"}


def allowed_path(value: str | Path, folders: list[str]) -> Path:
    path = Path(value).resolve(strict=True)
    roots = [Path(root).resolve() for root in folders]
    if not any(path == root or path.is_relative_to(root) for root in roots):
        raise PermissionError("This file is outside your approved folders.")
    if not path.is_file():
        raise ValueError("Select a file, not a directory.")
    return path


def extract_text(path: Path) -> tuple[str, bool]:
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError("Supported formats: TXT, Markdown, DOCX and text-based PDF.")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("This file exceeds the 20 MB extraction limit. Select a smaller document.")
    truncated = False
    if path.suffix.lower() in {".txt", ".md"}:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            text = stream.read(MAX_TEXT + 1)
    elif path.suffix.lower() == ".docx":
        from docx import Document
        document = Document(path)
        chunks = [p.text for p in document.paragraphs]
        chunks += [" | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows]
        text = "\n".join(chunks)
    else:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported. Select an unlocked copy.")
        chunks, length = [], 0
        for page in reader.pages:
            chunk = page.extract_text() or ""
            chunks.append(chunk)
            length += len(chunk)
            if length > MAX_TEXT:
                truncated = True
                break
        text = "\n".join(chunks)
    if not text.strip():
        raise ValueError("No readable text found. Scanned documents need OCR, which is not in this release.")
    return text[:MAX_TEXT], truncated or len(text) > MAX_TEXT


def find_files(query: str, store: Store, task: TaskContext) -> list[Path]:
    folders = store.setting("folders")
    if not folders:
        raise ValueError("Choose approved folders in Settings before searching local files.")
    terms = query.casefold().split()
    matches: list[Path] = []
    visited = 0
    for root in folders:
        for current, directories, files in os.walk(root, followlinks=False):
            task.check()
            directories[:] = [name for name in directories if name.casefold() not in SKIP_DIRS
                              and not (Path(current) / name).is_junction()
                              and not (Path(current) / name).is_symlink()]
            for name in files:
                visited += 1
                if visited > 15_000:
                    break
                candidate = Path(current) / name
                if all(term in name.casefold() for term in terms):
                    try:
                        candidate = allowed_path(candidate, folders)
                    except (OSError, ValueError, PermissionError):
                        continue
                    matches.append(candidate)
                    if len(matches) >= 30:
                        return matches
            if visited > 15_000:
                break
    # Previously read documents are searchable by their indexed body as well as filename.
    for item in store.search_documents(query):
        try:
            candidate = allowed_path(item, folders)
            if candidate not in matches:
                matches.append(candidate)
        except (OSError, ValueError, PermissionError):
            continue
    return matches[:30]
