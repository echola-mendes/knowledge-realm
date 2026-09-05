"""决策审计查询 API（docs/Trace.md §7）。Session 鉴权，仅本人数据。"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user
from app.models import DecisionRun, DecisionSpan, Message, User
from app.routers.documents import get_db
from app.schemas import DecisionRunDetail, DecisionRunOut

router = APIRouter(prefix="/api", tags=["decisions"])


def _owned_run(session: Session, run_id: uuid.UUID, user_id: uuid.UUID) -> DecisionRun:
    run = session.get(DecisionRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="决策链不存在")
    return run


@router.get("/decisions", response_model=list[DecisionRunOut])
def list_decisions(
    conversation_id: uuid.UUID | None = None,
    mode: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(DecisionRun).where(DecisionRun.user_id == user.id)
    if conversation_id is not None:
        stmt = stmt.where(DecisionRun.conversation_id == conversation_id)
    if mode:
        stmt = stmt.where(DecisionRun.mode == mode)
    if status:
        stmt = stmt.where(DecisionRun.status == status)
    if start is not None:
        stmt = stmt.where(DecisionRun.created_at >= start)
    if end is not None:
        stmt = stmt.where(DecisionRun.created_at <= end)
    stmt = stmt.order_by(DecisionRun.created_at.desc()).limit(limit).offset(offset)
    return session.scalars(stmt).all()


@router.get("/decisions/{run_id}", response_model=DecisionRunDetail)
def get_decision(
    run_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    run = _owned_run(session, run_id, user.id)
    spans = session.scalars(
        select(DecisionSpan).where(DecisionSpan.run_id == run.id).order_by(DecisionSpan.seq)
    ).all()
    return DecisionRunDetail(
        id=run.id,
        message_id=run.message_id,
        conversation_id=run.conversation_id,
        mode=run.mode,
        query=run.query,
        status=run.status,
        created_at=run.created_at,
        spans=spans,
    )


@router.get("/messages/{message_id}/decision", response_model=DecisionRunDetail)
def get_message_decision(
    message_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    msg = session.get(Message, message_id)
    if msg is None or msg.conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="消息不存在")
    run = session.scalar(select(DecisionRun).where(DecisionRun.message_id == message_id))
    if run is None:
        raise HTTPException(status_code=404, detail="该消息没有决策链")
    spans = session.scalars(
        select(DecisionSpan).where(DecisionSpan.run_id == run.id).order_by(DecisionSpan.seq)
    ).all()
    return DecisionRunDetail(
        id=run.id,
        message_id=run.message_id,
        conversation_id=run.conversation_id,
        mode=run.mode,
        query=run.query,
        status=run.status,
        created_at=run.created_at,
        spans=spans,
    )
