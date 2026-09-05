from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.models import Document


def parsed_dir(document_id: uuid.UUID) -> Path:
    return get_settings().data_dir / "parsed" / str(document_id)


def files_dir() -> Path:
    return get_settings().data_dir / "files"


def original_path(document_id: uuid.UUID, ext: str) -> Path:
    year = str(datetime.now().year)
    suffix = ext if ext.startswith(".") else f".{ext}"
    return files_dir() / year / f"{document_id}{suffix}"


def write_original(document_id: uuid.UUID, ext: str, data: bytes) -> Path:
    path = original_path(document_id, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def remove_document_files(doc: Document) -> None:
    parsed = parsed_dir(doc.id)
    if parsed.is_dir():
        shutil.rmtree(parsed)
    files_root = files_dir()
    if not files_root.is_dir():
        return
    for path in files_root.rglob(f"{doc.id}{doc.ext if doc.ext.startswith('.') else '.' + doc.ext}"):
        path.unlink(missing_ok=True)
    for path in files_root.rglob(f"{doc.id}.*"):
        path.unlink(missing_ok=True)


def remove_knowledge_base_files(documents: list[Document]) -> None:
    for doc in documents:
        remove_document_files(doc)
