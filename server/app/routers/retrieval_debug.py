from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import index as index_mod
from app import llm as llm_mod
from app.deps import current_user, get_db
from app.kb import KnowledgeBaseAccessError
from app.models import Document, DocumentChunk, KnowledgeBase, RetrievalLabel, User
from app.p1.graph import plan_agent_search
from app.schemas import (
    DebugDatasetChunkOut,
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
    original = body.query.strip()
    next_action: str = "search"
    search_query = original
    if llm_mod.llm_keys_ready():
        plan = plan_agent_search(original)
        next_action = str(plan.get("next_action") or "generate")
        rewritten = str(plan.get("search_query") or "").strip()
        if next_action == "search" and rewritten:
            search_query = rewritten
    try:
        result = search_debug(
            session,
            original,
            retrieval_query=search_query,
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
        return result.model_copy(
            update={
                "search_query": search_query,
                "next_action": "search" if next_action == "search" else "generate",
            }
        )
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/retrieval-debug/dataset-chunks", response_model=list[DebugDatasetChunkOut])
def list_dataset_chunks(
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = session.execute(
        select(DocumentChunk, Document, KnowledgeBase)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(KnowledgeBase.user_id == user.id)
        .order_by(text("CAST(SUBSTRING(document_chunk.chunk_label FROM 7) AS INTEGER)"))
    ).all()
    out: list[DebugDatasetChunkOut] = []
    for chunk, doc, kb in rows:
        preview = chunk.content.strip().replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:80] + "…"
        out.append(
            DebugDatasetChunkOut(
                chunk_id=chunk.id,
                chunk_label=chunk.chunk_label,
                document_id=doc.id,
                document_name=doc.filename,
                knowledge_base_id=doc.knowledge_base_id,
                knowledge_base_name=kb.name,
                chunk_index=chunk.chunk_index,
                content=preview,
            )
        )
    return out


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
        RetrievalLabelOut(chunk_id=row.chunk_id, document_id=row.document_id, relevance=row.relevance)
        for row in session.scalars(stmt)
    ]


@router.put("/retrieval-debug/labels", response_model=RetrievalLabelOut)
def put_label(
    body: RetrievalLabelPut,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    chunk = session.get(DocumentChunk, body.chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="切片不存在")
    doc = session.get(Document, chunk.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="切片不存在")
    kb = session.get(KnowledgeBase, doc.knowledge_base_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="切片不存在")
    if body.knowledge_base_id is not None and body.knowledge_base_id != doc.knowledge_base_id:
        raise HTTPException(status_code=400, detail="切片不属于该知识库")
    qn = normalize_query(body.query)
    stmt = select(RetrievalLabel).where(
        RetrievalLabel.user_id == user.id,
        RetrievalLabel.query_norm == qn,
        RetrievalLabel.chunk_id == body.chunk_id,
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
            document_id=doc.id,
            chunk_id=chunk.id,
            relevance=body.relevance,
        )
        session.add(row)
    else:
        row.relevance = body.relevance
    session.commit()
    session.refresh(row)
    return RetrievalLabelOut(chunk_id=row.chunk_id, document_id=row.document_id, relevance=row.relevance)
