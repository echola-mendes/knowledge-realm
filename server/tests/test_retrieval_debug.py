import uuid

from app.config import get_settings
from app.index import index_document
from app.main import reset_app_state
from app.parse import parse_text_document


def _client():
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
        elif "独角兽" in text or "XYZ" in text:
            vec[1] = 1.0
        else:
            vec[2] = 1.0
        vectors.append(vec)
    return vectors


def test_retrieval_debug_stages_and_eval(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.index.embed_texts", _directional_embed)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"dbg-{uuid.uuid4().hex[:8]}"}).json()
        note = client.post(
            "/api/documents/notes",
            json={"content": "独角兽代号XYZ", "filename": "rare.md", "knowledge_base_id": kb["id"]},
        )
        parse_text_document(uuid.UUID(note.json()["id"]))
        index_document(uuid.UUID(note.json()["id"]))
        doc_id = note.json()["id"]
        chat = client.post("/api/chat", json={"query": "独角兽代号XYZ", "knowledge_base_id": kb["id"]})
        assert chat.status_code == 200
        assert set(chat.json()) == {"conversation_id", "answer", "citations"}
        dbg = client.post(
            "/api/retrieval-debug",
            json={"query": "独角兽代号XYZ", "knowledge_base_id": kb["id"], "eval_k": 5},
        )
        assert dbg.status_code == 200, dbg.text
        body = dbg.json()
        assert "vector" in body and "bm25" in body and "rrf" in body and "rerank" in body
        assert "final" in body
        assert body["vector"]["actual_count"] >= 1
        assert body["bm25"]["actual_count"] >= 1
        put = client.put(
            "/api/retrieval-debug/labels",
            json={
                "query": "独角兽代号XYZ",
                "knowledge_base_id": kb["id"],
                "document_id": doc_id,
                "relevance": 3,
            },
        )
        assert put.status_code == 200
        dbg2 = client.post(
            "/api/retrieval-debug",
            json={"query": "独角兽代号XYZ", "knowledge_base_id": kb["id"], "eval_k": 5},
        )
        ev = dbg2.json()["evaluation"]
        assert ev["relevant_doc_count"] == 1
        assert ev["recall"] == 1.0
        assert ev["precision"] == 0.2
