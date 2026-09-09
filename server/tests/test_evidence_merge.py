"""Evidence Pool Merge: dedup, Top-N budget, merge span shape."""

from __future__ import annotations

import uuid

from app.agent.evidence_merge import (
    MAX_EVIDENCE,
    evidence_from_hit,
    merge_decision,
    merge_evidence,
    merge_evidence_refs,
)
from app.rag.search import SearchHit


def _hit(
    chunk_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    score: float = 0.5,
    content: str = "body",
) -> SearchHit:
    return SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=chunk_id or uuid.uuid4(),
        content=content,
        score=score,
        page=1,
        heading=None,
        kind="markdown",
        original_content=content,
        parent_id=parent_id,
    )


def test_merge_same_parent_different_chunk_keeps_both():
    parent = uuid.uuid4()
    a = evidence_from_hit(
        _hit(parent_id=parent, score=0.4, content="low"),
        qi_id="q1",
        question="what is A",
    )
    b = evidence_from_hit(
        _hit(parent_id=parent, score=0.9, content="high"),
        qi_id="q2",
        question="what is B",
    )
    result = merge_evidence([a, b])
    assert len(result["merged"]) == 2
    by_content = {m["content"]: m for m in result["merged"]}
    assert set(by_content) == {"low", "high"}
    assert by_content["high"]["score"] == 0.9
    assert by_content["low"]["related_questions"] == ["what is A"]
    assert by_content["high"]["related_questions"] == ["what is B"]
    assert result["dropped"] == []


def test_merge_same_chunk_id_keeps_best_and_merges_related_questions():
    chunk = uuid.uuid4()
    a = evidence_from_hit(
        _hit(chunk_id=chunk, score=0.2, content="x"),
        qi_id="q1",
        question="Q1",
    )
    b = evidence_from_hit(
        _hit(chunk_id=chunk, score=0.8, content="y"),
        qi_id="q2",
        question="Q2",
    )
    b["id"] = a["id"]
    b["chunk_id"] = a["chunk_id"]
    b["document_id"] = a["document_id"]
    result = merge_evidence([a, b])
    assert len(result["merged"]) == 1
    assert result["merged"][0]["score"] == 0.8
    assert result["merged"][0]["related_questions"] == ["Q1", "Q2"]


def test_merge_top_n_by_score_respects_max_evidence():
    pool = [
        evidence_from_hit(_hit(score=float(i) / 100.0, content=f"c{i}"), qi_id=f"q{i}")
        for i in range(MAX_EVIDENCE + 5)
    ]
    result = merge_evidence(pool)
    assert len(result["merged"]) == MAX_EVIDENCE
    scores = [m["score"] for m in result["merged"]]
    assert scores == sorted(scores, reverse=True)
    assert len(result["dropped"]) == 5
    assert result["input_count"] == MAX_EVIDENCE + 5


def test_merge_decision_span_input_output():
    parent = uuid.uuid4()
    pool = [
        evidence_from_hit(
            _hit(parent_id=parent, score=0.3),
            qi_id="q1",
            question="A",
        ),
        evidence_from_hit(
            _hit(parent_id=parent, score=0.7),
            qi_id="q2",
            question="B",
        ),
        evidence_from_hit(_hit(score=0.5), qi_id="q1", question="A"),
    ]
    result = merge_evidence(pool)
    assert len(result["merged"]) == 3
    decision = merge_decision(result)
    assert decision["step"] == "merge"
    assert decision["input"]["count"] == 3
    assert set(decision["input"]["by_qi"].keys()) == {"q1", "q2"}
    assert decision["output"]["count"] == len(result["merged"])
    assert isinstance(decision["output"]["ids"], list)
    assert isinstance(decision["output"]["dropped"], list)
    assert decision["input"]["count"] == decision["output"]["count"] + len(
        decision["output"]["dropped"]
    ) or len(decision["output"]["dropped"]) >= 1
    refs = merge_evidence_refs(result["merged"])
    assert "excerpt" in refs[0]
    assert "chunk_id" in refs[0]
