"""本人行程方案列表（工具 → 我的行程单）。身份仅来自 Session。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.models import PlanRecord, User
from app.schemas import PlanRecordOut

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _out(r: PlanRecord) -> PlanRecordOut:
    return PlanRecordOut(
        id=r.id,
        title=r.title,
        origin=r.origin,
        destination=r.destination,
        depart_date=r.depart_date,
        trip_type=r.trip_type or "other",
        nights=r.nights,
        conversation_id=r.conversation_id,
        url=r.url,
        minio_key=r.minio_key,
        created_at=r.created_at,
    )


@router.get("", response_model=list[PlanRecordOut])
def list_plans(session: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = session.scalars(
        select(PlanRecord)
        .where(PlanRecord.user_id == user.id)
        .order_by(PlanRecord.created_at.desc())
        .limit(100)
    ).all()
    return [_out(r) for r in rows]


@router.get("/{plan_id}", response_model=PlanRecordOut)
def get_plan(
    plan_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    row = session.get(PlanRecord, plan_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="行程单不存在")
    return _out(row)
