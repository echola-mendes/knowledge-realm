from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.es_bm25 import require_elasticsearch_url, search_chunk_ids
from app.index import STATUS_READY, embed_texts
from app.kb import resolve_knowledge_base_id
from app.models import Document, DocumentChunk, DocumentTag
from app.rerank import RERANK_CANDIDATE_MAX, score_documents

SCORE_THRESHOLD = 0.30
DEFAULT_K = 5
RRF_K = 60


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


def _similarity(distance: float) -> float:
    return 1.0 - float(distance)


def _rrf(rank: int) -> float:
    return 1.0 / (RRF_K + rank)


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
    )


def _tagged_document_ids(session: Session, tag_id: uuid.UUID) -> frozenset[uuid.UUID]:
    rows = session.scalars(select(DocumentTag.document_id).where(DocumentTag.tag_id == tag_id)).all()
    return frozenset(rows)


def search_chunks(
    session: Session,
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    k: int = DEFAULT_K,
) -> list[SearchHit]:
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20")
    require_elasticsearch_url()
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    query_vec = embed_texts([query])[0]
    distance = DocumentChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(DocumentChunk, Document, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.knowledge_base_id == kb_id, Document.status == STATUS_READY)
    )
    if tag_id is not None:
        stmt = stmt.join(DocumentTag, DocumentTag.document_id == Document.id).where(DocumentTag.tag_id == tag_id)
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    if document_id is not None:
        stmt = stmt.where(Document.id == document_id)
    stmt = stmt.order_by(distance).limit(k)
    rows = session.execute(stmt).all()
    vector_hits = [_hit_from_row(chunk, doc, dist) for chunk, doc, dist in rows]
    if not vector_hits or vector_hits[0].score < SCORE_THRESHOLD:
        return []
    tag_docs = _tagged_document_ids(session, tag_id) if tag_id is not None else None
    keyword_ids = search_chunk_ids(
        query,
        knowledge_base_id=kb_id,
        k=k,
        kind=kind,
        document_id=document_id,
        document_ids=tag_docs,
    )
    fused: dict[uuid.UUID, float] = {}
    for rank, hit in enumerate(vector_hits, start=1):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + _rrf(rank)
    for rank, cid in enumerate(keyword_ids, start=1):
        fused[cid] = fused.get(cid, 0.0) + _rrf(rank)
    by_id = {hit.chunk_id: hit for hit in vector_hits}
    missing = [cid for cid in fused if cid not in by_id]
    if missing:
        dist = DocumentChunk.embedding.cosine_distance(query_vec)
        extra = session.execute(
            select(DocumentChunk, Document, dist)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(missing), Document.status == STATUS_READY)
        ).all()
        for chunk, doc, d in extra:
            by_id[chunk.id] = _hit_from_row(chunk, doc, d)
    ordered_ids = sorted(fused.keys(), key=lambda cid: fused[cid], reverse=True)
    hits = [by_id[cid] for cid in ordered_ids if cid in by_id][:k]
    return _keep_relevant(_rerank(query, hits))


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
