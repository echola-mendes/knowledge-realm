from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Document, DocumentChunk, Entity, EntityLink, KnowledgeBase, User
from app.passwords import hash_password
from http_client import TEST_PASSWORD, api_client


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def test_search_graph_returns_linked_documents():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"图谱-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = uuid.UUID(kb["id"])
        session = session_scope()
        try:
            doc = Document(
                knowledge_base_id=kb_id,
                filename="doc.md",
                ext=".md",
                kind="note",
                checksum=uuid.uuid4().hex,
                status="ready",
                byte_size=1,
                summary="",
            )
            session.add(doc)
            session.flush()
            session.add(DocumentChunk(document_id=doc.id, chunk_index=0, chunk_label=doc.id.hex[:16], content="退款政策说明", page=1, embedding=[0.0] * 1024))
            session.flush()
            e1 = Entity(knowledge_base_id=kb_id, name="退款政策", type="concept")
            e2 = Entity(knowledge_base_id=kb_id, name="退款周期", type="concept")
            session.add_all([e1, e2])
            session.flush()
            session.add(EntityLink(from_id=e1.id, to_id=e2.id, rel="包含", document_id=doc.id))
            session.commit()

            res = client.get(f"/api/graph/search?knowledge_base_id={kb_id}&query=退款")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["document_id"] == str(doc.id)
            assert data[0]["document_name"] == "doc.md"
        finally:
            session.close()
    reset_app_state()


def test_search_graph_respects_kb_isolation():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"图谱隔离-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = uuid.UUID(kb["id"])
        other_kb = client.post("/api/knowledge-bases", json={"name": f"图谱其他-{uuid.uuid4().hex[:8]}"}).json()
        other_kb_id = uuid.UUID(other_kb["id"])

        session = session_scope()
        try:
            doc = Document(knowledge_base_id=kb_id, filename="a.md", ext=".md", kind="note", checksum=uuid.uuid4().hex, status="ready", byte_size=1)
            other_doc = Document(knowledge_base_id=other_kb_id, filename="b.md", ext=".md", kind="note", checksum=uuid.uuid4().hex, status="ready", byte_size=1)
            session.add_all([doc, other_doc])
            session.flush()
            session.add_all([
                DocumentChunk(document_id=doc.id, chunk_index=0, chunk_label=doc.id.hex[:16], content="关键词 a", page=1, embedding=[0.0] * 1024),
                DocumentChunk(document_id=other_doc.id, chunk_index=0, chunk_label=other_doc.id.hex[:16], content="关键词 b", page=1, embedding=[0.0] * 1024),
            ])
            session.flush()
            e1 = Entity(knowledge_base_id=kb_id, name="关键词", type="concept")
            e2 = Entity(knowledge_base_id=other_kb_id, name="关键词", type="concept")
            session.add_all([e1, e2])
            session.flush()
            session.add(EntityLink(from_id=e1.id, to_id=e1.id, rel="自指", document_id=doc.id))
            session.add(EntityLink(from_id=e2.id, to_id=e2.id, rel="自指", document_id=other_doc.id))
            session.commit()

            res = client.get(f"/api/graph/search?knowledge_base_id={kb_id}&query=关键词")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["document_id"] == str(doc.id)
        finally:
            session.close()
    reset_app_state()


def test_search_graph_empty_query():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"图谱空-{uuid.uuid4().hex[:8]}"}).json()
        res = client.get(f"/api/graph/search?knowledge_base_id={kb['id']}&query=")
        assert res.status_code == 200
        assert res.json() == []
    reset_app_state()


def test_search_graph_cross_user_404():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"图谱跨用户-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = kb["id"]

    other_name = f"sg-{uuid.uuid4().hex[:10]}"
    session = session_scope()
    try:
        session.add(User(username=other_name, password_hash=hash_password(TEST_PASSWORD)))
        session.commit()
    finally:
        session.close()

    other = TestClient(create_app(load_file=True, ensure_default=False))
    login = other.post("/api/auth/login", json={"username": other_name, "password": TEST_PASSWORD})
    assert login.status_code == 200
    res = other.get(f"/api/graph/search?knowledge_base_id={kb_id}&query=x")
    assert res.status_code == 404
    reset_app_state()
