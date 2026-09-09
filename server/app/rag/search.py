from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.rag.es_bm25 import require_elasticsearch_url, search_chunk_ids, search_chunk_scores
from app.ingest.index import STATUS_READY, embed_texts
from app.kb import search_kb_ids
from app.models import Document, DocumentChunk, DocumentTag, KnowledgeBase, RetrievalLabel
from app.rag.rerank import RERANK_CANDIDATE_MAX, rerank_keys_ready, score_documents
from app.schemas import (
    RetrievalDebugResponse,
    RetrievalDebugRow,
    RetrievalEvalOut,
    RetrievalStageOut,
    RetrievalTimingsOut,
)

SCORE_THRESHOLD = 0.30
DEFAULT_K = 5
RRF_K = 60
SECTION_EXPAND_MAX_CHARS = 4000


@dataclass
class SearchHit:
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    content: str
    score: float
    page: int | None
    heading: str | None
    kind: str
    original_content: str = ""
    parent_id: uuid.UUID | None = None
    neighbor_chunk_ids: list[uuid.UUID] = field(default_factory=list)
    expanded_chunk_ids: list[uuid.UUID] = field(default_factory=list)
    seed_chunk_ids: list[uuid.UUID] = field(default_factory=list)


def normalize_query(query: str) -> str:
    return " ".join(query.strip().split()).casefold()[:500]


def _similarity(distance: float) -> float:
    return 1.0 - float(distance)


def _rrf(rank: int, k_const: int = RRF_K) -> float:
    return 1.0 / (k_const + rank)


def _hit_from_row(chunk: DocumentChunk, doc: Document, dist: float) -> SearchHit:
    return SearchHit(
        document_id=doc.id,
        document_name=doc.filename,
        chunk_id=chunk.id,
        content=chunk.content,
        score=_similarity(dist),
        page=chunk.page,
        heading=chunk.heading,
        kind=doc.kind,
        parent_id=chunk.parent_id,
    )


def _tagged_document_ids(session: Session, tag_id: uuid.UUID) -> frozenset[uuid.UUID]:
    rows = session.scalars(select(DocumentTag.document_id).where(DocumentTag.tag_id == tag_id)).all()
    return frozenset(rows)


def _docs_in_time_window(
    session: Session,
    kb_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    created_after: datetime | None,
    created_before: datetime | None,
) -> frozenset[uuid.UUID] | None:
    if created_after is None and created_before is None:
        return None
    stmt = (
        select(Document.id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            Document.knowledge_base_id.in_(kb_ids),
            Document.status == STATUS_READY,
            KnowledgeBase.user_id == user_id,
        )
    )
    if created_after is not None:
        stmt = stmt.where(Document.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(Document.created_at <= created_before)
    return frozenset(session.scalars(stmt).all())


def _vector_stmt(
    session: Session,
    query_vec,
    kb_ids,
    user_id,
    tag_id,
    kind,
    document_id,
    limit: int,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
):
    distance = DocumentChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(DocumentChunk, Document, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            DocumentChunk.role == "child",
            DocumentChunk.embedding.isnot(None),
            Document.knowledge_base_id.in_(kb_ids),
            Document.status == STATUS_READY,
            KnowledgeBase.user_id == user_id,
        )
    )
    if tag_id is not None:
        stmt = stmt.join(DocumentTag, DocumentTag.document_id == Document.id).where(DocumentTag.tag_id == tag_id)
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    if document_id is not None:
        stmt = stmt.where(Document.id == document_id)
    if created_after is not None:
        stmt = stmt.where(Document.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(Document.created_at <= created_before)
    return session.execute(stmt.order_by(distance).limit(limit)).all()


def _hits_for_ids(session: Session, query_vec, kb_ids, user_id, chunk_ids: list[uuid.UUID]) -> dict[uuid.UUID, SearchHit]:
    if not chunk_ids:
        return {}
    dist = DocumentChunk.embedding.cosine_distance(query_vec)
    extra = session.execute(
        select(DocumentChunk, Document, dist)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.role == "child",
            DocumentChunk.embedding.isnot(None),
            Document.knowledge_base_id.in_(kb_ids),
            Document.status == STATUS_READY,
            KnowledgeBase.user_id == user_id,
        )
    ).all()
    return {chunk.id: _hit_from_row(chunk, doc, d) for chunk, doc, d in extra}


