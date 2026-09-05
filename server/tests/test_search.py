import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.ingest.index import index_document
from app.llm import CHAT_CALLS
from app.main import create_app, reset_app_state
from app.ingest.parse import parse_pdf_document, parse_text_document
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


def _make_text_pdf(text: str) -> bytes:
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text, fontname="china-s")
    data = pdf.tobytes()
    pdf.close()
    return data


def test_search_isolates_kb_tag_kind_and_skips_chat(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.ingest.index.embed_texts", _directional_embed)
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
        pdf = client.post(
            "/api/documents/upload",
            files={"file": ("apple.pdf", _make_text_pdf("也有苹果"), "application/pdf")},
            data={"knowledge_base_id": kb_a["id"]},
        )
        apple_id = uuid.UUID(apple.json()["id"])
        orange_id = uuid.UUID(orange.json()["id"])
        pdf_id = uuid.UUID(pdf.json()["id"])
        parse_text_document(apple_id)
        parse_text_document(orange_id)
        parse_pdf_document(pdf_id)
        index_document(apple_id)
        index_document(orange_id)
        index_document(pdf_id)
        tag = client.post("/api/tags", json={"name": f"水果-{uuid.uuid4().hex[:8]}"}).json()
        client.put(f"/api/documents/{apple.json()['id']}/tags", json={"tag_ids": [tag["id"]]})

        in_a = client.post("/api/search", json={"query": "苹果", "knowledge_base_id": kb_a["id"]})
        assert in_a.status_code == 200
        names = [hit["document_name"] for hit in in_a.json()]
        assert "apple.md" in names
        assert "orange.md" not in names

        apple_hit = next(h for h in in_a.json() if h["document_name"] == "apple.md")
        assert apple_hit["knowledge_base_name"] == kb_a["name"]
        assert apple_hit["tags"] == [tag["name"]]
        assert apple_hit["created_at"]

        tagged = client.post(
            "/api/search",
            json={"query": "苹果", "knowledge_base_id": kb_a["id"], "tag_id": tag["id"]},
        )
        tagged_ids = {hit["document_id"] for hit in tagged.json()}
        assert apple.json()["id"] in tagged_ids
        assert pdf.json()["id"] not in tagged_ids

        notes = client.post(
            "/api/search",
            json={"query": "苹果", "knowledge_base_id": kb_a["id"], "kind": "note"},
        )
        kinds = {hit["kind"] for hit in notes.json()}
        names = {hit["document_name"] for hit in notes.json()}
        assert kinds == {"note"}
        assert "apple.pdf" not in names

        default_hits = client.post("/api/search", json={"query": "苹果"})
        default_names = {hit["document_name"] for hit in default_hits.json()}
        assert "apple.md" in default_names
        assert "orange.md" not in default_names

        off = client.put(f"/api/knowledge-bases/{kb_a['id']}", json={"is_enabled": False})
        assert off.status_code == 200
        assert off.json()["is_enabled"] is False
        after_off = client.post("/api/search", json={"query": "苹果"})
        after_names = {hit["document_name"] for hit in after_off.json()}
        assert "apple.md" not in after_names

        assert llm_mod.CHAT_CALLS == 0
        assert CHAT_CALLS == 0
    reset_app_state()


def test_search_time_window_excludes_old_docs(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.ingest.index.embed_texts", _directional_embed)
    from datetime import datetime, timedelta, timezone

    from app.db import session_scope
    from app.models import Document

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"时窗-{uuid.uuid4().hex[:8]}"}).json()
        old = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果很久以前", "filename": "old-apple.md", "knowledge_base_id": kb["id"]},
        )
        new = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果就在今天", "filename": "new-apple.md", "knowledge_base_id": kb["id"]},
        )
        old_id = uuid.UUID(old.json()["id"])
        new_id = uuid.UUID(new.json()["id"])
        parse_text_document(old_id)
        parse_text_document(new_id)
        index_document(old_id)
        index_document(new_id)
        session = session_scope()
        try:
            row = session.get(Document, old_id)
            assert row is not None
            row.created_at = datetime.now(timezone.utc) - timedelta(days=20)
            session.commit()
        finally:
            session.close()
        after = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        windowed = client.post(
            "/api/search",
            json={"query": "苹果", "knowledge_base_id": kb["id"], "created_after": after},
        )
        assert windowed.status_code == 200, windowed.text
        names = {hit["document_name"] for hit in windowed.json()}
        assert "new-apple.md" in names
        assert "old-apple.md" not in names
        notes = client.post(
            "/api/search",
            json={"query": "苹果", "knowledge_base_id": kb["id"], "kind": "note", "created_after": after},
        )
        assert {hit["kind"] for hit in notes.json()} <= {"note"}
        assert "old-apple.md" not in {hit["document_name"] for hit in notes.json()}
    reset_app_state()
