import inspect
import json
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, reset_app_state
from app.p1 import graph as graph_mod
from app.search import SearchHit
import app.chat as chat_mod
import app.p1.chains as chains_mod
import app.routers.p1 as p1_router


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_agent_post_uses_graph_not_chat(monkeypatch):
    src = inspect.getsource(p1_router._agent_out) + inspect.getsource(p1_router.agent_stream)
    assert "build_graph" in inspect.getsource(p1_router._agent_out)
    assert "run_chat" not in src
    assert "/api/chat" not in src
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "langgraph" not in inspect.getsource(chains_mod)

    monkeypatch.setattr("app.routers.p1.llm_keys_ready", lambda: True)
    decisions = iter(
        [
            {"next_action": "search", "search_query": "苹果"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))
    searches: list[str] = []

    def fake_search(session, query, **kwargs):
        searches.append(query)
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="apple.md",
                chunk_id=uuid.uuid4(),
                content="讲苹果",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "Agent假答案")

    def boom(*args, **kwargs):
        raise AssertionError("must not use chat.run_chat")

    monkeypatch.setattr("app.chat.run_chat", boom)

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Agent-{uuid.uuid4().hex[:8]}"}).json()
        denied_task = client.post(
            "/api/agent",
            json={"task": "other", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert denied_task.status_code == 400
        res = client.post(
            "/api/agent",
            json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["task"] == "agent"
        assert body["knowledge_base_id"] == kb["id"]
        assert body["answer"] == "Agent假答案"
        assert body["loop_count"] == 1
        assert body["citations"][0]["document_name"] == "apple.md"
        assert searches == ["苹果"]
        monkeypatch.setattr("app.routers.p1.llm_keys_ready", lambda: False)
        denied_key = client.post(
            "/api/agent",
            json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert denied_key.status_code == 503
    reset_app_state()


def test_chat_contract_unchanged(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    dim = get_settings().embedding_dim
    monkeypatch.setattr("app.search.embed_texts", lambda texts: [[0.0] * dim for _ in texts])
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Chat-{uuid.uuid4().hex[:8]}"}).json()
        chat = client.post("/api/chat", json={"query": "你好", "knowledge_base_id": kb["id"]})
        assert chat.status_code == 200
        body = chat.json()
        assert set(body) == {"conversation_id", "answer", "citations"}
        assert body["answer"] == "假LLM答案"
        assert body["citations"] == []
    reset_app_state()


def test_agent_stream_matches_nonstream_fields(monkeypatch):
    monkeypatch.setattr("app.routers.p1.llm_keys_ready", lambda: True)

    def fake_reason(state):
        if int(state.get("loop_count") or 0) == 0:
            return {"next_action": "search", "search_query": "苹果"}
        return {"next_action": "generate"}

    monkeypatch.setattr(graph_mod, "reason_decide", fake_reason)
    hit_doc = uuid.uuid4()
    hit_chunk = uuid.uuid4()

    def fake_search(session, query, **kwargs):
        return [
            SearchHit(
                document_id=hit_doc,
                document_name="apple.md",
                chunk_id=hit_chunk,
                content="讲苹果",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "Agent假答案")

    def boom(*args, **kwargs):
        raise AssertionError("must not use chat stream")

    monkeypatch.setattr("app.chat.run_chat", boom)
    monkeypatch.setattr("app.routers.chat.chat_stream", boom)

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Stream-{uuid.uuid4().hex[:8]}"}).json()
        payload = {"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]}
        denied = client.post("/api/agent/stream", json={"task": "other", "query": "苹果", "knowledge_base_id": kb["id"]})
        assert denied.status_code == 400
        plain = client.post("/api/agent", json=payload)
        assert plain.status_code == 200
        streamed = client.post("/api/agent/stream", json=payload)
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(streamed.text)
        tokens = [item["text"] for item in events if item.get("type") == "token"]
        done = next(item for item in events if item.get("type") == "citations")
        assert "".join(tokens) == plain.json()["answer"]
        final = {key: value for key, value in done.items() if key != "type"}
        assert final == plain.json()
        assert "document_id" in final["citations"][0]
        assert "chunk_id" in final["citations"][0]
        monkeypatch.setattr("app.routers.p1.llm_keys_ready", lambda: False)
        no_key = client.post("/api/agent/stream", json=payload)
        assert no_key.status_code == 503
    reset_app_state()


def test_report_post_same_graph_as_agent(monkeypatch):
    monkeypatch.setattr("app.routers.p1.llm_keys_ready", lambda: True)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    questions: list[str] = []

    def fake_chat(question, context, history=None):
        questions.append(question)
        return "报告假答案"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Report-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "report", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["task"] == "report"
        assert body["answer"] == "报告假答案"
        assert "研究报告" in questions[0]
        streamed = client.post(
            "/api/agent/stream",
            json={"task": "report", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        done = next(item for item in _sse_events(streamed.text) if item.get("type") == "citations")
        assert done["task"] == "report"
        assert done["answer"] == "报告假答案"
    reset_app_state()
