from __future__ import annotations

import json
import uuid

from app.db import session_scope
from app.models import Conversation, Message
from app.p1 import graph as graph_mod
from app.p1.graph import build_graph
from app.search import SearchHit
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for part in text.split("\n\n"):
        line = next((l for l in part.split("\n") if l.startswith("data: ")), None)
        if line:
            events.append(json.loads(line[len("data: ") :]))
    return events


def test_agent_trace_emits_steps_and_final(monkeypatch):
    decisions = iter(
        [
            {"next_action": "search", "search_query": "苹果", "subtasks": ["查苹果"]},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))

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

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "根据资料回答")

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "苹果是什么", "task": "agent"})
        assert res.status_code == 200
        events = _sse_events(res.text)
    nodes = [e.get("node") for e in events if e["type"] == "step"]
    assert nodes == ["reason", "run_tool", "reason", "generate"]
    reason = events[0]
    assert reason["action"] == "search"
    assert reason["query"] == "苹果"
    assert reason["subtasks"] == ["查苹果"]
    tool = events[1]
    assert tool["tool"] == "search_knowledge"
    assert tool["hits"] == 1
    final = events[-1]
    assert final["type"] == "final"
    assert final["answer"] == "根据资料回答"
    assert final["loop_count"] == 1
    assert final["citations"][0]["document_name"] == "apple.md"
    for event in events:
        assert "elapsed_ms" in event or event["type"] == "final"


def test_agent_trace_does_not_persist_conversation(monkeypatch):
    import sqlalchemy

    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "直答")

    with _client() as client:
        with session_scope() as session:
            convos_before = len(list(session.scalars(sqlalchemy.select(Conversation))))
            messages_before = len(list(session.scalars(sqlalchemy.select(Message))))
        res = client.post("/api/agent/trace", json={"query": "你好", "task": "agent"})
        assert res.status_code == 200
        events = _sse_events(res.text)
        with session_scope() as session:
            conversations = list(session.scalars(sqlalchemy.select(Conversation)))
            messages = list(session.scalars(sqlalchemy.select(Message)))
    assert events[-1]["answer"] == "直答"
    assert len(conversations) == convos_before
    assert len(messages) == messages_before


def test_agent_trace_requires_llm_keys(monkeypatch):
    import app.routers.p1 as p1_mod

    monkeypatch.setattr(p1_mod, "llm_keys_ready", lambda: False)
    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "你好", "task": "agent"})
    assert res.status_code == 503
