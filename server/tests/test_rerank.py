import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.ingest.parse import parse_text_document
from app.rag.search import SearchHit, _rerank


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_rerank_mock_changes_order(monkeypatch):
    a = SearchHit(
        document_id=uuid.uuid4(),
        document_name="a.md",
        chunk_id=uuid.uuid4(),
        content="aaa",
        score=0.9,
        page=None,
        heading=None,
        kind="note",
    )
    b = SearchHit(
        document_id=uuid.uuid4(),
        document_name="b.md",
        chunk_id=uuid.uuid4(),
        content="bbb",
        score=0.8,
        page=None,
        heading=None,
        kind="note",
    )
    monkeypatch.setattr("app.rag.search.score_documents", lambda query, documents: None)
    out = _rerank("q", [a, b])
    assert [h.document_name for h in out] == ["a.md", "b.md"]
    monkeypatch.setattr("app.rag.search.score_documents", lambda query, documents: [0.1, 0.9])
    out = _rerank("q", [a, b])
    assert [h.document_name for h in out] == ["b.md", "a.md"]
    assert out[0].score == 0.9


def test_search_without_rerank_or_llm_key_not_500(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("RERANK_API_KEY", "")
    reset_app_state()
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.rag.search.score_documents", lambda query, documents: None)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"库-{uuid.uuid4().hex[:8]}"}).json()
        note = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果", "filename": "apple.md", "knowledge_base_id": kb["id"]},
        )
        doc_id = uuid.UUID(note.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)
        res = client.post("/api/search", json={"query": "苹果", "knowledge_base_id": kb["id"]})
        assert res.status_code == 200
    reset_app_state()
