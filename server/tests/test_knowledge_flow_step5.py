"""Step 5: Knowledge Gap + Final Answer from merged evidence."""

from __future__ import annotations

import uuid

from app.agent import knowledge_flow as kf
from app.agent.decompose import make_sub_questions
from app.agent.graph import MAX_LOOPS, initial_state
from app.rag.search import SearchHit


def _complex(monkeypatch):
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})


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


def _hit(content: str = "body", *, score: float = 0.9) -> SearchHit:
    return SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content=content,
        score=score,
        page=1,
        heading=None,
        kind="note",
    )


def test_no_hits_max_loops_answer_has_knowledge_gap(monkeypatch):
    _complex(monkeypatch)
    """AC-06: always empty hits until MAX_LOOPS → Answer + Knowledge Gap."""
    questions = ["缺口A", "缺口B"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    n = 0

    def fake_rewrite(qi_question: str, *, user_query: str = ""):
        nonlocal n
        n += 1
        return {"query": f"{qi_question}#rw{n}"}

    monkeypatch.setattr(kf, "rewrite_query", fake_rewrite)
    monkeypatch.setattr(kf, "search_knowledge", lambda *a, **k: [])
    monkeypatch.setattr(
        "app.llm.chat",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no evidence → skip LLM")),
    )
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("全空"),
        config={"configurable": {"session": None}},
    )
    assert out["loop_count"] >= MAX_LOOPS
    assert all(sq["status"] == "INSUFFICIENT" for sq in out["sub_questions"])
    assert out["knowledge_gaps"] == questions
    assert kf.GAP_HEADING in out["answer"]
    assert "缺口A" in out["answer"] and "缺口B" in out["answer"]
    assert out["citations"] == []


def test_partial_evidence_gap_and_answer_coexist(monkeypatch):
    _complex(monkeypatch)
    questions = ["有证据", "仍缺口"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    n = 0

    def fake_rewrite(qi_question: str, *, user_query: str = ""):
        nonlocal n
        n += 1
        return {"query": f"{qi_question}#rw{n}"}

    monkeypatch.setattr(kf, "rewrite_query", fake_rewrite)

    def fake_search(session, query, **kwargs):
        if query == "有证据" or query.startswith("有证据"):
            return [_hit("证据正文", score=0.95)]
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "部分作答依据证据")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("半有"),
        config={"configurable": {"session": None}},
    )
    assert out["sub_questions"][0]["status"] == "SUFFICIENT"
    assert out["sub_questions"][1]["status"] == "INSUFFICIENT"
    assert out["knowledge_gaps"] == ["仍缺口"]
    assert "部分作答依据证据" in out["answer"]
    assert kf.GAP_HEADING in out["answer"]
    assert "仍缺口" in out["answer"]
    assert out["citations"]
    cite_ids = {str(c.get("chunk_id") or "") for c in out["citations"]}
    evidence_ids = {str(e.get("chunk_id") or e.get("id") or "") for e in out["evidence"]}
    assert cite_ids <= evidence_ids
    assert all(c.get("content") for c in out["citations"])


def test_gap_and_generate_audit_spans(monkeypatch):
    _complex(monkeypatch)
    questions = ["空问"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    n = 0

    def fake_rewrite(qi_question: str, *, user_query: str = ""):
        nonlocal n
        n += 1
        return {"query": f"rw{n}"}

    monkeypatch.setattr(kf, "rewrite_query", fake_rewrite)
    monkeypatch.setattr(kf, "search_knowledge", lambda *a, **k: [])
    recorder = FakeRecorder()
    monkeypatch.setattr(kf, "recorder_from_config", lambda config: recorder)
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("审计"),
        config={"configurable": {"session": None}},
    )
    steps = [(s["decision"] or {}).get("step") for s in recorder.spans]
    assert "merge" in steps
    assert "gap" in steps
    assert "generate" in steps
    gap_at = steps.index("gap")
    gen_at = steps.index("generate")
    assert steps.index("merge") < gap_at < gen_at
    gap = next(s for s in recorder.spans if (s["decision"] or {}).get("step") == "gap")
    assert gap["node_type"] == "route"
    assert gap["decision"]["output"]["gaps"] == ["空问"]
    assert gap["decision"]["input"]["insufficient_qi"]
    gen = next(s for s in recorder.spans if (s["decision"] or {}).get("step") == "generate")
    assert gen["node_type"] == "generate"
    assert "evidence_ids" in gen["decision"]["input"]
    assert "answer" in gen["decision"]["output"]
    assert kf.GAP_HEADING in out["answer"]
