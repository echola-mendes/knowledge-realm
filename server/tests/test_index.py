import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.ingest.index import QUOTA_HINT, format_embed_error, index_document
from app.main import create_app, reset_app_state
from app.models import DocumentChunk
from app.ingest.parse import parse_text_document


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

    monkeypatch.setattr("app.ingest.index.embed_texts", counting)
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
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
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: False)
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

    monkeypatch.setattr("app.ingest.index.embed_texts", counting)
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
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


def test_index_parent_child_long_section_es_only_children(monkeypatch):
    """长节落库 parent+children；ES upsert 仅 child。"""
    es_calls: list[list] = []

    def fake_upsert(chunks):
        es_calls.append(list(chunks))

    monkeypatch.setattr("app.ingest.index.upsert_chunks", fake_upsert)
    monkeypatch.setattr("app.ingest.index.delete_document_chunks", lambda *_a, **_k: None)
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr(
        "app.ingest.index.embed_texts",
        lambda texts: [[0.01] * get_settings().embedding_dim for _ in texts],
    )
    monkeypatch.setattr("app.ingest.index._enrich_after_index", lambda *_a, **_k: None)

    from app.models import Document
    from app.ingest.storage import parsed_dir

    body = "甲" * 900
    md = f"# 长节\n\n{body}"
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"PC-{uuid.uuid4().hex[:8]}"}).json()
        doc = client.post(
            "/api/documents/notes",
            json={"knowledge_base_id": kb["id"], "content": md},
        ).json()
        doc_id = uuid.UUID(doc["id"])
        parsed_dir(doc_id).mkdir(parents=True, exist_ok=True)
        parsed_dir(doc_id).joinpath("document.md").write_text(md, encoding="utf-8")
        with session_scope() as session:
            row = session.get(Document, doc_id)
            assert row is not None
            row.status = "parsed"
            session.commit()
        index_document(doc_id)

    with session_scope() as session:
        rows = list(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc_id)
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )
        parents = [r for r in rows if r.role == "parent"]
        children = [r for r in rows if r.role == "child"]
        assert len(parents) == 1
        assert len(children) >= 2
        assert parents[0].embedding is None
        assert all(c.parent_id == parents[0].id for c in children)
        assert all(c.embedding is not None for c in children)
        parent_ids = {p.id for p in parents}
        child_ids = {c.id for c in children}

    assert es_calls, "upsert_chunks should be called"
    es_ids = {t[0] for t in es_calls[-1]}
    assert es_ids == child_ids
    assert not (es_ids & parent_ids)

    from app.chains import gather_document_text
    from app.ingest import index as index_mod
    from app.ingest.chunk import split_markdown_sections
    from app.routers.documents import _chunks_for_document

    sections = split_markdown_sections(md)
    assert any(k[0] == "parent" for k in index_mod._align_keys_from_sections(sections))
    with session_scope() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        gathered = gather_document_text(session, doc)
        parent_content = session.scalars(
            select(DocumentChunk).where(
                DocumentChunk.document_id == doc_id, DocumentChunk.role == "parent"
            )
        ).one().content
        # 旁路只拼 child：父全文不应作为独立重复段出现在「仅父」场景下的双倍长度
        child_rows = _chunks_for_document(doc, session)
        assert len(child_rows) == len(children)
        assert parent_content not in [c.content for c in child_rows]
        assert gathered  # non-empty from children
