from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.index import STATUS_READY, embed_texts
from app.kb import resolve_knowledge_base_id
from app.models import Document, DocumentChunk, DocumentTag

SCORE_THRESHOLD = 0.30
DEFAULT_K = 5


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


def search_chunks(
    session: Session,
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    kind: str | None = None,
    k: int = DEFAULT_K,
) -> list[SearchHit]:
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20")
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
    stmt = stmt.order_by(distance).limit(k)
    rows = session.execute(stmt).all()
    hits = [
        SearchHit(
            document_id=doc.id,
            document_name=doc.filename,
            chunk_id=chunk.id,
            content=chunk.content,
            score=_similarity(dist),
            page=chunk.page,
            heading=chunk.heading,
            kind=doc.kind,
        )
        for chunk, doc, dist in rows
    ]
    if not hits or hits[0].score < SCORE_THRESHOLD:
        return []
    return hits
