import inspect
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import graph as graph_mod
from app.agent.graph import build_graph, initial_state, reset_graph
from app.rag.search import SearchHit
import app.rag.chat as chat_mod
import app.chains as chains_mod


def _config(thread: str, **extra):
    cfg = {"thread_id": thread, "session": object(), "user_id": uuid.uuid4(), **extra}
    return {"configurable": cfg}


def test_graph_no_json_action_routing():
    src = inspect.getsource(graph_mod)
    assert "ToolNode" in src
    assert "tools_condition" in src
    assert "bind_tools" in src
    assert '{{"action":"rag"' not in src
    # 工具路由不得依赖 next_action / 手写 JSON action（plan_agent_search 兼容字段除外）
    assert "state.get(\"next_action\")" not in src
    assert 'state.get("next_action")' not in src
    assert 'parsed.get("action")' not in src
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "langgraph" not in inspect.getsource(chains_mod)
    assert "playwright" not in src.lower()


def test_graph_tool_calls_then_final(monkeypatch):
    reset_graph()
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
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

    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "苹果"}, "id": "c1"}],
            ),
            AIMessage(content="根据资料回答"),
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
    compiled = build_graph()
    out = compiled.invoke(initial_state("苹果是什么"), config=_config(f"graph-loop-{uuid.uuid4()}"))
    assert calls == ["苹果"]
    assert out["answer"] == "根据资料回答"
    assert out["loop_count"] == 1
    assert out["citations"][0]["document_name"] == "apple.md"


def test_graph_max_loops_forces_final_without_tools(monkeypatch):
    reset_graph()
    n = {"search": 0}

    def fake_search(session, query, **kwargs):
        n["search"] += 1
        return []

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)

    def always_tool(*a, **k):
        return AIMessage(
            content="",
            tool_calls=[{"name": "search_knowledge", "args": {"query": "再搜"}, "id": f"c{n['search']}"}],
        )

    class FakeRunnable:
        def invoke(self, messages, config=None):
            # after tools rebound empty, final answer path uses model.invoke without bind
            # Detect: if last message is ToolMessage and loop would exceed, node_agent binds []
            tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
            if len(tool_msgs) >= graph_mod.MAX_LOOPS:
                return AIMessage(content="停")
            return always_tool()

    class FakeModel:
        def bind_tools(self, tools):
            self._tools = tools
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return FakeRunnable().invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    compiled = build_graph()
    out = compiled.invoke(initial_state("一直搜"), config=_config(f"graph-cap-{uuid.uuid4()}"))
    assert n["search"] == graph_mod.MAX_LOOPS
    assert out["loop_count"] == graph_mod.MAX_LOOPS
    assert out["answer"] == "停"


def test_agent_and_report_share_one_graph(monkeypatch):
    reset_graph()
    assert "StateGraph" in inspect.getsource(graph_mod)
    assert "checkpointer" in inspect.getsource(graph_mod.build_graph)
    assert "StateGraph" not in inspect.getsource(chat_mod)
    assert "StateGraph" not in inspect.getsource(chains_mod)

    seen: list[str] = []

    class FakeRunnable:
        def invoke(self, messages, config=None):
            sys = messages[0].content if messages else ""
            seen.append(sys)
            return AIMessage(content="成文")

    class FakeModel:
        def bind_tools(self, tools):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return FakeRunnable().invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    compiled = build_graph()
    tid = f"graph-share-{uuid.uuid4()}"
    agent_out = compiled.invoke(initial_state("苹果", task="agent"), config=_config(tid + "-a"))
    report_out = compiled.invoke(initial_state("苹果", task="report"), config=_config(tid + "-r"))
    assert agent_out["task"] == "agent"
    assert report_out["task"] == "report"
    assert "研究报告" not in seen[0]
    assert "研究报告" in seen[1]
    assert agent_out["answer"] == "成文"
    assert report_out["answer"] == "成文"


def test_graph_multiple_tool_calls_in_one_round(monkeypatch):
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
                ],
            ),
            AIMessage(content="双工具答"),
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
    out = build_graph().invoke(initial_state("问两个"), config=_config(f"multi-{uuid.uuid4()}"))
    assert queries == ["A", "B"]
    assert out["answer"] == "双工具答"


def test_graph_no_tool_calls_ends_with_content(monkeypatch):
    reset_graph()

    class FakeModel:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return AIMessage(content="直答")

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    out = build_graph().invoke(initial_state("你好"), config=_config(f"direct-{uuid.uuid4()}"))
    assert out["answer"] == "直答"
    assert out["loop_count"] == 0


def test_route_after_agent_uses_tools_condition():
    state = {
        "agent_messages": [
            HumanMessage(content="q"),
            AIMessage(content="", tool_calls=[{"name": "search_knowledge", "args": {"query": "x"}, "id": "1"}]),
        ]
    }
    assert graph_mod.route_after_agent(state) == "tools"
    state2 = {"agent_messages": [AIMessage(content="done")]}
    assert graph_mod.route_after_agent(state2) == "__end__"
