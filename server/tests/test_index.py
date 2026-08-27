import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.index import QUOTA_HINT, format_embed_error, index_document
from app.main import create_app, reset_app_state
from app.models import DocumentChunk
from app.parse import parse_text_document


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_index_fake_embedding_writes_chunks_and_ready(monkeypatch):
    calls = {"n": 0}

    def counting(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        dim = get_settings().embedding_dim
        return [[0.02] * dim for _ in texts]

    monkeypatch.setattr("app.index.embed_texts", counting)
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    payload = f"index me {uuid.uuid4()} " + ("段" * 20)
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", payload.encode(), "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        indexed = client.post(f"/api/documents/{doc_id}/index")
        assert indexed.status_code == 200
        assert indexed.json()["status"] == "ready"
        session = session_scope()
        try:
            n = session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
            assert n > 0
        finally:
            session.close()
        assert calls["n"] > 0


def test_index_without_key_returns_503(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: False)
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", f"no key {uuid.uuid4()}".encode(), "text/plain")},
        )
        doc_id = res.json()["id"]
        missing = client.post(f"/api/documents/{doc_id}/index")
        assert missing.status_code == 503
        assert "Key" in missing.json()["detail"]


def test_second_upload_same_file_does_not_embed(monkeypatch):
    calls = {"n": 0}

    def counting(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        dim = get_settings().embedding_dim
        return [[0.03] * dim for _ in texts]

    monkeypatch.setattr("app.index.embed_texts", counting)
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    payload = f"same-index-bytes {uuid.uuid4()}".encode()
    with _client() as client:
        first = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", payload, "text/plain")},
        )
        doc_id = uuid.UUID(first.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)
        after_first = calls["n"]
        assert after_first > 0
        second = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", payload, "text/plain")},
        )
        assert second.json()["existed"] is True
        assert calls["n"] == after_first
    reset_app_state()


def test_quota_error_mentions_v4():
    assert "text-embedding-v4" in format_embed_error(RuntimeError("insufficient_quota"))
    assert QUOTA_HINT == format_embed_error(RuntimeError("FreeQuotaExceed"))
