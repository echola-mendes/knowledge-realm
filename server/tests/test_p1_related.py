import inspect
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.ingest.index import index_document
from app.llm import CHAT_CALLS
from app.main import create_app, reset_app_state
from app.models import Document
from app.ingest.parse import parse_text_document
from app.routers import documents as documents_mod
import app.llm as llm_mod


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def _directional_embed(texts: list[str]) -> list[list[float]]:
    dim = get_settings().embedding_dim
    vectors = []
    for text in texts:
        vec = [0.0] * dim
        if "苹果" in text:
            vec[0] = 1.0
        elif "橙子" in text:
            vec[1] = 1.0
        else:
            vec[2] = 1.0
        vectors.append(vec)
    return vectors


def test_related_excludes_self_and_finds_same_kb(monkeypatch):
    src = inspect.getsource(documents_mod.list_related_documents)
    assert "search_chunks" in src
    assert "/api/search" not in src
    assert "langgraph" not in src
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.rag.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.ingest.index.embed_texts", _directional_embed)
    llm_mod.CHAT_CALLS = 0
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"关联-{uuid.uuid4().hex[:8]}"}).json()
        apple = client.post(
            "/api/documents/notes",
            json={"content": "无关说明文字", "filename": "a.md", "knowledge_base_id": kb["id"]},
        )
        neighbor = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果", "filename": "b.md", "knowledge_base_id": kb["id"]},
        )
        orange = client.post(
            "/api/documents/notes",
            json={"content": "文档讲橙子", "filename": "c.md", "knowledge_base_id": kb["id"]},
        )
        apple_id = apple.json()["id"]
        neighbor_id = neighbor.json()["id"]
        orange_id = orange.json()["id"]
        for doc_id in (apple_id, neighbor_id, orange_id):
            parse_text_document(uuid.UUID(doc_id))
            index_document(uuid.UUID(doc_id))
        session = session_scope()
        try:
            row = session.get(Document, uuid.UUID(apple_id))
            assert row is not None
            row.summary = "苹果"
            session.commit()
        finally:
            session.close()
        related = client.get(f"/api/documents/{apple_id}/related")
        assert related.status_code == 200
        body = related.json()
        ids = [item["document_id"] for item in body]
        assert apple_id not in ids
        assert neighbor_id in ids
        hit = next(item for item in body if item["document_id"] == neighbor_id)
        assert hit["document_name"] == "b.md"
        assert hit["score"] > 0.9
        assert "content" in hit
        assert client.get(f"/api/documents/{uuid.uuid4()}/related").status_code == 404
        assert llm_mod.CHAT_CALLS == 0
        assert CHAT_CALLS == 0
    reset_app_state()
