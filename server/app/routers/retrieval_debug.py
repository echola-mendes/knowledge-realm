from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import index as index_mod
from app import llm as llm_mod
from app.deps import current_user, get_db
from app.kb import KnowledgeBaseAccessError
from app.models import Document, DocumentChunk, KnowledgeBase, RagEvalCase, RetrievalLabel, User
from app.p1.graph import plan_agent_search
from app.schemas import (
    AnswerQualityOut,
    AnswerQualityRequest,
    DebugDatasetChunkOut,
    RagEvalCaseOut,
    RagEvalCasePut,
    RagMetricsOut,
    RagMetricsRequest,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    RetrievalLabelOut,
    RetrievalLabelPut,
    RetrievalTimingsOut,
)
from app.quality import judge_answer, judge_keys_ready
from app.rag_eval import compute_rag_metrics, keys_ready as rag_eval_keys_ready
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
    plan_ms = 0
    if llm_mod.llm_keys_ready():
        t_plan = time.perf_counter()
        plan = plan_agent_search(original)
        plan_ms = round((time.perf_counter() - t_plan) * 1000)
        next_action = str(plan.get("next_action") or "generate")
        rewritten = str(plan.get("search_query") or "").strip()
        if next_action in ("search", "rag") and rewritten:
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
        timings = (result.timings or RetrievalTimingsOut()).model_copy(update={"plan_ms": plan_ms})
        return result.model_copy(
            update={
                "search_query": search_query,
                "next_action": "search" if next_action in ("search", "rag") else "generate",
                "timings": timings,
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


@router.get("/retrieval-debug/eval-cases", response_model=RagEvalCaseOut)
def get_eval_case(
    query: str = Query(min_length=1),
    knowledge_base_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    qn = normalize_query(query)
    stmt = select(RagEvalCase).where(
        RagEvalCase.user_id == user.id,
        RagEvalCase.query_norm == qn,
    )
    if knowledge_base_id is None:
        stmt = stmt.where(RagEvalCase.knowledge_base_id.is_(None))
    else:
        stmt = stmt.where(RagEvalCase.knowledge_base_id == knowledge_base_id)
    row = session.scalars(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="评测用例不存在")
    return RagEvalCaseOut(
        query_norm=row.query_norm,
        knowledge_base_id=row.knowledge_base_id,
        gt_answer=row.gt_answer,
    )


@router.put("/retrieval-debug/eval-cases", response_model=RagEvalCaseOut)
def put_eval_case(
    body: RagEvalCasePut,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if body.knowledge_base_id is not None:
        kb = session.get(KnowledgeBase, body.knowledge_base_id)
        if kb is None or kb.user_id != user.id:
            raise HTTPException(status_code=404, detail="知识库不存在")
    qn = normalize_query(body.query)
    stmt = select(RagEvalCase).where(
        RagEvalCase.user_id == user.id,
        RagEvalCase.query_norm == qn,
    )
    if body.knowledge_base_id is None:
        stmt = stmt.where(RagEvalCase.knowledge_base_id.is_(None))
    else:
        stmt = stmt.where(RagEvalCase.knowledge_base_id == body.knowledge_base_id)
    row = session.scalars(stmt).first()
    if row is None:
        row = RagEvalCase(
            user_id=user.id,
            query_norm=qn,
            knowledge_base_id=body.knowledge_base_id,
            gt_answer=body.gt_answer,
        )
        session.add(row)
    else:
        row.gt_answer = body.gt_answer
    session.commit()
    session.refresh(row)
    return RagEvalCaseOut(
        query_norm=row.query_norm,
        knowledge_base_id=row.knowledge_base_id,
        gt_answer=row.gt_answer,
    )


@router.post("/retrieval-debug/answer-quality", response_model=AnswerQualityOut)
def answer_quality_api(body: AnswerQualityRequest, user: User = Depends(current_user)):
    """调试用 LLM-as-judge：评估回答质量。不进生产问答链。"""
    if not judge_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    try:
        return AnswerQualityOut(**judge_answer(body.query, body.answer, body.contexts))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/retrieval-debug/rag-metrics", response_model=RagMetricsOut)
def rag_metrics_api(body: RagMetricsRequest, user: User = Depends(current_user)):
    """RAG 生成侧指标（0–1）。不进生产问答链。"""
    if not rag_eval_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM 或 Embedding API Key")
    try:
        return RagMetricsOut(
            **compute_rag_metrics(
                body.query,
                body.answer,
                body.contexts,
                body.gt_answer,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
