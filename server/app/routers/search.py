from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import index as index_mod
from app.deps import current_user
from app.kb import KnowledgeBaseAccessError
from app.models import Document, DocumentTag, KnowledgeBase, Tag, User
from app.routers.documents import get_db
from app.schemas import SearchHitOut, SearchRequest
from app.rag.search import SearchHit, search_chunks

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=list[SearchHitOut])
def search_api(
    body: SearchRequest, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    try:
        hits = search_chunks(
            session,
            body.query,
            user_id=user.id,
            knowledge_base_id=body.knowledge_base_id,
            tag_id=body.tag_id,
            kind=body.kind,
            k=body.k,
            created_after=body.created_after,
            created_before=body.created_before,
        )
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_to_out(session, h) for h in hits]


def _to_out(session: Session, h: SearchHit) -> SearchHitOut:
    doc_row = session.execute(
        select(Document.created_at, KnowledgeBase.name)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(Document.id == h.document_id)
    ).first()
    tag_names = session.execute(
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == h.document_id)
        .order_by(Tag.name)
    ).scalars().all()
    return SearchHitOut(
        document_id=h.document_id,
        document_name=h.document_name,
        chunk_id=h.chunk_id,
        content=h.content,
        score=h.score,
        page=h.page,
        heading=h.heading,
        kind=h.kind,
        knowledge_base_name=doc_row[1] if doc_row else None,
        created_at=doc_row[0] if doc_row else None,
        tags=list(tag_names),
    )
