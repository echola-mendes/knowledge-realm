from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage

from app.db import session_scope
from app.models import Conversation, Message
from app.agent import graph as graph_mod
from app.agent.graph import reset_graph
from app.rag.search import SearchHit
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
    reset_graph()
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "苹果"}, "id": "c1"}],
            ),
            AIMessage(content="根据资料回答"),
        ]
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

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    class FakeRunnable:
        def invoke(self, messages, config=None):
            return next(responses)

    class FakeModel:
        def bind_tools(self, tools):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return next(responses)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "苹果是什么", "task": "agent"})
        assert res.status_code == 200
        events = _sse_events(res.text)
    nodes = [e.get("node") for e in events if e["type"] == "step"]
    assert nodes == ["agent", "tools", "agent"]
    first = events[0]
    assert first["action"] == "tools"
    assert "search_knowledge" in first.get("tool_calls", [])
    tool = events[1]
    assert tool["node"] == "tools"
    assert tool["hits"] >= 1
    final = events[-1]
    assert final["type"] == "final"
    assert final["answer"] == "根据资料回答"
    assert final["loop_count"] == 1
    assert final["citations"][0]["document_name"] == "apple.md"
    for event in events:
        assert "elapsed_ms" in event or event["type"] == "final"


def test_agent_trace_does_not_persist_conversation(monkeypatch):
    import sqlalchemy

    reset_graph()

    def fake_agent(state, config=None):
        answer = "直答"
        messages = list(state.get("messages") or [])
        messages.append({"role": "assistant", "content": answer})
        return {"answer": answer, "messages": messages, "agent_messages": [AIMessage(content=answer)]}

    monkeypatch.setattr(graph_mod, "node_agent", fake_agent)

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
