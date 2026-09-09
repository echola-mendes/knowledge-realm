from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import load_settings, reset_settings
from app.rag import search as search_mod
from app.rag.search import (
    SearchHit,
    _hits_for_ids,
    _neighbor_expand,
    _section_siblings,
    _vector_stmt,
    search_chunks,
    search_debug,
)


def _emb(*vals: float) -> list[float]:
    return list(vals)


def _hit(
    *,
    doc_id: uuid.UUID,
    chunk_id: uuid.UUID,
    content: str,
    score: float,
    heading: str | None = "Sec",
    parent_id: uuid.UUID | None = None,
) -> SearchHit:
    return SearchHit(
        document_id=doc_id,
        document_name="doc.md",
        chunk_id=chunk_id,
        content=content,
        score=score,
        page=None,
        heading=heading,
        kind="note",
        parent_id=parent_id,
    )


def _chunk(
    *,
    chunk_id: uuid.UUID,
    doc_id: uuid.UUID,
    index: int,
    content: str,
    embedding: list[float],
    heading: str | None = "Sec",
    parent_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=index,
        content=content,
        heading=heading,
        parent_id=parent_id,
        embedding=embedding,
        role="child",
    )


def _session_with(chunks: list[SimpleNamespace]) -> MagicMock:
    session = MagicMock()
    session.scalars.return_value.all.return_value = chunks
    return session


@pytest.fixture(autouse=True)
def _reset_settings_after():
    yield
    reset_settings()


def test_search_hit_neighbor_fields_default_empty():
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
    assert hit.neighbor_chunk_ids == []
    assert hit.expanded_chunk_ids == []
    assert hit.original_content == ""


def test_af_hits_merge_one_and_cd_not_neighbors(monkeypatch):
    """Same parent A/F hits → 1 merged hit; C/D ∉ neighbor_chunk_ids."""
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(7)]  # A B C D E F G
    labels = "ABCDEFG"
    emb = _emb(1.0, 0.0, 0.0)
    siblings = [
        _chunk(
            chunk_id=ids[i],
            doc_id=doc_id,
            index=i,
            content=labels[i],
            embedding=emb,
            parent_id=parent_id,
        )
        for i in range(7)
    ]
    hit_a = _hit(doc_id=doc_id, chunk_id=ids[0], content="A", score=0.9, parent_id=parent_id)
    hit_f = _hit(doc_id=doc_id, chunk_id=ids[5], content="F", score=0.8, parent_id=parent_id)
    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: False)
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    out = _neighbor_expand(_session_with(siblings), "q", emb, [hit_a, hit_f])
    assert len(out) == 1
    merged = out[0]
    assert merged.chunk_id == ids[0]  # max score seed
    assert merged.score == 0.9
    assert set(merged.neighbor_chunk_ids) == {ids[1], ids[4], ids[6]}  # B,E,G
    assert ids[2] not in merged.neighbor_chunk_ids  # C
    assert ids[3] not in merged.neighbor_chunk_ids  # D
    assert "A" in merged.content and "F" in merged.content
    assert merged.original_content == "A"


def test_adjacent_hits_same_parent_merge_one_context(monkeypatch):
    """Adjacent seeds A/B → one hit; content not duplicated as two identical blobs."""
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    emb = _emb(1.0, 0.0)
    siblings = [
        _chunk(chunk_id=a_id, doc_id=doc_id, index=0, content="A-body", embedding=emb, parent_id=parent_id),
        _chunk(chunk_id=b_id, doc_id=doc_id, index=1, content="B-body", embedding=emb, parent_id=parent_id),
        _chunk(chunk_id=c_id, doc_id=doc_id, index=2, content="C-body", embedding=emb, parent_id=parent_id),
    ]
    hit_a = _hit(doc_id=doc_id, chunk_id=a_id, content="A-body", score=0.7, parent_id=parent_id)
    hit_b = _hit(doc_id=doc_id, chunk_id=b_id, content="B-body", score=0.95, parent_id=parent_id)
    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: False)
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    out = _neighbor_expand(_session_with(siblings), "q", emb, [hit_a, hit_b])
    assert len(out) == 1
    assert out[0].chunk_id == b_id
    assert out[0].score == 0.95
    assert out[0].neighbor_chunk_ids == [c_id]  # only non-seed ±1
    assert c_id in out[0].expanded_chunk_ids
    assert out[0].content == "A-body\n\nB-body\n\nC-body"
    assert out[0].original_content == "B-body"
    assert out[0].seed_chunk_ids == [a_id, b_id]


def test_dual_condition_requires_both(monkeypatch):
    """§6.2–3: only anchor-sim or only query-score → not expanded."""
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    emb_a = _emb(1.0, 0.0)
    emb_b = _emb(0.95, 0.05)
    emb_c = _emb(0.0, 1.0)
    siblings = [
        _chunk(chunk_id=a_id, doc_id=doc_id, index=0, content="A", embedding=emb_a, parent_id=parent_id),
        _chunk(chunk_id=b_id, doc_id=doc_id, index=1, content="B", embedding=emb_b, parent_id=parent_id),
        _chunk(chunk_id=c_id, doc_id=doc_id, index=2, content="C", embedding=emb_c, parent_id=parent_id),
    ]
    hit = _hit(doc_id=doc_id, chunk_id=b_id, content="B", score=0.9, parent_id=parent_id)

    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: True)
    monkeypatch.setattr(
        search_mod,
        "score_documents",
        lambda query, docs: [0.1 if d == "A" else 0.9 for d in docs],
    )
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    out = _neighbor_expand(_session_with(siblings), "q", emb_a, [hit])
    assert len(out) == 1
    assert set(out[0].neighbor_chunk_ids) == {a_id, c_id}
    assert out[0].expanded_chunk_ids == []
    assert out[0].content == "B"
    assert out[0].original_content == "B"


