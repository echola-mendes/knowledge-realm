import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.models import DocumentChunk
from app.ingest.parse import parse_text_document
from app.ingest.storage import original_path, parsed_dir


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_reindex_after_original_change(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    old = f"OLDTOKEN {uuid.uuid4()}"
    new = f"NEWTOKEN {uuid.uuid4()}"
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", old.encode(), "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        parsed = client.get(f"/api/documents/{doc_id}/parsed.md")
        assert parsed.status_code == 200
        assert old in parsed.text
        index_document(doc_id)
        original_path(doc_id, ".txt").write_bytes(new.encode())
        again = client.post(f"/api/documents/{doc_id}/reindex")
        assert again.status_code == 200
        assert again.json()["status"] == "ready"
        session = session_scope()
        try:
            texts = list(
                session.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id == doc_id))
            )
            assert any(new in t for t in texts)
            assert not any(old in t for t in texts)
        finally:
            session.close()


def test_delete_document_removes_row_and_files(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("del.txt", f"to-delete {uuid.uuid4()}".encode(), "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)
        path = original_path(doc_id, ".txt")
        parsed = parsed_dir(doc_id)
        assert path.is_file()
        gone = client.delete(f"/api/documents/{doc_id}")
        assert gone.status_code == 200
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert not path.exists()
        assert not parsed.exists()


def test_list_document_chunks(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.ingest.index.embed_texts", lambda texts: [[0.0] * 1024 for _ in texts])
    monkeypatch.setattr("app.ingest.index.process_document", lambda _document_id: None)
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("chunks.txt", f"hello chunk list {uuid.uuid4()}".encode(), "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        pending = client.get(f"/api/documents/{doc_id}/chunks")
        assert pending.status_code == 200
        rows = pending.json()
        assert rows
        assert all(r["vector_status"] == "pending" for r in rows)
        assert rows[0]["created_at"] is None
        index_document(doc_id)
        ready = client.get(f"/api/documents/{doc_id}/chunks")
        assert ready.status_code == 200
        ready_rows = ready.json()
        assert ready_rows
        assert all(r["vector_status"] == "ready" for r in ready_rows)
        assert ready_rows[0]["id"]
        assert ready_rows[0]["chunk_label"].startswith("Chunk_")
        assert ready_rows[0]["created_at"]


def test_reindex_single_chunk(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    calls: list[list[str]] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[float(len(calls))] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr("app.ingest.index.embed_texts", fake_embed)
    monkeypatch.setattr("app.ingest.index.process_document", lambda _document_id: None)
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("one.txt", f"single chunk reindex {uuid.uuid4()}".encode(), "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)
        listed = client.get(f"/api/documents/{doc_id}/chunks")
        assert listed.status_code == 200
        chunk_id = listed.json()[0]["id"]
        before_calls = len(calls)
        again = client.post(f"/api/documents/{doc_id}/chunks/{chunk_id}/reindex")
        assert again.status_code == 200, again.text
        body = again.json()
        assert body["id"] == chunk_id
        assert body["vector_status"] == "ready"
        assert len(calls) == before_calls + 1
        assert len(calls[-1]) == 1


def test_list_includes_error_message():
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("blank.txt", b"  \n  ", "text/plain")},
        )
        doc_id = res.json()["id"]
        parse_text_document(uuid.UUID(doc_id))
        listed = client.get("/api/documents")
        assert listed.status_code == 200
        row = next(item for item in listed.json() if item["id"] == doc_id)
        assert row["error_message"] is not None
        assert "empty_content" in row["error_message"]
        assert row["status"] == "parse_failed"
        assert row["source_path"]
        detail = client.get(f"/api/documents/{doc_id}")
        assert detail.json()["error_message"] == row["error_message"]
    reset_app_state()
