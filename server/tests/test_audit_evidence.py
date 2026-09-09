from __future__ import annotations

import uuid

from app.audit.evidence import context_assembly_summary, search_hit_evidence_ref
from app.rag.search import SearchHit


def test_search_hit_evidence_ref_child_only():
    neighbor = uuid.uuid4()
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
        neighbor_chunk_ids=[neighbor],
        expanded_chunk_ids=[],
    )
    ref = search_hit_evidence_ref(hit)
    assert ref["assembly"] == "child_only"
    assert ref["excerpt"] == "child text"
    assert "original_excerpt" not in ref
    assert ref["neighbor_chunk_ids"] == [str(neighbor)]
    assert ref["expanded_chunk_ids"] == []
    assert ref["dropped"] == [str(neighbor)]


def test_search_hit_evidence_ref_neighbor_expand():
    parent_id = uuid.uuid4()
    neighbor_kept = uuid.uuid4()
    neighbor_drop = uuid.uuid4()
    hit = SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content="anchor\n\nkept neighbor",
        score=0.85,
        page=1,
        heading="Intro",
        kind="markdown",
        original_content="anchor",
        parent_id=parent_id,
        neighbor_chunk_ids=[neighbor_kept, neighbor_drop],
        expanded_chunk_ids=[neighbor_kept],
    )
    ref = search_hit_evidence_ref(hit)
    assert ref["assembly"] == "neighbor_expand"
    assert ref["parent_id"] == str(parent_id)
    assert ref["original_excerpt"] == "anchor"
    assert ref["context_chars"] == len("anchor\n\nkept neighbor")
    assert ref["neighbor_chunk_ids"] == [str(neighbor_kept), str(neighbor_drop)]
    assert ref["expanded_chunk_ids"] == [str(neighbor_kept)]
    assert ref["dropped"] == [str(neighbor_drop)]


def test_search_hit_evidence_ref_multi_seed_without_neighbor_is_expand():
    """Joined seeds with empty expanded_chunk_ids still count as neighbor_expand."""
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    hit = SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=b_id,
        content="A\n\nB",
        score=0.9,
        page=1,
        heading="H",
        kind="markdown",
        original_content="B",
        seed_chunk_ids=[a_id, b_id],
        neighbor_chunk_ids=[],
        expanded_chunk_ids=[],
    )
    ref = search_hit_evidence_ref(hit)
    assert ref["assembly"] == "neighbor_expand"
    assert ref["seed_chunk_ids"] == [str(a_id), str(b_id)]
    assert ref["original_chars"] == 1
    assert ref["context_chars"] == len("A\n\nB")


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
    expanded = SearchHit(
        document_id=uuid.uuid4(),
        document_name="a",
        chunk_id=uuid.uuid4(),
        content="x\n\ny",
        score=0.8,
        page=None,
        heading="H",
        kind="markdown",
        original_content="x",
        neighbor_chunk_ids=[uuid.uuid4()],
        expanded_chunk_ids=[uuid.uuid4()],
    )
    summary = context_assembly_summary([child, expanded])
    assert summary == {"child_only": 1, "neighbor_expand": 1}