def search_chunks(
    session: Session,
    query: str,
    *,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    k: int = DEFAULT_K,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> list[SearchHit]:
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20")
    require_elasticsearch_url()
    kb_ids = search_kb_ids(session, user_id, knowledge_base_id)
    if not kb_ids:
        return []
    time_docs = _docs_in_time_window(session, kb_ids, user_id, created_after, created_before)
    if time_docs is not None and not time_docs:
        return []
    query_vec = embed_texts([query])[0]
    rows = _vector_stmt(
        session,
        query_vec,
        kb_ids,
        user_id,
        tag_id,
        kind,
        document_id,
        k,
        created_after=created_after,
        created_before=created_before,
    )
    vector_hits = [_hit_from_row(chunk, doc, dist) for chunk, doc, dist in rows]
    tag_docs = _tagged_document_ids(session, tag_id) if tag_id is not None else None
    es_docs = tag_docs
    if time_docs is not None:
        es_docs = time_docs if es_docs is None else es_docs & time_docs
    keyword_ids = search_chunk_ids(
        query,
        knowledge_base_ids=kb_ids,
        k=k,
        kind=kind,
        document_id=document_id,
        document_ids=es_docs,
    )
    if not vector_hits and not keyword_ids:
        return []
    weak_vector = not vector_hits or vector_hits[0].score < SCORE_THRESHOLD
    if weak_vector and not keyword_ids:
        return []
    fused: dict[uuid.UUID, float] = {}
    for rank, hit in enumerate(vector_hits, start=1):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + _rrf(rank)
    for rank, cid in enumerate(keyword_ids, start=1):
        fused[cid] = fused.get(cid, 0.0) + _rrf(rank)
    by_id = {hit.chunk_id: hit for hit in vector_hits}
    missing = [cid for cid in fused if cid not in by_id]
    by_id.update(_hits_for_ids(session, query_vec, kb_ids, user_id, missing))
    ordered_ids = sorted(fused.keys(), key=lambda cid: fused[cid], reverse=True)
    hits = [by_id[cid] for cid in ordered_ids if cid in by_id][:k]
    return _neighbor_expand(session, query, query_vec, _keep_relevant(_rerank(query, hits)))


def _keep_relevant(hits: list[SearchHit]) -> list[SearchHit]:
    floor = get_settings().relevance_min_score
    return [hit for hit in hits if hit.score >= floor]


def _rerank(query: str, hits: list[SearchHit]) -> list[SearchHit]:
    cands = hits[:RERANK_CANDIDATE_MAX]
    scores = score_documents(query, [h.content for h in cands])
    if scores is None:
        return cands
    ranked = [replace(hit, score=float(scores[i])) for i, hit in enumerate(cands)]
    ranked.sort(key=lambda h: h.score, reverse=True)
    return ranked


def _heading_blank(heading: str | None) -> bool:
    return heading is None or heading == ""


def _cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    try:
        va = [float(x) for x in a]
        vb = [float(x) for x in b]
    except (TypeError, ValueError):
        return 0.0
    if not va or not vb or len(va) != len(vb):
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    na = sum(x * x for x in va) ** 0.5
    nb = sum(y * y for y in vb) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _adjacent_chunks(siblings: list[DocumentChunk], center_id: uuid.UUID) -> list[DocumentChunk]:
    if not siblings:
        return []
    ordered = sorted(siblings, key=lambda c: c.chunk_index)
    try:
        pos = next(i for i, c in enumerate(ordered) if c.id == center_id)
    except StopIteration:
        return []
    out: list[DocumentChunk] = []
    if pos > 0:
        out.append(ordered[pos - 1])
    if pos + 1 < len(ordered):
        out.append(ordered[pos + 1])
    return out


def _join_chunks(
    must: list[DocumentChunk],
    optional: list[DocumentChunk],
    max_chars: int = SECTION_EXPAND_MAX_CHARS,
) -> str:
    selected = list(must)
    seen = {c.id for c in selected}
    total = sum(len(c.content) for c in selected)
    for chunk in sorted(optional, key=lambda c: c.chunk_index):
        if chunk.id in seen:
            continue
        if total + len(chunk.content) <= max_chars:
            selected.append(chunk)
            seen.add(chunk.id)
            total += len(chunk.content)
    selected.sort(key=lambda c: c.chunk_index)
    return "\n\n".join(c.content for c in selected)


def _join_anchor_expanded(
    anchor: DocumentChunk,
    expanded: list[DocumentChunk],
    max_chars: int = SECTION_EXPAND_MAX_CHARS,
) -> str:
    return _join_chunks([anchor], expanded, max_chars=max_chars)


def _expand_group_key(hit: SearchHit) -> tuple:
    if hit.parent_id is not None:
        return ("parent", hit.parent_id)
    if _heading_blank(hit.heading):
        return ("alone", hit.chunk_id)
    return ("heading", hit.document_id, hit.heading or "")


def _nearest_seed(neighbor: DocumentChunk, seeds: list[DocumentChunk]) -> DocumentChunk:
    return min(seeds, key=lambda s: abs(s.chunk_index - neighbor.chunk_index))


def _section_siblings(
    session: Session,
    keys: list[tuple[uuid.UUID, str]],
) -> dict[tuple[uuid.UUID, str], list[DocumentChunk]]:
    if not keys:
        return {}
    conds = [
        and_(DocumentChunk.document_id == doc_id, DocumentChunk.heading == heading)
        for doc_id, heading in keys
    ]
    rows = list(
        session.scalars(
            select(DocumentChunk).where(or_(*conds), DocumentChunk.role == "child")
        ).all()
    )
    out: dict[tuple[uuid.UUID, str], list[DocumentChunk]] = {}
    for chunk in rows:
        key = (chunk.document_id, chunk.heading or "")
        out.setdefault(key, []).append(chunk)
    for key in out:
        out[key].sort(key=lambda c: c.chunk_index)
    return out


def _chunks_by_ids(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, DocumentChunk]:
    if not ids:
        return {}
    rows = session.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ids))).all()
    return {chunk.id: chunk for chunk in rows}


