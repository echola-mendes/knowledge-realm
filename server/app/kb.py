from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgeBase

DEFAULT_KB_NAME = "默认知识库"


def ensure_default_knowledge_base(session: Session) -> KnowledgeBase:
    rows = list(session.scalars(select(KnowledgeBase)))
    defaults = [row for row in rows if row.is_default]
    if len(defaults) > 1:
        for extra in defaults[1:]:
            extra.is_default = False
        session.commit()
        defaults = [defaults[0]]
    if not rows:
        kb = KnowledgeBase(name=DEFAULT_KB_NAME, is_default=True)
        session.add(kb)
        session.commit()
        session.refresh(kb)
        return kb
    if defaults:
        return defaults[0]
    rows[0].is_default = True
    session.commit()
    session.refresh(rows[0])
    return rows[0]


def resolve_knowledge_base_id(session: Session, knowledge_base_id: uuid.UUID | None) -> uuid.UUID:
    if knowledge_base_id is not None:
        return knowledge_base_id
    return ensure_default_knowledge_base(session).id


def default_knowledge_base_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.is_default)) or 0
