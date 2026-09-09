"""task=knowledge 直连 knowledge_flow，不经 Master 意图路由。"""
from __future__ import annotations

import json
import uuid

from app.agent import knowledge_flow as kf
from app.agent import master as master_mod
from app.config import get_settings
from app.main import reset_app_state
from app.rag.search import SearchHit


def _client():
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client

    return api_client()


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_knowledge_task_uses_graph_not_master(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)

    def boom_master(*args, **kwargs):
        raise AssertionError("task=knowledge must not call Master")

    monkeypatch.setattr(master_mod, "build_master_graph", boom_master)
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "simple"})
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )

    def fake_search(session, query, **kwargs):
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

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "知识Agent答案")
    kf.reset_knowledge_flow_graph()

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"KB-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "knowledge", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["task"] == "knowledge"
        assert body["intent"] == "knowledge"
        assert body["answer"] == "知识Agent答案"
        assert body["citations"][0]["document_name"] == "apple.md"

        streamed = client.post(
            "/api/agent/stream",
            json={"task": "knowledge", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        events = _sse_events(streamed.text)
        assert events[0] == {"type": "intent", "intent": "knowledge"}
        assert any(e.get("type") == "citations" and e.get("task") == "knowledge" for e in events)
    reset_app_state()


def test_agent_task_still_uses_master(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(
        master_mod,
        "classify_intent",
        lambda query, *, task="agent", history_tail=None: "chat",
    )
    called = {"master": 0}

    class FakeGraph:
        def invoke(self, state, config=None):
            called["master"] += 1
            return {**state, "answer": "闲聊", "citations": [], "intent": "chat"}

        def stream(self, state, config=None, stream_mode=None):
            called["master"] += 1
            yield {"intent": {"intent": "chat"}}
            yield {"chat": {"answer": "闲聊", "citations": []}}

    monkeypatch.setattr(master_mod, "build_master_graph", lambda: FakeGraph())
    monkeypatch.setattr("app.routers.master.build_master_graph", lambda: FakeGraph())

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"M-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "agent", "query": "你好", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        assert res.json()["task"] == "agent"
        assert called["master"] >= 1
    reset_app_state()
