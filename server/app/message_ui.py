"""对话消息 UI 载荷：方案页/HITL/预订等随消息落库，刷新后可回放。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Message, PlanRecord
from app.schemas import MessageOut


def pack_assistant_citations(
    cites: list[dict[str, Any]] | None,
    *,
    plan_html: dict[str, Any] | None = None,
    travel_data: dict[str, Any] | None = None,
    pending_action: dict[str, Any] | None = None,
    bookings: list[dict[str, Any]] | None = None,
) -> list | dict | None:
    """无扩展载荷时保持 citations 为 list；有则包成 envelope。"""
    items = list(cites or [])
    plan = dict(plan_html or {}) if plan_html else {}
    travel = dict(travel_data or {}) if travel_data else {}
    pending = dict(pending_action) if isinstance(pending_action, dict) else None
    book_items = [dict(x) for x in bookings if isinstance(x, dict)] if isinstance(bookings, list) else []
    # 空 plan_html 不落库
    if plan and not (plan.get("html") or plan.get("url") or plan.get("key")):
        plan = {}
    if not plan and not travel and not pending and not book_items:
        return items or None
    out: dict[str, Any] = {"citations": items}
    if plan:
        # 落库保留回放所需字段；html 可能较大但本机知识库可接受
        slim = {k: plan[k] for k in ("html", "url", "key", "note", "plan_id") if k in plan and plan[k] is not None}
        if slim:
            out["plan_html"] = slim
    if travel:
        out["travel_data"] = travel
    if pending:
        out["pending_action"] = pending
    if book_items:
        out["bookings"] = book_items
    return out


def message_to_out(row: Message) -> MessageOut:
    raw = row.citations
    cites: list | dict | None = raw
    plan_html = None
    travel = None
    pending_action = None
    bookings = None
    if isinstance(raw, dict) and (
        "plan_html" in raw
        or "travel_data" in raw
        or "citations" in raw
        or "pending_action" in raw
        or "bookings" in raw
    ):
        inner = raw.get("citations")
        cites = inner if isinstance(inner, list) else (inner if inner is None else [])
        ph = raw.get("plan_html")
        plan_html = ph if isinstance(ph, dict) else None
        td = raw.get("travel_data")
        travel = td if isinstance(td, dict) else None
        pa = raw.get("pending_action")
        pending_action = pa if isinstance(pa, dict) else None
        bk = raw.get("bookings")
        bookings = [x for x in bk if isinstance(x, dict)] if isinstance(bk, list) else None
    return MessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        citations=cites,
        plan_html=plan_html,
        travel=travel,
        pending_action=pending_action,
        bookings=bookings,
    )


def mark_prior_hitl_resolved(
    session: Session,
    conversation_id: uuid.UUID,
    *,
    confirmed: bool,
) -> None:
    """HITL 确认/拒绝后，把同会话最近一条未决 pending_action 标成已处理，刷新不再出黄框。"""
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
    ).all()
    for row in rows:
        raw = row.citations
        if not isinstance(raw, dict):
            continue
        pa = raw.get("pending_action")
        if not isinstance(pa, dict) or pa.get("confirmed") is not None:
            continue
        row.citations = {**raw, "pending_action": {**pa, "confirmed": confirmed}}
        flag_modified(row, "citations")
        break


def hydrate_plan_html_from_records(
    session: Session,
    conversation_id: uuid.UUID,
    rows: list[MessageOut],
) -> list[MessageOut]:
    """兼容旧消息：未落 plan_html 时，用同会话 plan_record 补到最后一条助手消息。"""
    if any(m.plan_html for m in rows):
        return rows
    plans = list(
        session.scalars(
            select(PlanRecord)
            .where(PlanRecord.conversation_id == conversation_id)
            .order_by(PlanRecord.created_at.asc())
        ).all()
    )
    if not plans:
        return rows
    last_idx = max((i for i, m in enumerate(rows) if m.role == "assistant"), default=-1)
    if last_idx < 0:
        return rows
    p = plans[-1]
    if not (p.url or p.minio_key):
        return rows
    patched = rows[last_idx].model_copy(
        update={
            "plan_html": {
                "html": None,
                "url": p.url,
                "key": p.minio_key,
                "note": "历史方案（来自行程单）",
                "plan_id": str(p.id),
            }
        }
    )
    out = list(rows)
    out[last_idx] = patched
    return out
