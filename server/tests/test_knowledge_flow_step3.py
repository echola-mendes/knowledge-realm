"""Step 3: Decomposition clip + per-Qi initial retrieve graph contract."""

from __future__ import annotations

import uuid

from app.agent import knowledge_flow as kf
from app.agent.decompose import (
    MAX_SUB_QUESTIONS,
    clip_sub_questions,
    fallback_single_qi,
    make_sub_questions,
)
from app.agent.graph import initial_state
from app.rag.search import SearchHit


def _no_rewrite(monkeypatch):
    """Step 3 tests: avoid real LLM; duplicate rewrite → skip Tool."""
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "step3-stub")




class FakeRecorder:
    def __init__(self) -> None:
        self.spans: list[dict] = []

    def add_span(
        self,
        node_type: str,
        *,
        decision=None,
        rationale=None,
        evidence_refs=None,
        metrics=None,
    ):
        self.spans.append(
            {
                "node_type": node_type,
                "decision": decision,
                "rationale": rationale,
                "evidence_refs": evidence_refs,
                "metrics": metrics,
            }
        )
        return uuid.uuid4()


def test_clip_sub_questions_hard_cap_at_five():
    raw = [f"q{i}" for i in range(8)]
    assert clip_sub_questions(raw) == [f"q{i}" for i in range(5)]
    assert len(clip_sub_questions(raw)) == MAX_SUB_QUESTIONS


def test_clip_sub_questions_from_dict_items():
    raw = [{"question": "a"}, {"q": "b"}, {"question": ""}, "c"]
    assert clip_sub_questions(raw) == ["a", "b", "c"]


def test_n_qi_means_n_initial_searches_loop_count_stays_zero(monkeypatch):
    _no_rewrite(monkeypatch)
    questions = ["消息模型", "消费模式", "顺序保证"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="mq.md",
                chunk_id=uuid.uuid4(),
                content=f"about {query}",
                score=0.8,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    kf.reset_knowledge_flow_graph()
    state = initial_state("Kafka vs RabbitMQ 区别？")
    out = kf.build_knowledge_flow_graph().invoke(
        state,
        config={"configurable": {"session": None, "user_id": None}},
    )
    assert calls == questions
    assert out["loop_count"] == 0
    assert len(out["sub_questions"]) == 3
    assert all(sq["status"] == "SUFFICIENT" for sq in out["sub_questions"])
    assert len(out["evidence"]) == 3


def test_per_qi_retrieve_and_sufficiency_spans(monkeypatch):
    _no_rewrite(monkeypatch)
    questions = ["A", "B"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )

    def fake_search(session, query, **kwargs):
        if query == "B":
            return []
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="a.md",
                chunk_id=uuid.uuid4(),
                content="hit A",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    recorder = FakeRecorder()
    monkeypatch.setattr(kf, "recorder_from_config", lambda config: recorder)
    kf.reset_knowledge_flow_graph()
    state = initial_state("对比 A 和 B")
    out = kf.build_knowledge_flow_graph().invoke(
        state,
        config={"configurable": {"session": None}},
    )
    steps = [
        (s["node_type"], (s["decision"] or {}).get("step"))
        for s in recorder.spans
    ]
    assert steps[0] == ("route", "analyze")
    assert steps[1] == ("route", "decompose")
    assert steps[2] == ("retrieve", "retrieve_qi")
    assert steps[3] == ("route", "sufficiency")
    assert steps[4] == ("retrieve", "retrieve_qi")
    assert steps[5] == ("route", "sufficiency")

    retrieve_spans = [s for s in recorder.spans if (s["decision"] or {}).get("step") == "retrieve_qi"]
    assert len(retrieve_spans) == 2
    for span in retrieve_spans:
        d = span["decision"]
        assert "qi_id" in d["input"] and "query" in d["input"]
        assert "hit_count" in d["output"] and "hit_ids" in d["output"]

    suf_spans = [s for s in recorder.spans if (s["decision"] or {}).get("step") == "sufficiency"]
    assert len(suf_spans) == 2
    statuses = [s["decision"]["output"]["status"] for s in suf_spans]
    assert statuses == ["SUFFICIENT", "INSUFFICIENT"]
    assert all("hit_count" in s["decision"]["output"] for s in suf_spans)
    assert out["sub_questions"][0]["status"] == "SUFFICIENT"
    assert out["sub_questions"][1]["status"] == "INSUFFICIENT"


def test_decompose_failure_falls_back_to_single_qi(monkeypatch):
    _no_rewrite(monkeypatch)
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": fallback_single_qi(query)},
    )
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    kf.reset_knowledge_flow_graph()
    state = initial_state("单一问题")
    out = kf.build_knowledge_flow_graph().invoke(
        state,
        config={"configurable": {"session": None}},
    )
    assert calls == ["单一问题"]
    assert len(out["sub_questions"]) == 1
    assert out["loop_count"] == 0


def test_more_than_five_sub_questions_truncated_in_graph(monkeypatch):
    _no_rewrite(monkeypatch)
    six = make_sub_questions([f"q{i}" for i in range(6)])
    monkeypatch.setattr(kf, "decompose_query", lambda query: {"sub_questions": six})
    calls: list[str] = []

    def fake_search(session, query, **kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("很多点"),
        config={"configurable": {"session": None}},
    )
    assert len(out["sub_questions"]) == 5
    assert len(calls) == 5
    assert out["loop_count"] == 0
