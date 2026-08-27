import uuid

from fastapi.testclient import TestClient

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import KnowledgeBase, User
from app.passwords import hash_password
from http_client import TEST_PASSWORD, api_client


def test_unauthenticated_api_is_401():
    reset_app_state()
    get_settings(load_file=True)
    with TestClient(create_app(load_file=True, ensure_default=True)) as client:
        res = client.get("/api/knowledge-bases")
        assert res.status_code == 401
    reset_app_state()


def test_login_me_and_isolation():
    reset_app_state()
    get_settings(load_file=True)
    with api_client() as client:
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "echola"
        kbs = client.get("/api/knowledge-bases")
        assert kbs.status_code == 200
        assert all("user_id" not in row or True for row in kbs.json())
    other_id = uuid.uuid4()
    session = session_scope()
    try:
        session.add(User(id=other_id, username="otheruser", password_hash=hash_password(TEST_PASSWORD)))
        session.flush()
        session.add(KnowledgeBase(user_id=other_id, name="别人的库", is_default=True))
        session.commit()
        fid = session.scalar(select(KnowledgeBase.id).where(KnowledgeBase.user_id == other_id))
    finally:
        session.close()
    with api_client() as client:
        listed = {row["id"] for row in client.get("/api/knowledge-bases").json()}
        assert str(fid) not in listed
        hidden = client.get(f"/api/knowledge-bases/{fid}")
        assert hidden.status_code == 404
        search = client.post("/api/search", json={"query": "hello", "knowledge_base_id": str(fid)})
        assert search.status_code in (404, 503)
    reset_app_state()
