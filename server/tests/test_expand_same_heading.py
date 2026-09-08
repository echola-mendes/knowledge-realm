from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.rag.search import (
    SECTION_EXPAND_MAX_CHARS,
    SearchHit,
    _center_out_chunks,
    _expand_same_heading,
)


def _hit(
    *,
    doc_id: uuid.UUID,
    chunk_id: uuid.UUID,
    content: str,
    score: float,
    heading: str | None,
    name: str = "doc.md",
) -> SearchHit:
    return SearchHit(
        document_id=doc_id,
        document_name=name,
        chunk_id=chunk_id,
        content=content,
        score=score,
        page=None,
        heading=heading,
        kind="note",
    )


def _chunk(
    *,
    chunk_id: uuid.UUID,
    doc_id: uuid.UUID,
    index: int,
    content: str,
    heading: str | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=index,
        content=content,
        heading=heading,
    )


def _session_with(chunks: list[SimpleNamespace]) -> MagicMock:
    session = MagicMock()
    session.scalars.return_value.all.return_value = chunks
    return session


def test_search_hit_original_content_defaults_empty():
    hit = SearchHit(
        document_id=uuid.uuid4(),
        document_name="a.md",
        chunk_id=uuid.uuid4(),
        content="body",
        score=0.5,
        page=None,
        heading="H",
        kind="note",
    )
    assert hit.original_content == ""


def test_expand_whole_section_and_original_content():
    doc_id = uuid.uuid4()
    c0_id, c1_id, c2_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    siblings = [
        _chunk(chunk_id=c0_id, doc_id=doc_id, index=0, content="C0", heading="Sec"),
        _chunk(chunk_id=c1_id, doc_id=doc_id, index=1, content="C1", heading="Sec"),
        _chunk(chunk_id=c2_id, doc_id=doc_id, index=2, content="C2", heading="Sec"),
    ]
    hit = _hit(doc_id=doc_id, chunk_id=c1_id, content="C1", score=0.9, heading="Sec")
    out = _expand_same_heading(_session_with(siblings), [hit])
    assert len(out) == 1
    assert out[0].chunk_id == c1_id
    assert out[0].original_content == "C1"
    assert out[0].content == "C0\n\nC1\n\nC2"
    assert out[0].score == 0.9


def test_expand_dedupes_same_section_keeps_highest_score():
    doc_id = uuid.uuid4()
    c0_id, c1_id = uuid.uuid4(), uuid.uuid4()
    siblings = [
        _chunk(chunk_id=c0_id, doc_id=doc_id, index=0, content="C0", heading="Sec"),
        _chunk(chunk_id=c1_id, doc_id=doc_id, index=1, content="C1", heading="Sec"),
    ]
    low = _hit(doc_id=doc_id, chunk_id=c0_id, content="C0", score=0.2, heading="Sec")
    high = _hit(doc_id=doc_id, chunk_id=c1_id, content="C1", score=0.8, heading="Sec")
    out = _expand_same_heading(_session_with(siblings), [low, high])
    assert len(out) == 1
    assert out[0].chunk_id == c1_id
    assert out[0].original_content == "C1"
    assert "C0" in out[0].content and "C1" in out[0].content


def test_expand_blank_heading_skips():
    doc_id = uuid.uuid4()
    cid = uuid.uuid4()
    hit_none = _hit(doc_id=doc_id, chunk_id=cid, content="alone", score=0.5, heading=None)
    hit_empty = _hit(doc_id=doc_id, chunk_id=uuid.uuid4(), content="empty", score=0.4, heading="")
    session = MagicMock()
    out = _expand_same_heading(session, [hit_none, hit_empty])
    session.scalars.assert_not_called()
    assert len(out) == 2
    assert out[0].content == "alone" and out[0].original_content == "alone"
    assert out[1].content == "empty" and out[1].original_content == "empty"


def test_expand_budget_skips_neighbor_no_truncation():
    doc_id = uuid.uuid4()
    c0_id, c1_id, c2_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # center 3000; each neighbor 1500 → can take only one side at dist 1 then stop
    c0 = "L" * 1500
    c1 = "C" * 3000
    c2 = "R" * 1500
    siblings = [
        _chunk(chunk_id=c0_id, doc_id=doc_id, index=0, content=c0, heading="Sec"),
        _chunk(chunk_id=c1_id, doc_id=doc_id, index=1, content=c1, heading="Sec"),
        _chunk(chunk_id=c2_id, doc_id=doc_id, index=2, content=c2, heading="Sec"),
    ]
    hit = _hit(doc_id=doc_id, chunk_id=c1_id, content=c1, score=0.7, heading="Sec")
    out = _expand_same_heading(_session_with(siblings), [hit])
    assert len(out) == 1
    assert out[0].original_content == c1
    assert c1 in out[0].content
    # left tried first and fits (3000+1500=4500? no 4500>4000) — left fails, right fails → only center
    assert out[0].content == c1
    assert len(out[0].content) == 3000


def test_center_out_includes_hit_when_over_budget_alone():
    doc_id = uuid.uuid4()
    c0_id, c1_id = uuid.uuid4(), uuid.uuid4()
    huge = "H" * (SECTION_EXPAND_MAX_CHARS + 50)
    siblings = [
        _chunk(chunk_id=c0_id, doc_id=doc_id, index=0, content="small", heading="Sec"),
        _chunk(chunk_id=c1_id, doc_id=doc_id, index=1, content=huge, heading="Sec"),
    ]
    chosen = _center_out_chunks(siblings, c1_id)
    assert len(chosen) == 1
    assert chosen[0].id == c1_id
    assert chosen[0].content == huge


def test_center_out_left_fail_still_tries_right():
    doc_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(3)]
    # center 2500; left 2000 fails; right 1000 fits
    siblings = [
        _chunk(chunk_id=ids[0], doc_id=doc_id, index=0, content="L" * 2000, heading="Sec"),
        _chunk(chunk_id=ids[1], doc_id=doc_id, index=1, content="C" * 2500, heading="Sec"),
        _chunk(chunk_id=ids[2], doc_id=doc_id, index=2, content="R" * 1000, heading="Sec"),
    ]
    chosen = _center_out_chunks(siblings, ids[1])
    assert [c.id for c in chosen] == [ids[1], ids[2]]
    assert "".join(c.content for c in chosen)  # no truncation inside chunks
    assert all(len(c.content) in (2500, 1000) for c in chosen)
