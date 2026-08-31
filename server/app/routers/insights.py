from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.insights import analyze_conflicts, analyze_gaps, organize_kb, weak_queries
from app.llm import llm_keys_ready
from app.models import Document, KnowledgeBase, User
from app.schemas import ConflictReport, GapReport, OrganizeBody, OrganizeReport

router = APIRouter(prefix="/api/knowledge-bases", tags=["insights"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _owned_kb(session: Session, kb_id: uuid.UUID, user_id: uuid.UUID) -> KnowledgeBase:
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None or kb.user_id != user_id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.post("/{kb_id}/insights/conflicts", response_model=ConflictReport)
def run_conflicts(
    kb_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _owned_kb(session, kb_id, user.id)
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    docs = list(
        session.scalars(
            select(Document)
            .where(Document.knowledge_base_id == kb_id, Document.status == "ready")
            .order_by(Document.created_at.desc())
        ).all()
    )
    result = analyze_conflicts(docs)
    items = [
        {
            "documents": c.get("documents", []),
            "point": c.get("point", ""),
            "detail": c.get("detail", ""),
            "suggestion": c.get("suggestion", ""),
        }
        for c in result.get("conflicts", [])
    ]
    return ConflictReport(conflicts=items, truncated=result.get("truncated", False))


@router.post("/{kb_id}/insights/gaps", response_model=GapReport)
def run_gaps(
    kb_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _owned_kb(session, kb_id, user.id)
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    docs = list(
        session.scalars(
            select(Document)
            .where(Document.knowledge_base_id == kb_id, Document.status == "ready")
            .order_by(Document.created_at.desc())
        ).all()
    )
    result = analyze_gaps(docs, weak_queries(session, user.id))
    items = [
        {
            "topic": g.get("topic", ""),
            "evidence": g.get("evidence", ""),
            "suggestion": g.get("suggestion", ""),
        }
        for g in result.get("gaps", [])
    ]
    return GapReport(
        covered_topics=result.get("covered_topics", []),
        gaps=items,
        truncated=result.get("truncated", False),
    )


@router.post("/{kb_id}/insights/organize", response_model=OrganizeReport)
def run_organize(
    kb_id: uuid.UUID,
    body: OrganizeBody = OrganizeBody(),
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    kb = _owned_kb(session, kb_id, user.id)
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    result = organize_kb(session, kb, apply_tags=body.apply_tags)
    return OrganizeReport(
        applied=result.get("applied", []),
        applied_tags=result.get("applied_tags", False),
        duplicates=result.get("duplicates", []),
        empty_summary=result.get("empty_summary", []),
        bad_names=result.get("bad_names", []),
        untagged_total=result.get("untagged_total", 0),
    )

