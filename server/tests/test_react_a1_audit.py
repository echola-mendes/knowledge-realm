"""Step 3: react A1 multi-kb retrieval + tool_call/tool_result audit spans."""
from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage

from app.agent import graph as graph_mod
from app.agent import master as master_mod
from app.agent.graph import reset_graph
from app.audit.recorder import NODE_TYPES
from app.config import get_settings
from app.main import reset_app_state
from app.rag.search import SearchHit


def _client():
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client

    return api_client()


def test_node_types_include_tool_spans():
    assert "tool_call" in NODE_TYPES
    assert "tool_result" in NODE_TYPES
    assert len("tool_call") <= 20
    assert len("tool_result") <= 20


def test_react_without_kb_id_passes_none_to_search(monkeypatch):
    reset_graph()
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    seen: dict = {}

    def fake_search(session, query, user_id=None, knowledge_base_id=None, **kwargs):
        seen["knowledge_base_id"] = knowledge_base_id
        return [
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
        ]

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "苹果"}, "id": "c1"}],
            ),
            AIMessage(content="答"),
        ]
    )

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
        # 不传 knowledge_base_id → A1 检索应为 None（多库）
        res = client.post("/api/agent", json={"task": "react", "query": "查一下"})
        assert res.status_code == 200, res.text
        assert res.json()["answer"] == "答"
    assert "knowledge_base_id" in seen
    assert seen["knowledge_base_id"] is None
    reset_app_state()


def test_react_audit_spans_are_tool_call_and_tool_result(monkeypatch):
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
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "q"}, "id": "c1"}],
            ),
            AIMessage(content="终答"),
        ]
    )

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
        kb = client.post("/api/knowledge-bases", json={"name": f"R-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "react", "query": "查", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        convo_id = res.json()["conversation_id"]
        detail = client.get(f"/api/decisions?conversation_id={convo_id}&limit=5")
        assert detail.status_code == 200, detail.text
        runs = detail.json()
        items = runs if isinstance(runs, list) else runs.get("items") or runs.get("runs") or []
        react_runs = [r for r in items if r.get("mode") == "react"]
        assert react_runs, items
        run_id = react_runs[0]["id"]
        full = client.get(f"/api/decisions/{run_id}")
        assert full.status_code == 200, full.text
        body = full.json()
        spans = body.get("spans") or []
        types = [s.get("node_type") for s in spans]
        assert "tool_call" in types
        assert "tool_result" in types
    reset_app_state()


def test_master_knowledge_path_has_no_decision_recorder(monkeypatch):
    reset_graph()
    seen_configs: list[dict] = []

    class FakeGraph:
        def invoke(self, state, config=None):
            cfg = (config or {}).get("configurable") or {}
            seen_configs.append(dict(cfg))
            return {**state, "answer": "k", "citations": [], "loop_count": 0}

    monkeypatch.setattr(master_mod, "build_graph", lambda: FakeGraph())
    monkeypatch.setattr(master_mod, "classify_intent", lambda *a, **k: "knowledge")

    from app.agent.master import build_master_graph, master_initial_state

    out = build_master_graph().invoke(
        master_initial_state("苹果是什么", conversation_id=uuid.uuid4()),
        config={
            "configurable": {
                "thread_id": f"master-test-{uuid.uuid4()}",
                "session": object(),
                "user_id": uuid.uuid4(),
            }
        },
    )
    assert out["answer"] == "k"
    assert seen_configs
    assert "decision_recorder" not in seen_configs[0]
