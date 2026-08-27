from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import User
from app.user import DEFAULT_USER_NAME, ensure_default_user


def _wipe_users() -> None:
    session = session_scope()
    try:
        session.execute(delete(User))
        session.commit()
    finally:
        session.close()


def _count() -> int:
    session = session_scope()
    try:
        return session.scalar(select(func.count()).select_from(User)) or 0
    finally:
        session.close()


def test_ensure_default_user_once_then_idempotent():
    reset_app_state()
    get_settings(load_file=True)
    _wipe_users()
    session = session_scope()
    try:
        first = ensure_default_user(session)
        second = ensure_default_user(session)
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert first.username == DEFAULT_USER_NAME
        assert session.scalar(select(func.count()).select_from(User)) == 1
    finally:
        session.close()
    reset_app_state()


def test_recreate_after_delete_via_lifespan_and_me():
    reset_app_state()
    get_settings(load_file=True)
    _wipe_users()
    assert _count() == 0
    with TestClient(create_app(load_file=True, ensure_default=True)) as client:
        assert _count() == 1
        denied = client.get("/api/auth/me")
        assert denied.status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"username": DEFAULT_USER_NAME, "password": get_settings().initial_password},
        )
        assert login.status_code == 200
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == DEFAULT_USER_NAME
        assert body["id"]
    reset_app_state()
