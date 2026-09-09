"""Step 6: Simple/Complex Query Analysis + knowledge entry via knowledge_flow."""

from __future__ import annotations

import uuid

from app.agent import knowledge_flow as kf
from app.agent.decompose import make_sub_questions
from app.agent.graph import initial_state
from app.rag.search import SearchHit


def _hit(content: str = "body") -> SearchHit:
    return SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content=content,
        score=0.9,
        page=1,
        heading=None,
        kind="note",
    )


def test_simple_no_decompose_one_search(monkeypatch):
    """AC-01: Simple → no decompose; search_knowledge called once."""
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "simple"})

    def boom_decompose(query: str):
        raise AssertionError("Simple must not decompose")

    monkeypatch.setattr(kf, "decompose_query", boom_decompose)
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return [_hit(f"about {query}")]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "简单作答")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("什么是 pgvector"),
        config={"configurable": {"session": None}},
    )
    assert out["query_type"] == "simple"
    assert calls == ["什么是 pgvector"]
    assert out["loop_count"] == 0
    assert "简单作答" in out["answer"]
    assert out["citations"]


def test_complex_goes_decompose(monkeypatch):
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})
    questions = ["消息模型", "消费模式"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return [_hit(query)]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "对比作答")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("Kafka 和 RabbitMQ 区别？"),
        config={"configurable": {"session": None}},
    )
    assert out["query_type"] == "complex"
    assert calls == questions
    assert len(out["sub_questions"]) == 2


def test_decompose_failure_degrades_to_single_retrieve(monkeypatch):
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": [], "degraded": True},
    )
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return [_hit("ok")]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "降级作答")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("复杂但分解失败"),
        config={"configurable": {"session": None}},
    )
    assert calls == ["复杂但分解失败"]
    assert len(out["sub_questions"]) == 1
    assert out["query_type"] == "simple"
    assert "降级作答" in out["answer"]


def test_initial_state_knowledge_entry_runs(monkeypatch):
    """knowledge Agent entry via initial_state + knowledge_flow still works."""
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "simple"})
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    monkeypatch.setattr(kf, "search_knowledge", lambda *a, **k: [_hit("x")])
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "入口可用")
    kf.reset_knowledge_flow_graph()
    state = initial_state("入口探测", knowledge_base_id=uuid.uuid4())
    out = kf.build_knowledge_flow_graph().invoke(
        state,
        config={"configurable": {"session": None, "user_id": uuid.uuid4()}},
    )
    assert out.get("answer")
    assert out["citations"]
