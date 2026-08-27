import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import session_scope
from app.models import Entity, EntityLink, KnowledgeBase
from app.user import ensure_default_user


def test_entity_link_same_kb_and_reject_missing_fk():
    session = session_scope()
    try:
        uid = ensure_default_user(session).id
        kb = KnowledgeBase(user_id=uid, name=f"图谱-{uuid.uuid4().hex[:8]}", is_default=False)
        session.add(kb)
        session.flush()
        src = Entity(knowledge_base_id=kb.id, name="LangChain", type="tool")
        dst = Entity(knowledge_base_id=kb.id, name="RAG", type="concept")
        session.add_all([src, dst])
        session.flush()
        session.add(EntityLink(from_id=src.id, to_id=dst.id, rel="用于"))
        session.commit()

        session.add(Entity(knowledge_base_id=uuid.uuid4(), name="幽灵", type="concept"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(EntityLink(from_id=uuid.uuid4(), to_id=dst.id, rel="假边"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()
