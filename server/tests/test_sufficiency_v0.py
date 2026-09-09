"""Sufficiency V0 + knowledge span decision / evidence_refs shape."""

from __future__ import annotations

import uuid

from app.agent.sufficiency import (
    INSUFFICIENT,
    RULE_V0,
    SUFFICIENT,
    sufficiency_decision,
    sufficiency_v0,
)
from app.audit.evidence import search_hit_evidence_ref
from app.rag.search import SearchHit


def _hit(*, score: float = 0.01) -> SearchHit:
    return SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content="hit body text for excerpt",
        score=score,
        page=1,
        heading=None,
        kind="markdown",
        original_content="hit body text for excerpt",
    )


def test_sufficiency_v0_empty_is_insufficient():
    assert sufficiency_v0([]) is INSUFFICIENT
    assert sufficiency_v0(()) == INSUFFICIENT


def test_sufficiency_v0_nonempty_is_sufficient_ignores_score():
    assert sufficiency_v0([_hit(score=0.0)]) is SUFFICIENT
    assert sufficiency_v0([_hit(score=-1.0), _hit(score=0.99)]) is SUFFICIENT


def test_sufficiency_decision_shape():
    hits = [_hit()]
    decision = sufficiency_decision(hits, qi_id="q1", query="what is x")
    assert set(decision.keys()) == {"step", "input", "output"}
    assert decision["step"] == "sufficiency"
    assert decision["input"]["hit_count"] == 1
    assert decision["input"]["qi_id"] == "q1"
    assert decision["input"]["query"] == "what is x"
    assert decision["output"]["status"] == SUFFICIENT
    assert decision["output"]["rule"] == RULE_V0
    assert decision["output"]["hit_count"] == 1


def test_sufficiency_decision_empty_hits():
    decision = sufficiency_decision([])
    assert decision["output"]["status"] == INSUFFICIENT
    assert decision["input"]["hit_count"] == 0


def test_evidence_refs_excerpt_and_ids_with_qi():
    hit = _hit(score=0.42)
    parent = uuid.uuid4()
    hit.parent_id = parent
    ref = search_hit_evidence_ref(hit, qi_id="qi-2")
    assert ref["excerpt"] == "hit body text for excerpt"
    assert ref["id"] == str(hit.chunk_id)
    assert ref["chunk_id"] == str(hit.chunk_id)
    assert ref["document_id"] == str(hit.document_id)
    assert ref["document_name"] == "doc.md"
    assert ref["score"] == 0.42
    assert ref["parent_id"] == str(parent)
    assert ref["qi_id"] == "qi-2"
