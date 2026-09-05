import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.ingest.index import index_document
from app.main import create_app, reset_app_state
from app.models import Document
from app.ingest.parse import parse_text_document


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def _ready_note(client: TestClient, content: str, filename: str, knowledge_base_id: str | None = None) -> str:
    payload: dict = {"content": content, "filename": filename}
    if knowledge_base_id is not None:
        payload["knowledge_base_id"] = knowledge_base_id
    created = client.post("/api/documents/notes", json=payload)
    assert created.status_code == 200
    doc_id = created.json()["id"]
    parse_text_document(uuid.UUID(doc_id))
    index_document(uuid.UUID(doc_id))
    return doc_id


def test_compare_two_ready_docs_and_reject_bad_pairs(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr(
        "app.ingest.index.embed_texts",
        lambda texts: [[0.01] * get_settings().embedding_dim for _ in texts],
    )
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.routers.master.compare_documents", lambda *args, **kwargs: "假对比")
    with _client() as client:
        a = _ready_note(client, "资料甲讲苹果", "a.md")
        b = _ready_note(client, "资料乙讲橙子", "b.md")
        ok = client.post("/api/compare", json={"document_id_a": a, "document_id_b": b})
        assert ok.status_code == 200
        body = ok.json()
        assert body["comparison"] == "假对比"
        assert body["document_id_a"] == a
        assert body["document_id_b"] == b
        same = client.post("/api/compare", json={"document_id_a": a, "document_id_b": a})
        assert same.status_code == 400
        pending_id = uuid.uuid4()
        kb_id = uuid.UUID(client.get(f"/api/documents/{a}").json()["knowledge_base_id"])
        session = session_scope()
        try:
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
        not_ready = client.post("/api/compare", json={"document_id_a": a, "document_id_b": str(pending_id)})
        assert not_ready.status_code == 400
        other_kb = client.post("/api/knowledge-bases", json={"name": f"比-{uuid.uuid4().hex[:8]}"}).json()
        other = _ready_note(client, "另一库文档", "c.md", knowledge_base_id=other_kb["id"])
        cross = client.post("/api/compare", json={"document_id_a": a, "document_id_b": other})
        assert cross.status_code == 400
        monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: False)
        denied = client.post("/api/compare", json={"document_id_a": a, "document_id_b": b})
        assert denied.status_code == 503
    reset_app_state()
