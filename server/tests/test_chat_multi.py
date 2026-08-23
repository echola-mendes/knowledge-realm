import json
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.index import index_document
from app.main import create_app, reset_app_state
from app.parse import parse_text_document


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
        else:
            vec[2] = 1.0
        vectors.append(vec)
    return vectors


def test_second_turn_sends_history_stream_matches_and_delete(monkeypatch):
    captured: dict = {}

    def fake_chat(question, context, history=None):
        captured["history"] = list(history or [])
        captured["question"] = question
        return "假LLM答案"

    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.index.embed_texts", _directional_embed)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"聊-{uuid.uuid4().hex[:8]}"}).json()
        note = client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果", "filename": "apple.md", "knowledge_base_id": kb["id"]},
        )
        doc_id = uuid.UUID(note.json()["id"])
        parse_text_document(doc_id)
        index_document(doc_id)
        first = client.post("/api/chat", json={"query": "苹果是什么", "knowledge_base_id": kb["id"]})
        assert first.status_code == 200
        convo_id = first.json()["conversation_id"]
        second = client.post(
            "/api/chat",
            json={"query": "再讲讲苹果", "knowledge_base_id": kb["id"], "conversation_id": convo_id},
        )
        assert second.status_code == 200
        hist = captured["history"]
        assert ("user", "苹果是什么") in hist
        assert ("assistant", "假LLM答案") in hist

        streamed = client.post(
            "/api/chat/stream",
            json={"query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        tokens = []
        citations_event = None
        for line in streamed.text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if payload.get("type") == "token":
                tokens.append(payload["text"])
            if payload.get("type") == "citations":
                citations_event = payload
        assert "".join(tokens) == first.json()["answer"]
        assert citations_event is not None
        assert citations_event["answer"] == first.json()["answer"]
        assert "citations" in citations_event
        assert "conversation_id" in citations_event

        listed = client.get("/api/conversations")
        assert any(item["id"] == convo_id for item in listed.json())
        msgs = client.get(f"/api/conversations/{convo_id}/messages")
        assert msgs.status_code == 200
        assert len(msgs.json()) >= 2
        gone = client.delete(f"/api/conversations/{convo_id}")
        assert gone.status_code == 200
        assert client.get(f"/api/conversations/{convo_id}/messages").status_code == 404
    reset_app_state()
