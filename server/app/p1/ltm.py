from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserMemory

LTM_LIMIT = 20


def load_ltm_hits(session: Session, user_id: uuid.UUID, *, limit: int = LTM_LIMIT) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.updated_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {"id": str(row.id), "kind": row.kind, "content": row.content}
        for row in rows
        if row.content
    ]


def write_user_memory(session: Session, user_id: uuid.UUID, kind: str, content: str) -> UserMemory:
    kind = kind.strip()
    text = content.strip()
    if not kind or not text:
        raise ValueError("kind and content required")
    row = UserMemory(user_id=user_id, kind=kind[:50], content=text)
    session.add(row)
    session.flush()
    return row
