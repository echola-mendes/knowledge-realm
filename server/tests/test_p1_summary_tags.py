import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.index import index_document
from app.main import create_app, reset_app_state
from app.models import Document, DocumentTag, Tag
from app.parse import parse_text_document


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_summarize_and_auto_tags_keep_existing(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.index.embed_texts", lambda texts: [[0.01] * get_settings().embedding_dim for _ in texts])
    monkeypatch.setattr("app.routers.documents.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.routers.documents.summarize_document", lambda text: "假摘要")
    monkeypatch.setattr("app.routers.documents.suggest_tag_names", lambda text: ["AI生成", "保留测"])
    with _client() as client:
        created = client.post("/api/documents/notes", json={"content": "正文用于摘要与标签", "filename": "p1.md"})
        assert created.status_code == 200
        doc_id = created.json()["id"]
        parse_text_document(uuid.UUID(doc_id))
        index_document(uuid.UUID(doc_id))
        hand = client.post("/api/tags", json={"name": f"手打-{uuid.uuid4().hex[:8]}"})
        assert hand.status_code == 201
        hand_id = hand.json()["id"]
        put = client.put(f"/api/documents/{doc_id}/tags", json={"tag_ids": [hand_id]})
        assert put.status_code == 200
        pending_id = uuid.uuid4()
        session = session_scope()
        try:
            kb_id = uuid.UUID(created.json()["knowledge_base_id"])
            session.add(
                Document(
                    id=pending_id,
                    knowledge_base_id=kb_id,
                    filename="wait.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="pending",
                    byte_size=1,
                )
            )
            session.commit()
        finally:
            session.close()
        bad = client.post(f"/api/documents/{pending_id}/summarize")
        assert bad.status_code == 400
        summarized = client.post(f"/api/documents/{doc_id}/summarize")
        assert summarized.status_code == 200
        assert summarized.json()["summary"] == "假摘要"
        tagged = client.post(f"/api/documents/{doc_id}/auto-tags")
        assert tagged.status_code == 200
        tag_ids = {item for item in tagged.json()["tag_ids"]}
        assert hand_id in tag_ids
        session = session_scope()
        try:
            names = set(session.scalars(select(Tag.name)).all())
            assert "AI生成" in names
            links = list(session.scalars(select(DocumentTag).where(DocumentTag.document_id == uuid.UUID(doc_id))))
            assert len(links) >= 2
            doc = session.get(Document, uuid.UUID(doc_id))
            assert doc is not None
            assert doc.summary == "假摘要"
        finally:
            session.close()
            monkeypatch.setattr("app.routers.documents.llm_keys_ready", lambda: False)
            denied = client.post(f"/api/documents/{doc_id}/summarize")
        assert denied.status_code == 503
    reset_app_state()


def test_index_writes_overview_and_tags(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.p1.chains.summarize_document", lambda text: "上传概述")
    monkeypatch.setattr("app.p1.chains.suggest_tag_names", lambda text: ["自动标"])
    from app.p1.chains import enrich_document_after_ready

    monkeypatch.setattr("app.index._enrich_after_index", enrich_document_after_ready)
    with _client() as client:
        created = client.post("/api/documents/notes", json={"content": "用于上传概述的正文", "filename": "overview.md"})
        assert created.status_code == 200
        doc_id = created.json()["id"]
        parse_text_document(uuid.UUID(doc_id))
        index_document(uuid.UUID(doc_id))
        listed = client.get("/api/documents")
        row = next(item for item in listed.json() if item["id"] == doc_id)
        assert row["summary"] == "上传概述"
        assert row["tag_ids"]
    reset_app_state()
