from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.chunk import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, split_markdown
from app.chunk_settings import get_user_chunk_settings, upsert_user_chunk_settings
from app.db import session_scope
from app.index import process_document
from app.models import Document, DocumentChunk, KnowledgeBase, User, UserChunkSetting
from app.passwords import hash_password
from http_client import api_client


def test_get_defaults_without_row():
    with api_client() as client:
        res = client.get("/api/chunk-settings")
        assert res.status_code == 200, res.text
        assert res.json() == {
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
        }


def test_put_then_get_and_split_uses_settings():
    with api_client() as client:
        put = client.put("/api/chunk-settings", json={"chunk_size": 200, "chunk_overlap": 20})
        assert put.status_code == 200, put.text
        assert put.json() == {"chunk_size": 200, "chunk_overlap": 20}
        got = client.get("/api/chunk-settings")
        assert got.json() == {"chunk_size": 200, "chunk_overlap": 20}
        me = client.get("/api/auth/me").json()
        session = session_scope()
        try:
            cfg = get_user_chunk_settings(session, uuid.UUID(me["id"]))
            assert cfg.chunk_size == 200
            assert cfg.chunk_overlap == 20
        finally:
            session.close()
        body = "甲" * 500
        md = f"# 一\n\n{body}"
        chunks = split_markdown(md, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for item in chunks[:-1]:
            assert len(item.content) <= 200


def test_put_rejects_overlap_ge_size():
    with api_client() as client:
        res = client.put("/api/chunk-settings", json={"chunk_size": 100, "chunk_overlap": 100})
        assert res.status_code == 422


def test_other_user_keeps_defaults():
    with api_client() as client:
        assert client.put("/api/chunk-settings", json={"chunk_size": 300, "chunk_overlap": 30}).status_code == 200
    session = session_scope()
    try:
        other = User(username=f"other-{uuid.uuid4().hex[:8]}", password_hash=hash_password("x"))
        session.add(other)
        session.commit()
        cfg = get_user_chunk_settings(session, other.id)
        assert cfg.chunk_size == DEFAULT_CHUNK_SIZE
        assert cfg.chunk_overlap == DEFAULT_CHUNK_OVERLAP
        assert session.get(UserChunkSetting, other.id) is None
    finally:
        session.close()


def test_change_settings_does_not_rewrite_existing_chunks():
    with api_client() as client:
        note = client.post(
            "/api/documents/notes",
            json={"content": "# T\n\n" + ("字" * 900), "filename": "chunk-settings-note.md"},
        )
        assert note.status_code == 200, note.text
        doc_id = uuid.UUID(note.json()["id"])
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            if doc.status != "ready":
                process_document(doc_id)
                session.refresh(doc)
            assert doc.status == "ready", doc.error_message
            before = session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            assert before and before > 0
            stored_size = doc.chunk_size
            stored_overlap = doc.chunk_overlap
            assert stored_size is not None
            assert stored_overlap is not None
            uid = session.get(KnowledgeBase, doc.knowledge_base_id).user_id
            upsert_user_chunk_settings(session, uid, chunk_size=150, chunk_overlap=10)
            session.commit()
            session.refresh(doc)
            after = session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            assert after == before
            assert doc.chunk_size == stored_size
            assert doc.chunk_overlap == stored_overlap
            got = client.get(f"/api/documents/{doc_id}")
            assert got.status_code == 200, got.text
            body = got.json()
            assert body["chunk_size"] == stored_size
            assert body["chunk_overlap"] == stored_overlap
        finally:
            session.close()


def test_reindex_updates_document_chunk_params():
    from app.index import reindex_document

    with api_client() as client:
        note = client.post(
            "/api/documents/notes",
            json={"content": "# T\n\n" + ("字" * 900), "filename": "chunk-reindex-params.md"},
        )
        assert note.status_code == 200, note.text
        doc_id = uuid.UUID(note.json()["id"])
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            uid = session.get(KnowledgeBase, doc.knowledge_base_id).user_id
            upsert_user_chunk_settings(session, uid, chunk_size=200, chunk_overlap=20)
            session.commit()
        finally:
            session.close()
        reindex_document(doc_id)
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "ready", doc.error_message
            assert doc.chunk_size == 200
            assert doc.chunk_overlap == 20
            uid = session.get(KnowledgeBase, doc.knowledge_base_id).user_id
            upsert_user_chunk_settings(session, uid, chunk_size=400, chunk_overlap=40)
            session.commit()
            session.refresh(doc)
            assert doc.chunk_size == 200
            assert doc.chunk_overlap == 20
        finally:
            session.close()
        mid = client.get(f"/api/documents/{doc_id}")
        assert mid.json()["chunk_size"] == 200
        assert mid.json()["chunk_overlap"] == 20
        reindex_document(doc_id)
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "ready", doc.error_message
            assert doc.chunk_size == 400
            assert doc.chunk_overlap == 40
        finally:
            session.close()
        final = client.get(f"/api/documents/{doc_id}")
        assert final.json()["chunk_size"] == 400
        assert final.json()["chunk_overlap"] == 40
