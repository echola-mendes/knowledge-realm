import uuid
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.kb import resolve_knowledge_base_id
from app.user import ensure_default_user
from app.main import create_app, reset_app_state
from app.models import Document
from app.routers import documents as documents_mod
from app.storage import original_path
from sqlalchemy import func, select


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_upload_txt_saves_file_and_defaults_kb():
    with _client() as client:
        payload = f"hello knowledge {uuid.uuid4()}".encode()
        res = client.post(
            "/api/documents/upload",
            files={"file": ("note.TXT", payload, "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["existed"] is False
        assert body["status"] in (
            "pending",
            "parsing",
            "parsed",
            "indexing",
            "ready",
            "index_failed",
        )
        assert body["kind"] == "txt"
        doc_id = uuid.UUID(body["id"])
        path = original_path(doc_id, ".txt")
        assert path.is_file()
        assert path.read_bytes() == payload
        session = session_scope()
        try:
            default_id = resolve_knowledge_base_id(session, None, ensure_default_user(session).id)
            assert uuid.UUID(body["knowledge_base_id"]) == default_id
        finally:
            session.close()


def test_reject_exe_and_oversize(monkeypatch):
    with _client() as client:
        bad = client.post(
            "/api/documents/upload",
            files={"file": ("virus.exe", b"xx", "application/octet-stream")},
        )
        assert bad.status_code == 400
        monkeypatch.setattr(documents_mod, "UPLOAD_MAX_BYTES", 5)
        big = client.post(
            "/api/documents/upload",
            files={"file": ("big.txt", b"123456", "text/plain")},
        )
        assert big.status_code == 400


def test_same_file_second_upload_skips_insert():
    payload = f"same-bytes-twice {uuid.uuid4()}".encode()
    with _client() as client:
        first = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", payload, "text/plain")},
        )
        second = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", payload, "text/plain")},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["existed"] is True
        assert first.json()["id"] == second.json()["id"]
        session = session_scope()
        try:
            kb_id = uuid.UUID(first.json()["knowledge_base_id"])
            checksum = first.json()["checksum"]
            n = session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
            )
            assert n == 1
        finally:
            session.close()
    reset_app_state()
