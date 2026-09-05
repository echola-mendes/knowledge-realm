import inspect
import uuid

from app.agent import graph as graph_mod
from app.agent.graph import build_graph, initial_state
from app.rag.search import SearchHit
import app.rag.chat as chat_mod
import app.chains as chains_mod


def test_graph_searches_then_generates_and_caps_loops(monkeypatch):
    src = inspect.getsource(graph_mod)
    assert "search_knowledge" in src
    assert "web_search" in src
    assert '{{"action":"rag"' in inspect.getsource(graph_mod.reason_decide)
    assert '{{"action":"web"' in inspect.getsource(graph_mod.reason_decide)
    assert '{{"action":"direct"' in inspect.getsource(graph_mod.reason_decide)
    assert inspect.getsource(graph_mod.node_reason).count("search_knowledge") == 0
    assert inspect.getsource(graph_mod.node_reason).count("web_search") == 0
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "langgraph" not in inspect.getsource(chains_mod)
    assert "playwright" not in inspect.getsource(graph_mod).lower()

    decisions = iter(
        [
            {"next_action": "search", "search_query": "苹果"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))
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

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "根据资料回答")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("苹果是什么"),
        config={"configurable": {"thread_id": f"graph-loop-{uuid.uuid4()}", "session": object()}},
    )
    assert calls == ["苹果"]
    assert out["answer"] == "根据资料回答"
    assert out["loop_count"] == 1
    assert out["citations"][0]["document_name"] == "apple.md"


def test_graph_max_loops_forces_generate(monkeypatch):
    monkeypatch.setattr(
        graph_mod,
        "reason_decide",
        lambda state: {"next_action": "search", "search_query": "再搜"},
    )
    n = {"search": 0}

    def fake_search(session, query, **kwargs):
        n["search"] += 1
        return []

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "停")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("一直搜"),
        config={"configurable": {"thread_id": f"graph-cap-{uuid.uuid4()}", "session": object()}},
    )
    assert n["search"] == 3
    assert out["loop_count"] == 3
    assert out["answer"] == "停"
    assert out["next_action"] == "generate"


def test_agent_and_report_share_one_graph(monkeypatch):
    assert "StateGraph" in inspect.getsource(graph_mod)
    assert "checkpointer" in inspect.getsource(graph_mod.build_graph)
    assert "StateGraph" not in inspect.getsource(chat_mod)
    assert "StateGraph" not in inspect.getsource(chains_mod)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    questions: list[str] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        questions.append(question)
        return "成文"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    compiled = build_graph()
    tid = f"graph-share-{uuid.uuid4()}"
    agent_out = compiled.invoke(
        initial_state("苹果", task="agent"),
        config={"configurable": {"thread_id": tid + "-a", "session": object()}},
    )
    report_out = compiled.invoke(
        initial_state("苹果", task="report"),
        config={"configurable": {"thread_id": tid + "-r", "session": object()}},
    )
    assert agent_out["task"] == "agent"
    assert report_out["task"] == "report"
    assert questions[0] == "苹果"
    assert "研究报告" in questions[1]
    assert "大纲" in questions[1]
    assert questions[1].endswith("主题：苹果")
    assert agent_out["answer"] == "成文"
    assert report_out["answer"] == "成文"


def test_graph_web_reason_calls_web_search(monkeypatch):
    decisions = iter(
        [
            {"next_action": "web", "search_query": "今日新闻"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))
    web_calls: list[str] = []

    def fake_web(query, **kwargs):
        web_calls.append(query)
        return [{"title": "新闻", "url": "https://example.com", "snippet": "摘要"}]

    def boom_search(*args, **kwargs):
        raise AssertionError("RAG must not run when reason is WEB")

    monkeypatch.setattr(graph_mod, "web_search", fake_web)
    monkeypatch.setattr(graph_mod, "search_knowledge", boom_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "根据网页回答")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("今天有什么新闻", allow_web=True),
        config={"configurable": {"thread_id": f"graph-web-{uuid.uuid4()}", "session": object()}},
    )
    assert web_calls == ["今日新闻"]
    assert out["answer"] == "根据网页回答"
    assert out["loop_count"] == 1
    assert out["web_hits"][0]["url"] == "https://example.com"
    assert out["citations"] == []


