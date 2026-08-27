from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import index as index_mod
from app.deps import current_user, get_db
from app.kb import KnowledgeBaseAccessError
from app.models import Document, KnowledgeBase, RetrievalLabel, User
from app.schemas import (
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    RetrievalLabelOut,
    RetrievalLabelPut,
)
from app.search import normalize_query, search_debug

router = APIRouter(prefix="/api", tags=["retrieval-debug"])


@router.post("/retrieval-debug", response_model=RetrievalDebugResponse)
def retrieval_debug_api(
    body: RetrievalDebugRequest,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    try:
        return search_debug(
            session,
            body.query,
            user_id=user.id,
            knowledge_base_id=body.knowledge_base_id,
            vector_k=body.vector_k,
            bm25_k=body.bm25_k,
            rrf_k=body.rrf_k,
            rerank_k=body.rerank_k,
            vector_threshold=body.vector_threshold,
            rrf_k_const=body.rrf_k_const,
            eval_k=body.eval_k,
        )
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/retrieval-debug/labels", response_model=list[RetrievalLabelOut])
def list_labels(
    query: str = Query(min_length=1),
    knowledge_base_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    qn = normalize_query(query)
    stmt = select(RetrievalLabel).where(
        RetrievalLabel.user_id == user.id,
        RetrievalLabel.query_norm == qn,
    )
    if knowledge_base_id is None:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id.is_(None))
    else:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id == knowledge_base_id)
    return [
        RetrievalLabelOut(document_id=row.document_id, relevance=row.relevance)
        for row in session.scalars(stmt)
    ]


@router.put("/retrieval-debug/labels", response_model=RetrievalLabelOut)
def put_label(
    body: RetrievalLabelPut,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = session.get(Document, body.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    kb = session.get(KnowledgeBase, doc.knowledge_base_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    if body.knowledge_base_id is not None and body.knowledge_base_id != doc.knowledge_base_id:
        raise HTTPException(status_code=400, detail="文档不属于该知识库")
    qn = normalize_query(body.query)
    stmt = select(RetrievalLabel).where(
        RetrievalLabel.user_id == user.id,
        RetrievalLabel.query_norm == qn,
        RetrievalLabel.document_id == body.document_id,
    )
    if body.knowledge_base_id is None:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id.is_(None))
    else:
        stmt = stmt.where(RetrievalLabel.knowledge_base_id == body.knowledge_base_id)
    row = session.scalars(stmt).first()
    if row is None:
        row = RetrievalLabel(
            user_id=user.id,
            query_norm=qn,
            knowledge_base_id=body.knowledge_base_id,
            document_id=body.document_id,
            relevance=body.relevance,
        )
        session.add(row)
    else:
        row.relevance = body.relevance
    session.commit()
    session.refresh(row)
    return RetrievalLabelOut(document_id=row.document_id, relevance=row.relevance)