def test_blank_heading_without_parent_skips_expand(monkeypatch):
    """确认① B: 无 parent + heading 空 → 两列表 []; 有 parent + heading 空仍可 ±1."""
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    emb = _emb(1.0, 0.0)
    children = [
        _chunk(
            chunk_id=a_id,
            doc_id=doc_id,
            index=0,
            content="A",
            embedding=emb,
            heading="",
            parent_id=parent_id,
        ),
        _chunk(
            chunk_id=b_id,
            doc_id=doc_id,
            index=1,
            content="B",
            embedding=emb,
            heading="",
            parent_id=parent_id,
        ),
    ]
    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: False)
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    with_parent = _hit(
        doc_id=doc_id,
        chunk_id=a_id,
        content="A",
        score=0.9,
        heading="",
        parent_id=parent_id,
    )
    out_parent = _neighbor_expand(_session_with(children), "q", emb, [with_parent])
    assert out_parent[0].neighbor_chunk_ids == [b_id]
    assert b_id in out_parent[0].expanded_chunk_ids

    alone_id = uuid.uuid4()
    alone = _hit(doc_id=doc_id, chunk_id=alone_id, content="alone", score=0.5, heading=None)
    session = MagicMock()
    out_alone = _neighbor_expand(session, "q", emb, [alone])
    session.scalars.assert_not_called()
    assert out_alone[0].neighbor_chunk_ids == []
    assert out_alone[0].expanded_chunk_ids == []
    assert out_alone[0].content == "alone"


def test_query_score_uses_rerank_when_key_ready(monkeypatch):
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    emb = _emb(1.0, 0.0)
    siblings = [
        _chunk(chunk_id=a_id, doc_id=doc_id, index=0, content="A", embedding=emb, parent_id=parent_id),
        _chunk(chunk_id=b_id, doc_id=doc_id, index=1, content="B", embedding=emb, parent_id=parent_id),
    ]
    hit = _hit(doc_id=doc_id, chunk_id=a_id, content="A", score=0.9, parent_id=parent_id)
    called: list[list[str]] = []

    def fake_score(query: str, documents: list[str]):
        called.append(list(documents))
        return [0.9 for _ in documents]

    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: True)
    monkeypatch.setattr(search_mod, "score_documents", fake_score)
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    out = _neighbor_expand(_session_with(siblings), "q", emb, [hit])
    assert called == [["B"]]
    assert out[0].expanded_chunk_ids == [b_id]


def test_query_score_falls_back_to_cosine_without_rerank_key(monkeypatch):
    doc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    emb = _emb(1.0, 0.0)
    siblings = [
        _chunk(chunk_id=a_id, doc_id=doc_id, index=0, content="A", embedding=emb, parent_id=parent_id),
        _chunk(chunk_id=b_id, doc_id=doc_id, index=1, content="B", embedding=emb, parent_id=parent_id),
    ]
    hit = _hit(doc_id=doc_id, chunk_id=a_id, content="A", score=0.9, parent_id=parent_id)

    def boom(*_a, **_k):
        raise AssertionError("score_documents should not be used without rerank key")

    monkeypatch.setattr(search_mod, "rerank_keys_ready", lambda: False)
    monkeypatch.setattr(search_mod, "score_documents", boom)
    monkeypatch.setattr(
        search_mod,
        "get_settings",
        lambda: SimpleNamespace(expand_anchor_min=0.6, expand_query_min=0.3),
    )
    out = _neighbor_expand(_session_with(siblings), "q", emb, [hit])
    assert out[0].expanded_chunk_ids == [b_id]


def test_expand_defaults_in_settings():
    s = load_settings(environ={"DATABASE_URL": "postgresql://x"}, load_file=False)
    assert s.expand_anchor_min == 0.6
    assert s.expand_query_min == 0.3


def test_section_siblings_query_filters_child_role():
    src = inspect.getsource(_section_siblings)
    assert 'role == "child"' in src


def test_vector_and_id_recall_require_child_with_embedding():
    vector_src = inspect.getsource(_vector_stmt)
    hits_src = inspect.getsource(_hits_for_ids)
    for src in (vector_src, hits_src):
        assert 'role == "child"' in src
        assert "embedding.isnot(None)" in src


def test_search_chunks_uses_neighbor_expand_debug_does_not():
    chunks_src = inspect.getsource(search_chunks)
    debug_src = inspect.getsource(search_debug)
    assert "_neighbor_expand" in chunks_src
    assert "_neighbor_expand(session, query, query_vec, _keep_relevant(_rerank(query, hits)))" in chunks_src
    assert "_assemble_parent_context" not in chunks_src
    assert "_neighbor_expand" not in debug_src
    assert "_assemble_parent_context" not in debug_src
    assert "_expand_same_heading" not in debug_src


def test_old_assemble_symbols_removed():
    assert not hasattr(search_mod, "_assemble_parent_context")
    assert not hasattr(search_mod, "_assemble_with_parent")
    assert not hasattr(search_mod, "_expand_same_heading")
    assert not hasattr(search_mod, "_center_out_chunks")
