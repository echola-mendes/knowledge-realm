import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Favorite


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def test_favorite_list_idempotent_unfavorite_and_delete_clears_row():
    with _client() as client:
        a = client.post(
            "/api/documents/notes",
            json={"content": f"fav a {uuid.uuid4()}", "filename": "a.md"},
        )
        b = client.post(
            "/api/documents/notes",
            json={"content": f"fav b {uuid.uuid4()}", "filename": "b.md"},
        )
        a_id = a.json()["id"]
        b_id = b.json()["id"]
        first = client.post(f"/api/documents/{a_id}/favorite")
        second = client.post(f"/api/documents/{a_id}/favorite")
        assert first.status_code == 200
        assert second.status_code == 200
        listed = client.get("/api/documents", params={"favorite": "true"})
        ids = {item["id"] for item in listed.json()}
        assert a_id in ids
        assert b_id not in ids
        session = session_scope()
        try:
            n = session.scalar(
                select(func.count()).select_from(Favorite).where(Favorite.document_id == uuid.UUID(a_id))
            )
            assert n == 1
        finally:
            session.close()
        client.delete(f"/api/documents/{a_id}/favorite")
        empty = client.get("/api/documents", params={"favorite": "true"})
        assert empty.json() == []
        client.post(f"/api/documents/{b_id}/favorite")
        client.delete(f"/api/documents/{b_id}")
        session = session_scope()
        try:
            left = session.scalar(
                select(func.count()).select_from(Favorite).where(Favorite.document_id == uuid.UUID(b_id))
            )
            assert left == 0
        finally:
            session.close()
    reset_app_state()
