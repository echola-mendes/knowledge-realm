import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.index import index_document
from app.main import create_app, reset_app_state
from app.models import Document
from app.parse import parse_text_document
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


def test_chat_hit_miss_pending_and_kb_isolation(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.index.embed_texts", _directional_embed)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    llm_mod.CHAT_CALLS = 0
    with _client() as client:
        kb_a = client.post("/api/knowledge-bases", json={"name": f"库A-{uuid.uuid4().hex[:8]}"}).json()
        kb_b = client.post("/api/knowledge-bases", json={"name": f"库B-{uuid.uuid4().hex[:8]}"}).json()
        apple = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果", "filename": "apple.md", "knowledge_base_id": kb_a["id"]},
        )
        orange = client.post(
            "/api/documents/notes",
            json={"content": "文档讲橙子", "filename": "orange.md", "knowledge_base_id": kb_b["id"]},
        )
        pending_id = uuid.uuid4()
        session = session_scope()
        try:
            session.add(
                Document(
                    id=pending_id,
                    knowledge_base_id=uuid.UUID(kb_a["id"]),
                    filename="pending.md",
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
        apple_id = uuid.UUID(apple.json()["id"])
        orange_id = uuid.UUID(orange.json()["id"])
        parse_text_document(apple_id)
        parse_text_document(orange_id)
        index_document(apple_id)
        index_document(orange_id)

        hit = client.post("/api/chat", json={"query": "苹果", "knowledge_base_id": kb_a["id"]})
        assert hit.status_code == 200
        assert hit.json()["answer"] == "假LLM答案"
        names = [c["document_name"] for c in hit.json()["citations"]]
        assert "apple.md" in names
        assert hit.json()["conversation_id"]

        miss = client.post("/api/chat", json={"query": "完全无关查询", "knowledge_base_id": kb_a["id"]})
        assert miss.status_code == 200
        assert miss.json()["answer"] == "假LLM答案"
        assert miss.json()["citations"] == []

        pending_chat = client.post(
            "/api/chat",
            json={"query": "苹果", "knowledge_base_id": kb_a["id"], "document_id": str(pending_id)},
        )
        assert pending_chat.status_code == 400

        only_b = client.post("/api/chat", json={"query": "橙子", "knowledge_base_id": kb_b["id"]})
        assert only_b.status_code == 200
        b_names = [c["document_name"] for c in only_b.json()["citations"]]
        assert "orange.md" in b_names
        assert "apple.md" not in b_names
        assert "apple.md" not in only_b.json()["answer"]
    reset_app_state()


def test_chat_without_embed_key_returns_503(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: False)
    with _client() as client:
        res = client.post("/api/chat", json={"query": "你好"})
        assert res.status_code == 503
        assert res.json()["detail"] == "未配置 Embedding API Key"
        stream = client.post("/api/chat/stream", json={"query": "你好"})
        assert stream.status_code == 503
        assert stream.json()["detail"] == "未配置 Embedding API Key"
    reset_app_state()
