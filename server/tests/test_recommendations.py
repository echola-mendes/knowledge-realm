from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Conversation, Document, Favorite, KnowledgeBase, Message, User
from app.passwords import hash_password
from http_client import TEST_PASSWORD, api_client
from sqlalchemy import select, func


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return api_client()

def _client_as(username: str, password: str = TEST_PASSWORD) -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    session = session_scope()
    try:
        if not session.scalar(select(User).where(User.username == username)):
            session.add(User(username=username, password_hash=hash_password(password)))
            session.commit()
    finally:
        session.close()
    client = TestClient(create_app(load_file=True, ensure_default=False))
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    return client



def test_recommendations_empty_for_new_user(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    with _client_as(f"reco-empty-{uuid.uuid4().hex[:8]}") as client:
        res = client.get("/api/recommendations")
        assert res.status_code == 200
        assert res.json() == []
    reset_app_state()


def test_recommendations_from_favorites_and_citations(monkeypatch):
    """收藏与 citation 文档作为种子，相似文档被推荐；种子与已收藏被排除。"""
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.rag.search.embed_texts", lambda texts: [[0.9] * 1024 for _ in texts])
    monkeypatch.setattr("app.rag.search.require_elasticsearch_url", lambda: None)

    from app.rag.search import SearchHit

    similar_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_name = f"reco-fav-{uuid.uuid4().hex[:8]}"

    def fake_search_chunks(session, query, *, user_id, knowledge_base_id=None, **kw):
        return [
            SearchHit(
                document_id=similar_id,
                document_name="相似文档.md",
                chunk_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                content="相似内容",
                score=0.85,
                page=None,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr("app.recommendations.search_chunks", fake_search_chunks)

    with _client_as(user_name) as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"推荐-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = kb["id"]
        session = session_scope()
        try:
            seed = Document(
                knowledge_base_id=uuid.UUID(kb_id),
                filename="seed.md",
                ext=".md",
                kind="note",
                checksum=uuid.uuid4().hex,
                status="ready",
                byte_size=1,
                summary="种子摘要",
            )
            similar = Document(
                id=similar_id,
                knowledge_base_id=uuid.UUID(kb_id),
                filename="相似文档.md",
                ext=".md",
                kind="note",
                checksum=uuid.uuid4().hex,
                status="ready",
                byte_size=1,
                summary="相似摘要",
            )
            session.add_all([seed, similar])
            session.flush()
            session.add(Favorite(user_id=uuid.UUID(client.get("/api/auth/me").json()["id"]), document_id=seed.id))
            session.commit()
        finally:
            session.close()

        res = client.get("/api/recommendations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["document_name"] == "相似文档.md"
        assert data[0]["document_id"] == str(similar_id)
    reset_app_state()


def test_recommendations_cross_user_isolation(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.rag.search.embed_texts", lambda texts: [[0.9] * 1024 for _ in texts])
    monkeypatch.setattr("app.rag.search.require_elasticsearch_url", lambda: None)
    owner_name = f"reco-owner-{uuid.uuid4().hex[:8]}"

    from app.rag.search import SearchHit

    def fake_search_chunks(session, query, *, user_id, knowledge_base_id=None, **kw):
        return [
            SearchHit(
                document_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                document_name="他人相似.md",
                chunk_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
                content="x",
                score=0.5,
                page=None,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr("app.recommendations.search_chunks", fake_search_chunks)

    with _client_as(owner_name) as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"推荐隔离-{uuid.uuid4().hex[:8]}"}).json()
        session = session_scope()
        try:
            seed = Document(
                knowledge_base_id=uuid.UUID(kb["id"]),
                filename="seed.md",
                ext=".md",
                kind="note",
                checksum=uuid.uuid4().hex,
                status="ready",
                byte_size=1,
                summary="x",
            )
            session.add(seed)
            session.flush()
            session.add(Favorite(user_id=uuid.UUID(client.get("/api/auth/me").json()["id"]), document_id=seed.id))
            session.commit()
        finally:
            session.close()

    other_name = f"r-{uuid.uuid4().hex[:10]}"
    session = session_scope()
    try:
        session.add(User(username=other_name, password_hash=hash_password(TEST_PASSWORD)))
        session.commit()
    finally:
        session.close()

    other = TestClient(create_app(load_file=True, ensure_default=False))
    login = other.post("/api/auth/login", json={"username": other_name, "password": TEST_PASSWORD})
    assert login.status_code == 200
    res = other.get("/api/recommendations")
    assert res.status_code == 200
    assert res.json() == []
    reset_app_state()


def test_recommendations_limit_five(monkeypatch):
    """即使种子很多，返回不超过 5 条。"""
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.rag.search.embed_texts", lambda texts: [[0.9] * 1024 for _ in texts])
    monkeypatch.setattr("app.rag.search.require_elasticsearch_url", lambda: None)
    limit_user = f"reco-limit-{uuid.uuid4().hex[:8]}"

    from app.rag.search import SearchHit

    similar_uuids = [uuid.UUID(f"0000000{i}-0000-0000-0000-000000000000") for i in range(1, 6)]

    def fake_search_chunks(session, query, *, user_id, knowledge_base_id=None, **kw):
        idx = (fake_search_chunks._call_count % 5)
        fake_search_chunks._call_count += 1
        return [
            SearchHit(
                document_id=similar_uuids[idx],
                document_name=f"doc{idx}.md",
                chunk_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                content="x",
                score=0.8,
                page=None,
                heading=None,
                kind="note",
            )
        ]

    fake_search_chunks._call_count = 0
    monkeypatch.setattr("app.recommendations.search_chunks", fake_search_chunks)

    with _client_as(limit_user) as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"推荐上限-{uuid.uuid4().hex[:8]}"}).json()
        session = session_scope()
        try:
            similars = [
                Document(
                    id=similar_uuids[i],
                    knowledge_base_id=uuid.UUID(kb["id"]),
                    filename=f"doc{i}.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary=f"相似{i}",
                )
                for i in range(5)
            ]
            session.add_all(similars)
            for i in range(10):
                seed = Document(
                    knowledge_base_id=uuid.UUID(kb["id"]),
                    filename=f"seed{i}.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary=f"种子{i}",
                )
                session.add(seed)
                session.flush()
                session.add(Favorite(user_id=uuid.UUID(client.get("/api/auth/me").json()["id"]), document_id=seed.id))
            session.commit()
        finally:
            session.close()

        res = client.get("/api/recommendations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) <= 5
    reset_app_state()
