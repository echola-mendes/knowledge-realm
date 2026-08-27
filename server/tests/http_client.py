from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import session_scope
from app.main import create_app
from app.models import User
from app.passwords import hash_password
from app.user import ensure_default_user

TEST_PASSWORD = "pytest-isolated-password"


def api_client() -> TestClient:
    client = TestClient(create_app(load_file=True, ensure_default=True))
    username = os.environ.get("INITIAL_USERNAME", "echola")
    session = session_scope()
    try:
        ensure_default_user(session)
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = session.scalar(select(User))
        assert user is not None
        user.password_hash = hash_password(TEST_PASSWORD)
        session.commit()
        username = user.username
    finally:
        session.close()
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return client
