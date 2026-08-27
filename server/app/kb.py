from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, KnowledgeBase

DEFAULT_KB_NAME = "默认知识库"


class KnowledgeBaseAccessError(LookupError):
    pass


def ensure_default_knowledge_base(session: Session, user_id: uuid.UUID) -> KnowledgeBase:
    rows = list(session.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)))
    defaults = [row for row in rows if row.is_default]
    if len(defaults) > 1:
        for extra in defaults[1:]:
            extra.is_default = False
        session.commit()
        defaults = [defaults[0]]
    if not rows:
        kb = KnowledgeBase(user_id=user_id, name=DEFAULT_KB_NAME, is_default=True)
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


def resolve_knowledge_base_id(
    session: Session,
    knowledge_base_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> uuid.UUID:
    if knowledge_base_id is not None:
        kb = session.get(KnowledgeBase, knowledge_base_id)
        if kb is None or kb.user_id != user_id:
            raise KnowledgeBaseAccessError("知识库不存在")
        return kb.id
    return ensure_default_knowledge_base(session, user_id).id


def search_kb_ids(
    session: Session,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    if knowledge_base_id is not None:
        return [resolve_knowledge_base_id(session, knowledge_base_id, user_id)]
    return list(
        session.scalars(
            select(KnowledgeBase.id).where(KnowledgeBase.user_id == user_id, KnowledgeBase.is_enabled.is_(True))
        ).all()
    )


def owned_document(session: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
    doc = session.get(Document, document_id)
    if doc is None:
        return None
    kb = session.get(KnowledgeBase, doc.knowledge_base_id)
    if kb is None or kb.user_id != user_id:
        return None
    return doc


def default_knowledge_base_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.is_default)) or 0