def test_graph_allow_web_false_blocks_web_search(monkeypatch):
    decisions = iter(
        [
            {"next_action": "web", "search_query": "今日新闻"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))

    def boom_web(*args, **kwargs):
        raise AssertionError("allow_web=false must not call web_search")

    def boom_search(*args, **kwargs):
        raise AssertionError("WEB path must not call search_knowledge")

    monkeypatch.setattr(graph_mod, "web_search", boom_web)
    monkeypatch.setattr(graph_mod, "search_knowledge", boom_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "未联网直答")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("今天有什么新闻", allow_web=False),
        config={"configurable": {"thread_id": f"graph-no-allow-web-{uuid.uuid4()}", "session": object()}},
    )
    assert out["answer"] == "未联网直答"
    assert out["web_hits"] == []
    assert out["loop_count"] == 0


def test_graph_empty_rag_does_not_force_web(monkeypatch):
    decisions = iter(
        [
            {"next_action": "search", "search_query": "库内没有的东西"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))

    def fake_search(session, query, **kwargs):
        return []

    def boom_web(*args, **kwargs):
        raise AssertionError("empty citations must not force web_search")

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "web_search", boom_web)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "无资料直答")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("库里没有的问题"),
        config={"configurable": {"thread_id": f"graph-no-web-{uuid.uuid4()}", "session": object()}},
    )
    assert out["citations"] == []
    assert out["web_hits"] == []
    assert out["answer"] == "无资料直答"


def test_graph_direct_does_not_call_web_search(monkeypatch):
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})

    def boom_web(*args, **kwargs):
        raise AssertionError("DIRECT must not call web_search")

    def boom_search(*args, **kwargs):
        raise AssertionError("DIRECT must not call search_knowledge")

    monkeypatch.setattr(graph_mod, "web_search", boom_web)
    monkeypatch.setattr(graph_mod, "search_knowledge", boom_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "直答")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("你好"),
        config={"configurable": {"thread_id": f"graph-direct-{uuid.uuid4()}", "session": object()}},
    )
    assert out["answer"] == "直答"
    assert out["loop_count"] == 0


def test_graph_plan_subtasks_capped_at_three_one_graph(monkeypatch):
    from pathlib import Path

    p1_dir = Path(graph_mod.__file__).resolve().parent
    graph_files = sorted(p.name for p in p1_dir.glob("*.py") if "graph" in p.name.lower())
    assert graph_files == ["graph.py"]
    assert inspect.getsource(graph_mod).count("StateGraph(") == 1
    assert "MAX_SUBTASKS = 3" in inspect.getsource(graph_mod)
    assert graph_mod.MAX_SUBTASKS == graph_mod.MAX_LOOPS == 3
    assert graph_mod.clip_subtasks(["一", "二", "三", "四", "五"]) == ["一", "二", "三"]
    assert graph_mod.clip_subtasks(["", "  ", "甲"]) == ["甲"]

    n = {"i": 0}

    def fake_reason(state):
        n["i"] += 1
        if n["i"] == 1:
            return {
                "next_action": "search",
                "search_query": "一",
                "subtasks": ["一", "二", "三", "四"],
            }
        if n["i"] == 2:
            return {
                "next_action": "search",
                "search_query": "二",
                "subtasks": ["应忽略1", "应忽略2", "应忽略3", "应忽略4"],
            }
        return {"next_action": "generate", "subtasks": ["再写也不行"]}

    queries: list[str] = []

    def fake_search(session, query, **kwargs):
        queries.append(query)
        return []

    monkeypatch.setattr(graph_mod, "reason_decide", fake_reason)
    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "汇总")
    compiled = build_graph()
    out = compiled.invoke(
        initial_state("复杂问题请分步"),
        config={"configurable": {"thread_id": f"graph-plan-{uuid.uuid4()}", "session": object()}},
    )
    assert out["subtasks"] == ["一", "二", "三"]
    assert len(out["subtasks"]) <= 3
    assert queries == ["一", "二"]
    assert out["answer"] == "汇总"
    assert out["subtask_index"] == 2
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "StateGraph" not in inspect.getsource(chains_mod)
