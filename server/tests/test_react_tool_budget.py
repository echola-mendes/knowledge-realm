"""Step 1: MAX_TOOL_CALLS hard cap (parallel overflow + bind flag)."""
import inspect
import uuid

from langchain_core.messages import AIMessage, ToolMessage

from app.agent import graph as graph_mod
from app.agent.graph import build_graph, initial_state, reset_graph


def _config(thread: str, **extra):
    cfg = {"thread_id": thread, "session": object(), "user_id": uuid.uuid4(), **extra}
    return {"configurable": cfg}


def _ai_parallel(queries: list[str], *, content: str = "", msg_id: str = "ai") -> AIMessage:
    """AIMessage with LC tool_calls plus provider additional_kwargs (the restore trap)."""
    tool_calls = [
        {"name": "search_knowledge", "args": {"query": q}, "id": f"{msg_id}-{i}"}
        for i, q in enumerate(queries)
    ]
    raw = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": '{"query":"%s"}' % tc["args"]["query"]},
        }
        for tc in tool_calls
    ]
    return AIMessage(
        content=content,
        tool_calls=tool_calls,
        additional_kwargs={"tool_calls": raw},
        id=msg_id,
    )


def test_bind_tools_disables_parallel_tool_calls():
    src = inspect.getsource(graph_mod)
    assert "parallel_tool_calls=False" in src
    assert "_bind_model_tools" in src
    assert "_truncate_tool_calls" in src


def test_truncate_tool_calls_helper():
    msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_knowledge", "args": {"query": "a"}, "id": "1"},
            {"name": "search_knowledge", "args": {"query": "b"}, "id": "2"},
            {"name": "search_knowledge", "args": {"query": "c"}, "id": "3"},
        ],
        id="ai-1",
    )
    out = graph_mod._truncate_tool_calls(msg, 1)
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0]["id"] == "1"
    assert out.id == "ai-1"
    assert graph_mod._truncate_tool_calls(msg, 0).tool_calls == []
    assert graph_mod._truncate_tool_calls(msg, 5) is msg

    provider = _ai_parallel(["a", "b", "c", "d"], content="keep-text", msg_id="prov")
    cleared = graph_mod._truncate_tool_calls(provider, 0)
    assert cleared.tool_calls == []
    assert "tool_calls" not in (cleared.additional_kwargs or {})
    assert cleared.content == "keep-text"
    kept = graph_mod._truncate_tool_calls(provider, 2)
    assert [tc["id"] for tc in kept.tool_calls] == ["prov-0", "prov-1"]
    assert "tool_calls" not in (kept.additional_kwargs or {})


def test_parallel_tool_calls_respect_remaining_budget(monkeypatch):
    """One AIMessage with many tool_calls when remaining=1 → only 1 execution."""
    reset_graph()
    queries: list[str] = []

    def fake_search(session, query, **kwargs):
        queries.append(query)
        return []

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_knowledge", "args": {"query": "A"}, "id": "1"},
                    {"name": "search_knowledge", "args": {"query": "B"}, "id": "2"},
                    {"name": "search_knowledge", "args": {"query": "C"}, "id": "3"},
                ],
            ),
            AIMessage(content="截断后终答"),
        ]
    )

    class FakeRunnable:
        def invoke(self, messages, config=None):
            return next(responses)

        def stream(self, messages, config=None):
            yield next(responses)

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return next(responses)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())

    state = initial_state("超预算并行")
    # Leave only 1 slot before this round.
    state["tool_call_count"] = graph_mod.MAX_TOOL_CALLS - 1
    out = build_graph().invoke(state, config=_config(f"budget-{uuid.uuid4()}"))
    assert queries == ["A"]
    assert out["tool_call_count"] == graph_mod.MAX_TOOL_CALLS
    assert out["answer"] == "截断后终答"


def test_tool_call_count_never_exceeds_max(monkeypatch):
    reset_graph()
    n = {"search": 0}

    def fake_search(session, query, **kwargs):
        n["search"] += 1
        return []

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    class FakeRunnable:
        def invoke(self, messages, config=None):
            tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
            if len(tool_msgs) >= graph_mod.MAX_TOOL_CALLS:
                return AIMessage(content="到顶")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_knowledge",
                        "args": {"query": f"q{len(tool_msgs)}"},
                        "id": f"c{len(tool_msgs)}",
                    },
                    {
                        "name": "search_knowledge",
                        "args": {"query": f"extra{len(tool_msgs)}"},
                        "id": f"e{len(tool_msgs)}",
                    },
                ],
            )

        def stream(self, messages, config=None):
            yield self.invoke(messages, config)

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            self._tools = tools
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return FakeRunnable().invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    # Raise loop cap so only MAX_TOOL_CALLS binds the budget.
    state = initial_state("累计封顶")
    state["max_loops"] = 20
    out = build_graph().invoke(state, config=_config(f"cap-{uuid.uuid4()}"))
    assert n["search"] <= graph_mod.MAX_TOOL_CALLS
    assert out["tool_call_count"] <= graph_mod.MAX_TOOL_CALLS
    assert out["answer"] == "到顶"

def test_four_then_four_parallel_does_not_execute_eight(monkeypatch):
    """4 parallel then another 4 parallel must execute 6, not 8, and still answer."""
    reset_graph()
    queries: list[str] = []

    def fake_search(session, query, **kwargs):
        queries.append(query)
        return []

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    class FakeRunnable:
        def invoke(self, messages, config=None):
            n_tools = sum(1 for m in messages if isinstance(m, ToolMessage))
            if n_tools >= graph_mod.MAX_TOOL_CALLS:
                return AIMessage(content="四加四终答")
            prefix = "a" if n_tools == 0 else "b"
            return _ai_parallel([f"{prefix}{i}" for i in range(4)], msg_id=prefix)

        def stream(self, messages, config=None):
            yield self.invoke(messages, config)

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return FakeRunnable().invoke(messages, config)

        def stream(self, messages, config=None):
            yield FakeRunnable().invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    state = initial_state("四加四")
    state["max_loops"] = 20
    out = build_graph().invoke(state, config=_config(f"four-{uuid.uuid4()}"))
    assert queries == ["a0", "a1", "a2", "a3", "b0", "b1"]
    assert out["tool_call_count"] == graph_mod.MAX_TOOL_CALLS
    assert out["answer"] == "四加四终答"


def test_budget_exhausted_with_provider_tool_calls_still_answers(monkeypatch):
    """remaining=0 + additional_kwargs tool_calls must not execute or raise."""
    reset_graph()
    queries: list[str] = []

    def fake_search(session, query, **kwargs):
        queries.append(query)
        return []

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            raise AssertionError("budget exhausted should unbind tools")

        def invoke(self, messages, config=None):
            return _ai_parallel(["A", "B", "C", "D"], content="预算用尽终答", msg_id="over")

        def stream(self, messages, config=None):
            yield self.invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    state = initial_state("已用尽")
    state["tool_call_count"] = graph_mod.MAX_TOOL_CALLS
    out = build_graph().invoke(state, config=_config(f"exhausted-{uuid.uuid4()}"))
    assert queries == []
    assert out["tool_call_count"] == graph_mod.MAX_TOOL_CALLS
    assert out["answer"] == "预算用尽终答"

