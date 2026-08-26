import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.index import index_document
from app.llm import CHAT_CALLS
from app.main import create_app, reset_app_state
from app.parse import parse_pdf_document, parse_text_document
import app.llm as llm_mod


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


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
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.index.embed_texts", _directional_embed)
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
        assert "orange.md" not in default_names
        assert "apple.md" not in default_names

        assert llm_mod.CHAT_CALLS == 0
        assert CHAT_CALLS == 0
    reset_app_state()
