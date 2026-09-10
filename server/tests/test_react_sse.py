"""task=react live SSE + LLM token stream via custom writer."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, AIMessageChunk

from app.agent import graph as graph_mod
from app.agent.graph import reset_graph
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


def _fake_model(monkeypatch, responses):
    it = iter(responses)

    class FakeRunnable:
        def invoke(self, messages, config=None):
            return next(it)

        def stream(self, messages, config=None):
            msg = next(it)
            tool_calls = list(getattr(msg, "tool_calls", None) or [])
            if tool_calls:
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tc.get("name"),
                            "args": json.dumps(tc.get("args") or {}, ensure_ascii=False),
                            "id": tc.get("id"),
                            "index": i,
                        }
                        for i, tc in enumerate(tool_calls)
                    ],
                )
                return
            content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
            for ch in content:
                yield AIMessageChunk(content=ch)

    class FakeModel:
        def bind_tools(self, tools):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return FakeRunnable().invoke(messages, config)

        def stream(self, messages, config=None):
            yield from FakeRunnable().stream(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())


def test_react_stream_emits_tool_events_and_compat_tokens(monkeypatch):
    reset_graph()
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(
        "app.agent.tools.knowledge.search_chunks",
        lambda *a, **k: [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="a.md",
                chunk_id=uuid.uuid4(),
                content="x",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ],
    )
    _fake_model(
        monkeypatch,
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "q"}, "id": "c1"}],
            ),
            AIMessage(content="完整回答"),
        ],
    )
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"S-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent/stream",
            json={"task": "react", "query": "查", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        events = _sse_events(res.text)
    types = [e.get("type") for e in events]
    assert "intent" in types
    assert "agent_start" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "answer_delta" in types or "token" in types
    assert "agent_end" in types
    assert types[-1] == "citations" or events[-1].get("type") == "citations"
    text_i = next(
        i for i, e in enumerate(events) if e.get("type") in ("token", "answer_delta") and e.get("text")
    )
    cite_i = next(i for i, e in enumerate(events) if e.get("type") == "citations")
    assert text_i < cite_i
    tokens = "".join(e.get("text") or "" for e in events if e.get("type") == "token")
    deltas = "".join(e.get("text") or "" for e in events if e.get("type") == "answer_delta")
    assert "完整回答" in tokens or "完整回答" in deltas
    cite = next(e for e in events if e.get("type") == "citations")
    assert cite.get("task") == "react"
    assert cite.get("answer") == "完整回答"
    reset_app_state()


def test_knowledge_stream_no_forced_tool_call_protocol(monkeypatch):
    reset_graph()
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)

    class FakeKF:
        def invoke(self, state, config=None):
            return {**state, "answer": "知识答", "citations": [], "loop_count": 0}

    monkeypatch.setattr("app.routers.master.build_knowledge_flow_graph", lambda: FakeKF())
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"K-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent/stream",
            json={"task": "knowledge", "query": "问", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        events = _sse_events(res.text)
    types = [e.get("type") for e in events]
    assert "tool_call" not in types
    assert "agent_start" not in types
    assert "token" in types
    assert any(e.get("type") == "citations" for e in events)
    reset_app_state()


def test_react_stream_uses_same_build_graph():
    import inspect
    import app.routers.master as master_router

    src = inspect.getsource(master_router._stream_react_graph)
    assert "build_graph().stream" in src
    assert "custom" in src
    assert "yield" in src
    assert "build_graph" in inspect.getsource(master_router._invoke_react_graph)
    stream_src = inspect.getsource(master_router.agent_stream)
    assert "react_events" in stream_src
    assert "next(gen)" in stream_src