def _children_of_parents(
    session: Session, parent_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[DocumentChunk]]:
    if not parent_ids:
        return {}
    rows = list(
        session.scalars(
            select(DocumentChunk).where(
                DocumentChunk.parent_id.in_(parent_ids),
                DocumentChunk.role == "child",
            )
        ).all()
    )
    out: dict[uuid.UUID, list[DocumentChunk]] = {}
    for chunk in rows:
        if chunk.parent_id is None:
            continue
        out.setdefault(chunk.parent_id, []).append(chunk)
    for pid in out:
        out[pid].sort(key=lambda c: c.chunk_index)
    return out


def _neighbor_query_scores(
    query: str,
    query_vec,
    neighbor_ids: list[uuid.UUID],
    chunk_by_id: dict[uuid.UUID, DocumentChunk],
) -> dict[uuid.UUID, float]:
    if not neighbor_ids:
        return {}
    if rerank_keys_ready():
        docs = [chunk_by_id[nid].content for nid in neighbor_ids]
        scores = score_documents(query, docs)
        if scores is not None:
            return {nid: float(sc) for nid, sc in zip(neighbor_ids, scores)}
    return {nid: _cosine(query_vec, chunk_by_id[nid].embedding) for nid in neighbor_ids}


def _neighbor_expand(
    session: Session,
    query: str,
    query_vec,
    hits: list[SearchHit],
) -> list[SearchHit]:
    """Group same-parent / same-heading hits, union ±1 neighbors, dual-filter, one hit."""
    if not hits:
        return []
    settings = get_settings()
    anchor_min = settings.expand_anchor_min
    query_min = settings.expand_query_min

    groups: dict[tuple, list[SearchHit]] = {}
    for hit in hits:
        groups.setdefault(_expand_group_key(hit), []).append(hit)

    parent_ids: list[uuid.UUID] = []
    heading_keys: list[tuple[uuid.UUID, str]] = []
    for key, group in groups.items():
        kind = key[0]
        if kind == "parent":
            parent_ids.append(key[1])  # type: ignore[arg-type]
        elif kind == "heading":
            heading_keys.append((key[1], key[2]))  # type: ignore[arg-type]

    children_by_parent = _children_of_parents(session, list(dict.fromkeys(parent_ids)))
    siblings_by_heading = _section_siblings(session, list(dict.fromkeys(heading_keys)))

    chunk_by_id: dict[uuid.UUID, DocumentChunk] = {}
    for siblings in list(children_by_parent.values()) + list(siblings_by_heading.values()):
        for chunk in siblings:
            chunk_by_id[chunk.id] = chunk

    missing_seeds = [
        h.chunk_id
        for key, group in groups.items()
        if key[0] != "alone"
        for h in group
        if h.chunk_id not in chunk_by_id
    ]
    if missing_seeds:
        chunk_by_id.update(_chunks_by_ids(session, list(dict.fromkeys(missing_seeds))))

    # Collect group-level neighbor candidates (seeds ∪ ±1, then non-seeds only).
    group_neighbors: dict[tuple, list[DocumentChunk]] = {}
    all_neighbor_ids: list[uuid.UUID] = []
    for key, group in groups.items():
        kind = key[0]
        if kind == "alone":
            group_neighbors[key] = []
            continue
        if kind == "parent":
            siblings = children_by_parent.get(key[1], [])  # type: ignore[arg-type]
        else:
            siblings = siblings_by_heading.get((key[1], key[2]), [])  # type: ignore[arg-type]
        seed_ids = {h.chunk_id for h in group}
        neighbors: dict[uuid.UUID, DocumentChunk] = {}
        for seed_id in seed_ids:
            for n in _adjacent_chunks(siblings, seed_id):
                if n.id not in seed_ids:
                    neighbors[n.id] = n
        ordered = sorted(neighbors.values(), key=lambda c: c.chunk_index)
        group_neighbors[key] = ordered
        all_neighbor_ids.extend(n.id for n in ordered)

    unique_neighbor_ids = list(dict.fromkeys(all_neighbor_ids))
    query_scores = _neighbor_query_scores(query, query_vec, unique_neighbor_ids, chunk_by_id)

    out: list[SearchHit] = []
    for key, group in groups.items():
        primary = max(group, key=lambda h: h.score)
        seed_chunks: list[DocumentChunk] = []
        for h in group:
            chunk = chunk_by_id.get(h.chunk_id)
            if chunk is not None:
                seed_chunks.append(chunk)
        seed_chunks.sort(key=lambda c: c.chunk_index)
        primary_chunk = chunk_by_id.get(primary.chunk_id)
        original = (
            primary_chunk.content
            if primary_chunk is not None
            else (primary.original_content or primary.content)
        )

        if key[0] == "alone" or not seed_chunks:
            out.append(
                replace(
                    primary,
                    content=original if primary_chunk is not None else primary.content,
                    original_content=original,
                    neighbor_chunk_ids=[],
                    expanded_chunk_ids=[],
                    seed_chunk_ids=[primary.chunk_id],
                )
            )
            continue

        # Deduplicate seeds by id while keeping chunk_index order.
        seen_seed: set[uuid.UUID] = set()
        unique_seeds: list[DocumentChunk] = []
        for chunk in seed_chunks:
            if chunk.id in seen_seed:
                continue
            seen_seed.add(chunk.id)
            unique_seeds.append(chunk)
        seed_chunks = unique_seeds

        neighbors = group_neighbors.get(key, [])
        neighbor_ids = [n.id for n in neighbors]
        expanded: list[DocumentChunk] = []
        for neighbor in neighbors:
            nearest = _nearest_seed(neighbor, seed_chunks)
            anchor_sim = _cosine(nearest.embedding, neighbor.embedding)
            q_score = query_scores.get(neighbor.id, 0.0)
            if anchor_sim >= anchor_min and q_score >= query_min:
                expanded.append(neighbor)
        expanded_ids = [c.id for c in expanded]
        seed_ids = [c.id for c in seed_chunks]
        content = _join_chunks(seed_chunks, expanded)
        out.append(
            replace(
                primary,
                content=content,
                original_content=original,
                neighbor_chunk_ids=neighbor_ids,
                expanded_chunk_ids=expanded_ids,
                seed_chunk_ids=seed_ids,
            )
        )
    out.sort(key=lambda h: h.score, reverse=True)
    return out


