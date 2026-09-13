"""ReAct evidence precheck + LLM sufficiency (knowledge_flow V0 untouched)."""

from __future__ import annotations

from app.agent.evidence_sufficiency import (
    EvidenceSufficiencyResult,
    assign_evidence_qi_id,
    evaluate_evidence_sufficiency,
    format_sufficiency_observation,
)
from app.agent.sufficiency import (
    HAS_VALID_EVIDENCE,
    NO_VALID_EVIDENCE,
    RULE_V0,
    INSUFFICIENT,
    SUFFICIENT,
    precheck_evidence,
    sufficiency_v0,
)


def _ev(eid: str, content: str = "body", **extra):
    item = {"id": eid, "chunk_id": eid, "content": content}
    item.update(extra)
    return item


def test_precheck_empty_is_no_valid():
    out = precheck_evidence([])
    assert out["status"] == NO_VALID_EVIDENCE
    assert out["valid_evidence"] == []


def test_precheck_blank_content_and_dup_filtered():
    out = precheck_evidence(
        [
            _ev("e1", ""),
            _ev("e2", "   "),
            {"content": "x"},  # missing id
            _ev("e3", "ok"),
            _ev("e3", "ok-dup"),
        ]
    )
    assert out["status"] == HAS_VALID_EVIDENCE
    assert out["valid_count"] == 1
    assert out["valid_evidence"][0]["id"] == "e3"


def test_evaluate_no_valid_skips_llm():
    called = {"n": 0}

    def boom(_msgs):
        called["n"] += 1
        raise AssertionError("LLM must not be called")

    out = evaluate_evidence_sufficiency(
        user_question="q",
        evidence=[_ev("e1", "")],
        llm_invoke=boom,
    )
    assert called["n"] == 0
    assert out["llm_called"] is False
    assert out["precheck"] == NO_VALID_EVIDENCE
    assert out["sufficient"] is False
    assert out["status"] == INSUFFICIENT


def test_evaluate_calls_llm_when_valid():
    def fake(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=["a"],
            missing_aspects=["b"],
            gaps=["need b"],
            reason="partial",
        )

    out = evaluate_evidence_sufficiency(
        user_question="q",
        evidence=[_ev("e1", "text about a")],
        qi={"id": "q1", "question": "why", "aspects": ["a", "b"]},
        llm_invoke=fake,
    )
    assert out["llm_called"] is True
    assert out["precheck"] == HAS_VALID_EVIDENCE
    assert out["sufficient"] is False
    assert out["covered_aspects"] == ["a"]
    assert out["missing_aspects"] == ["b"]
    assert out["gaps"] == ["need b"]
    assert out["reason"] == "partial"


def test_format_observation_contains_instruction():
    text = format_sufficiency_observation(
        {
            "sufficient": False,
            "precheck": HAS_VALID_EVIDENCE,
            "covered_aspects": ["x"],
            "missing_aspects": ["y"],
            "gaps": ["g"],
            "reason": "r",
        },
        qi_id="q1",
    )
    assert "[Evidence Sufficiency]" in text
    assert "qi_id: q1" in text
    assert "missing_aspects" in text
    assert "instruction:" in text


def test_assign_qi_priority_explicit_then_match_then_unassigned():
    qis = [
        {"id": "q1", "question": "原因是什么"},
        {"id": "q2", "question": "怎么排查"},
    ]
    assert assign_evidence_qi_id(query="x", sub_questions=qis, explicit_qi_id="q2") == "q2"
    assert assign_evidence_qi_id(query="怎么排查", sub_questions=qis) == "q2"
    assert assign_evidence_qi_id(query="无关", sub_questions=qis) == "unassigned"


def test_sufficiency_v0_unchanged_smoke():
    assert sufficiency_v0([]) == INSUFFICIENT
    assert sufficiency_v0([object()]) == SUFFICIENT
    assert RULE_V0 == "len(hits)>0"
