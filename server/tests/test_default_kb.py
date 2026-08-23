from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import reset_engine, session_scope
from app.kb import DEFAULT_KB_NAME, ensure_default_knowledge_base
from app.main import create_app, reset_app_state
from app.models import KnowledgeBase


def _wipe_kbs() -> None:
    session = session_scope()
    try:
        session.execute(delete(KnowledgeBase))
        session.commit()
    finally:
        session.close()


def _count() -> int:
    session = session_scope()
    try:
        return session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
    finally:
        session.close()


def test_ensure_default_once_then_idempotent():
    reset_app_state()
    get_settings(load_file=True)
    _wipe_kbs()
    session = session_scope()
    try:
        first = ensure_default_knowledge_base(session)
        second = ensure_default_knowledge_base(session)
        assert first.id == second.id
        assert first.name == DEFAULT_KB_NAME
        assert first.is_default is True
        assert session.scalar(select(func.count()).select_from(KnowledgeBase)) == 1
    finally:
        session.close()
    reset_app_state()


def test_recreate_after_delete_via_lifespan():
    reset_app_state()
    get_settings(load_file=True)
    _wipe_kbs()
    assert _count() == 0
    with TestClient(create_app(load_file=True, ensure_default=True)):
        assert _count() == 1
        session = session_scope()
        try:
            kb = session.scalar(select(KnowledgeBase))
            assert kb is not None
            assert kb.name == DEFAULT_KB_NAME
            assert kb.is_default is True
        finally:
            session.close()
    reset_app_state()
