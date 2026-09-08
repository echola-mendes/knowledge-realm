from __future__ import annotations

import uuid
from dataclasses import replace

from app.audit.evidence import context_assembly_summary, search_hit_evidence_ref
from app.rag.search import SearchHit


def test_search_hit_evidence_ref_child_only():
    hit = SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content="child text",
        score=0.9,
        page=1,
        heading=None,
        kind="markdown",
        original_content="child text",
    )
    ref = search_hit_evidence_ref(hit)
    assert ref["assembly"] == "child_only"
    assert ref["excerpt"] == "child text"
    assert "original_excerpt" not in ref


def test_search_hit_evidence_ref_parent():
    parent_id = uuid.uuid4()
    hit = SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content="parent full section text",
        score=0.85,
        page=1,
        heading="Intro",
        kind="markdown",
        original_content="child snippet",
        parent_id=parent_id,
    )
    ref = search_hit_evidence_ref(hit)
    assert ref["assembly"] == "parent"
    assert ref["parent_id"] == str(parent_id)
    assert ref["original_excerpt"] == "child snippet"
    assert ref["context_chars"] == len("parent full section text")


def test_context_assembly_summary():
    child = SearchHit(
        document_id=uuid.uuid4(),
        document_name="a",
        chunk_id=uuid.uuid4(),
        content="x",
        score=1.0,
        page=None,
        heading=None,
        kind="markdown",
        original_content="x",
    )
    expanded = replace(
        child,
        content="expanded",
        original_content="x",
        heading="H",
    )
    summary = context_assembly_summary([child, expanded])
    assert summary["child_only"] == 1
    assert summary["heading_expand"] == 1
