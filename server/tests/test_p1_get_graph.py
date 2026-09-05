import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.ingest.parse import parse_text_document


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def _ready_note(client: TestClient, filename: str, content: str) -> tuple[str, str]:
    created = client.post("/api/documents/notes", json={"content": content, "filename": filename})
    assert created.status_code == 200
    doc_id = created.json()["id"]
    kb_id = created.json()["knowledge_base_id"]
    parse_text_document(uuid.UUID(doc_id))
    index_document(uuid.UUID(doc_id))
    return doc_id, kb_id


def test_get_graph_lists_kb_and_filters_by_document(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr(
        "app.ingest.index.embed_texts",
        lambda texts: [[0.01] * get_settings().embedding_dim for _ in texts],
    )
    monkeypatch.setattr("app.routers.documents.llm_keys_ready", lambda: True)
    payloads = iter(
        [
            (
                [{"name": "LangChain", "type": "tool"}, {"name": "RAG", "type": "concept"}],
                [{"from_name": "LangChain", "to_name": "RAG", "rel": "用于"}],
            ),
            (
                [{"name": "pgvector", "type": "tool"}, {"name": "PostgreSQL", "type": "tool"}],
                [{"from_name": "pgvector", "to_name": "PostgreSQL", "rel": "扩展"}],
            ),
        ]
    )
    monkeypatch.setattr("app.routers.documents.extract_graph", lambda text: next(payloads))
    with _client() as client:
        doc_a, kb_id = _ready_note(client, "a.md", "LangChain 用于 RAG")
        doc_b, _ = _ready_note(client, "b.md", "pgvector 是 PostgreSQL 扩展")
        assert client.post(f"/api/documents/{doc_a}/graph").status_code == 200
        assert client.post(f"/api/documents/{doc_b}/graph").status_code == 200
        listed = client.get("/api/graph", params={"knowledge_base_id": kb_id})
        assert listed.status_code == 200
        body = listed.json()
        names = {item["name"] for item in body["entities"]}
        assert names == {"LangChain", "RAG", "pgvector", "PostgreSQL"}
        rels = {item["rel"] for item in body["links"]}
        assert rels == {"用于", "扩展"}
        filtered = client.get("/api/graph", params={"knowledge_base_id": kb_id, "document_id": doc_a})
        assert filtered.status_code == 200
        only_a = filtered.json()
        assert {item["name"] for item in only_a["entities"]} == {"LangChain", "RAG"}
        assert len(only_a["links"]) == 1
        assert only_a["links"][0]["rel"] == "用于"
        assert only_a["links"][0]["document_id"] == doc_a
        missing = client.get("/api/graph", params={"knowledge_base_id": kb_id, "document_id": str(uuid.uuid4())})
        assert missing.status_code == 404
    reset_app_state()