def _rerank_model_name() -> str:
    settings = get_settings()
    if rerank_keys_ready():
        return settings.rerank_model
    if settings.llm_api_key.strip():
        return "llm"
    return "none"


def _label_map(
    session: Session, user_id: uuid.UUID, query_norm: str, knowledge_base_id: uuid.UUID | None
) -> dict[uuid.UUID, int]:
    stmt = select(RetrievalLabel).where(
        RetrievalLabel.user_id == user_id,
        RetrievalLabel.query_norm == query_norm,
    )
    if knowledge_base_id is None:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id.is_(None))
    else:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id == knowledge_base_id)
    return {row.chunk_id: row.relevance for row in session.scalars(stmt)}


def search_debug(
    session: Session,
    query: str,
    *,
    retrieval_query: str | None = None,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    vector_k: int = DEFAULT_K,
    bm25_k: int = DEFAULT_K,
    rrf_k: int = DEFAULT_K,
    rerank_k: int = DEFAULT_K,
    vector_threshold: float = SCORE_THRESHOLD,
    rrf_k_const: int = RRF_K,
    eval_k: int = DEFAULT_K,
) -> RetrievalDebugResponse:
    require_elasticsearch_url()
    t_start = time.perf_counter()
    kb_ids = search_kb_ids(session, user_id, knowledge_base_id)
    rq = (retrieval_query or query).strip() or query
    query_norm = normalize_query(query)
    empty_stage = RetrievalStageOut(requested_k=0, actual_count=0, rows=[])
    if not kb_ids:
        return RetrievalDebugResponse(
            query=query,
            query_norm=query_norm,
            vector=empty_stage.model_copy(update={"requested_k": vector_k, "threshold": vector_threshold}),
            bm25=empty_stage.model_copy(update={"requested_k": bm25_k}),
            rrf=empty_stage.model_copy(update={"requested_k": rrf_k, "k_const": rrf_k_const, "candidate_count": 0}),
            rerank=empty_stage.model_copy(update={"requested_k": rerank_k, "model": _rerank_model_name()}),
            final=[],
            candidates=[],
            evaluation=RetrievalEvalOut(k=eval_k, relevant_chunk_count=0),
            labels={},
            timings=RetrievalTimingsOut(),
        )
    t0 = time.perf_counter()
    query_vec = embed_texts([rq])[0]
    t1 = time.perf_counter()
    rows = _vector_stmt(session, query_vec, kb_ids, user_id, None, None, None, vector_k)
    vector_hits = [_hit_from_row(chunk, doc, dist) for chunk, doc, dist in rows]
    t2 = time.perf_counter()
    bm25_pairs = search_chunk_scores(rq, knowledge_base_ids=kb_ids, k=bm25_k)
    bm25_ids = [cid for cid, _ in bm25_pairs]
    bm25_scores = {cid: score for cid, score in bm25_pairs}
    by_id = {hit.chunk_id: hit for hit in vector_hits}
    by_id.update(_hits_for_ids(session, query_vec, kb_ids, user_id, bm25_ids))
    t3 = time.perf_counter()
    vector_rank = {hit.chunk_id: i for i, hit in enumerate(vector_hits, start=1)}
    bm25_rank = {cid: i for i, cid in enumerate(bm25_ids, start=1)}
    fused: dict[uuid.UUID, float] = {}
    from_v: dict[uuid.UUID, float] = {}
    from_b: dict[uuid.UUID, float] = {}
    for rank, hit in enumerate(vector_hits, start=1):
        part = _rrf(rank, rrf_k_const)
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + part
        from_v[hit.chunk_id] = part
    for rank, cid in enumerate(bm25_ids, start=1):
        part = _rrf(rank, rrf_k_const)
        fused[cid] = fused.get(cid, 0.0) + part
        from_b[cid] = part
    rrf_ids = sorted(fused.keys(), key=lambda cid: fused[cid], reverse=True)[:rrf_k]
    rrf_hits = [by_id[cid] for cid in rrf_ids if cid in by_id]
    t4 = time.perf_counter()
    gate_fail = not vector_hits or vector_hits[0].score < vector_threshold
    rerank_in = rrf_hits[: min(rerank_k, RERANK_CANDIDATE_MAX)]
    reranked = _rerank(rq, rerank_in)
    t5 = time.perf_counter()
    kept = [] if gate_fail else _keep_relevant(reranked)
    t6 = time.perf_counter()
    kept_ids = {h.chunk_id for h in kept}
    timings = RetrievalTimingsOut(
        embed_ms=round((t1 - t0) * 1000),
        vector_ms=round((t2 - t1) * 1000),
        bm25_ms=round((t3 - t2) * 1000),
        rrf_ms=round((t4 - t3) * 1000),
        rerank_ms=round((t5 - t4) * 1000),
        final_ms=round((t6 - t5) * 1000),
        total_ms=round((t6 - t_start) * 1000),
    )

    def row_for(
        cid: uuid.UUID,
        *,
        rank: int,
        score: float,
        rrf_r: int | None = None,
        rerank_r: int | None = None,
        final: bool = False,
    ) -> RetrievalDebugRow:
        hit = by_id[cid]
        return RetrievalDebugRow(
            rank=rank,
            document_id=hit.document_id,
            document_name=hit.document_name,
            chunk_id=cid,
            score=score,
            vector_rank=vector_rank.get(cid),
            vector_score=by_id[cid].score if cid in vector_rank else None,
            bm25_rank=bm25_rank.get(cid),
            bm25_score=bm25_scores.get(cid),
            rrf_rank=rrf_r,
            rrf_score=fused.get(cid),
            rrf_from_vector=from_v.get(cid),
            rrf_from_bm25=from_b.get(cid),
            rerank_rank=rerank_r,
            rerank_score=None,
            final=final,
        )

    vector_rows = [
        row_for(h.chunk_id, rank=i, score=h.score)
        for i, h in enumerate(vector_hits, start=1)
    ]
    bm25_rows = [
        row_for(cid, rank=i, score=bm25_scores[cid])
        for i, cid in enumerate(bm25_ids, start=1)
        if cid in by_id
    ]
    rrf_rows = [
        row_for(h.chunk_id, rank=i, score=fused[h.chunk_id], rrf_r=i)
        for i, h in enumerate(rrf_hits, start=1)
    ]
    rerank_rows: list[RetrievalDebugRow] = []
    rerank_score_by_id: dict[uuid.UUID, float] = {}
    for i, h in enumerate(reranked, start=1):
        rerank_score_by_id[h.chunk_id] = h.score
        item = row_for(h.chunk_id, rank=i, score=h.score, rrf_r=None, rerank_r=i, final=h.chunk_id in kept_ids)
        item = item.model_copy(
            update={
                "rerank_score": h.score,
                "rrf_rank": next((r.rank for r in rrf_rows if r.chunk_id == h.chunk_id), None),
            }
        )
        rerank_rows.append(item)
    final_rows = [
        r.model_copy(update={"rank": i, "final": True, "score": r.rerank_score or r.score})
        for i, r in enumerate((x for x in rerank_rows if x.final), start=1)
    ]
    merged: dict[uuid.UUID, RetrievalDebugRow] = {}
    for src in vector_rows + bm25_rows + rrf_rows + rerank_rows:
        prev = merged.get(src.chunk_id)
        if prev is None:
            merged[src.chunk_id] = src
        else:
            merged[src.chunk_id] = prev.model_copy(
                update={
                    "vector_rank": prev.vector_rank or src.vector_rank,
                    "vector_score": prev.vector_score if prev.vector_score is not None else src.vector_score,
                    "bm25_rank": prev.bm25_rank or src.bm25_rank,
                    "bm25_score": prev.bm25_score if prev.bm25_score is not None else src.bm25_score,
                    "rrf_rank": prev.rrf_rank or src.rrf_rank,
                    "rrf_score": prev.rrf_score if prev.rrf_score is not None else src.rrf_score,
                    "rrf_from_vector": prev.rrf_from_vector if prev.rrf_from_vector is not None else src.rrf_from_vector,
                    "rrf_from_bm25": prev.rrf_from_bm25 if prev.rrf_from_bm25 is not None else src.rrf_from_bm25,
                    "rerank_rank": prev.rerank_rank or src.rerank_rank,
                    "rerank_score": prev.rerank_score if prev.rerank_score is not None else src.rerank_score,
                    "final": prev.final or src.final,
                }
            )
    ordered = sorted(
        merged.values(),
        key=lambda r: (
            0 if r.final else 1,
            r.rerank_rank or 999,
            r.rrf_rank or 999,
            r.vector_rank or 999,
        ),
    )
    candidates = [r.model_copy(update={"rank": i}) for i, r in enumerate(ordered, start=1)]
    labels = _label_map(session, user_id, query_norm, knowledge_base_id)
    chunk_order: list[uuid.UUID] = [row.chunk_id for row in final_rows]
    relevant = {cid for cid, rel in labels.items() if rel >= 2}
    recall = precision = None
    if relevant:
        top = chunk_order[:eval_k]
        hit_n = sum(1 for cid in top if cid in relevant)
        precision = hit_n / eval_k
        recall = hit_n / len(relevant)
    return RetrievalDebugResponse(
        query=query,
        query_norm=query_norm,
        vector=RetrievalStageOut(
            requested_k=vector_k,
            actual_count=len(vector_rows),
            threshold=vector_threshold,
            rows=vector_rows,
        ),
        bm25=RetrievalStageOut(requested_k=bm25_k, actual_count=len(bm25_rows), rows=bm25_rows),
        rrf=RetrievalStageOut(
            requested_k=rrf_k,
            actual_count=len(rrf_rows),
            k_const=rrf_k_const,
            candidate_count=len(fused),
            rows=rrf_rows,
        ),
        rerank=RetrievalStageOut(
            requested_k=rerank_k,
            actual_count=len(rerank_rows),
            model=_rerank_model_name(),
            rows=rerank_rows,
        ),
        final=final_rows,
        candidates=candidates,
        evaluation=RetrievalEvalOut(
            k=eval_k,
            recall=recall,
            precision=precision,
            relevant_chunk_count=len(relevant),
        ),
        labels={str(k): v for k, v in labels.items()},
        timings=timings,
    )
