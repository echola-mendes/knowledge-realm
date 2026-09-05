import inspect
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.models import Document, EntityLink
from app.ingest.parse import parse_text_document
from app import chains as chains_mod
from app.db import session_scope


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_extract_graph_replaces_links_not_stacks(monkeypatch):
    assert "langgraph" not in inspect.getsource(chains_mod)
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr(
        "app.ingest.index.embed_texts",
        lambda texts: [[0.01] * get_settings().embedding_dim for _ in texts],
    )
    monkeypatch.setattr("app.routers.documents.llm_keys_ready", lambda: True)
    first = (
        [{"name": "LangChain", "type": "tool"}, {"name": "RAG", "type": "concept"}],
        [
            {"from_name": "LangChain", "to_name": "RAG", "rel": "用于"},
            {"from_name": "LangChain", "to_name": "幽灵", "rel": "无关"},
        ],
    )
    second = (
        [{"name": "LangChain", "type": "tool"}, {"name": "RAG", "type": "concept"}],
        [{"from_name": "LangChain", "to_name": "RAG", "rel": "用于"}],
    )
    calls = iter([first, second])
    monkeypatch.setattr("app.routers.documents.extract_graph", lambda text: next(calls))
    with _client() as client:
        created = client.post(
            "/api/documents/notes",
            json={"content": "LangChain 用于 RAG", "filename": "graph.md"},
        )
        assert created.status_code == 200
        doc_id = created.json()["id"]
        parse_text_document(uuid.UUID(doc_id))
        index_document(uuid.UUID(doc_id))
        pending_id = uuid.uuid4()
        session = session_scope()
        try:
            session.add(
                Document(
                    id=pending_id,
                    knowledge_base_id=uuid.UUID(created.json()["knowledge_base_id"]),
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
        assert client.post(f"/api/documents/{pending_id}/graph").status_code == 400
        once = client.post(f"/api/documents/{doc_id}/graph")
        assert once.status_code == 200
        body = once.json()
        assert len(body["entities"]) == 2
        assert len(body["links"]) == 1
        assert body["links"][0]["rel"] == "用于"
        twice = client.post(f"/api/documents/{doc_id}/graph")
        assert twice.status_code == 200
        assert len(twice.json()["links"]) == 1
        session = session_scope()
        try:
            n = session.scalar(
                select(func.count()).select_from(EntityLink).where(EntityLink.document_id == uuid.UUID(doc_id))
            )
            assert n == 1
        finally:
            session.close()
        monkeypatch.setattr("app.routers.documents.llm_keys_ready", lambda: False)
        assert client.post(f"/api/documents/{doc_id}/graph").status_code == 503
    reset_app_state()
