import inspect
import uuid

from app.p1 import graph as graph_mod
from app.p1.graph import build_graph, initial_state
from app.search import SearchHit
import app.chat as chat_mod
import app.p1.chains as chains_mod


def test_graph_searches_then_generates_and_caps_loops(monkeypatch):
    src = inspect.getsource(graph_mod)
    assert "search_knowledge" in src
    assert '{{"action":"search"' in inspect.getsource(graph_mod.reason_decide)
    assert inspect.getsource(graph_mod.node_reason).count("search_knowledge") == 0
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "langgraph" not in inspect.getsource(chains_mod)

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

    def fake_chat(question, context, history=None):
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
