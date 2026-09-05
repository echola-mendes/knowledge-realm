import uuid

from fastapi.testclient import TestClient

import pytest

from app.config import get_settings, load_settings
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.ingest.parse import parse_text_document
import app.llm as llm_mod


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_relevance_default_is_half():
    s = load_settings(
        environ={"DATABASE_URL": "postgresql+psycopg://postgres@127.0.0.1:5432/echola_kb"},
        load_file=False,
    )
    assert s.relevance_min_score == 0.5


@pytest.fixture(autouse=True)
def skip_rerank():
    yield


def test_low_rerank_drops_hits_high_keeps(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "闲聊")
    llm_mod.CHAT_CALLS = 0
    scores = [0.1]

    def fake_embed(texts: list[str]) -> list[list[float]]:
        dim = get_settings().embedding_dim
        return [[0.01] * dim for _ in texts]

    monkeypatch.setattr("app.rag.search.embed_texts", fake_embed)
    monkeypatch.setattr("app.ingest.index.embed_texts", fake_embed)
    monkeypatch.setattr(
        "app.rag.search.score_documents",
        lambda query, documents: [scores[0]] * len(documents),
    )
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"库-{uuid.uuid4().hex[:8]}"}).json()
        note = client.post(
            "/api/documents/notes",
            json={"content": "你好，我是 echola", "filename": "笔记.md", "knowledge_base_id": kb["id"]},
        )
        doc_id = uuid.UUID(note.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)

        weather = client.post(
            "/api/chat",
            json={"query": "今天天气不错", "knowledge_base_id": kb["id"]},
        )
        assert weather.status_code == 200
        assert weather.json()["citations"] == []
        assert weather.json()["answer"] == "闲聊"

        scores[0] = 0.9
        who = client.post(
            "/api/chat",
            json={"query": "echola是谁", "knowledge_base_id": kb["id"]},
        )
        assert who.status_code == 200
        names = [c["document_name"] for c in who.json()["citations"]]
        assert "笔记.md" in names
    reset_app_state()
