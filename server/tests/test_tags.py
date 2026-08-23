import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import DocumentTag


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def test_tag_assign_filter_delete_and_duplicate_name():
    with _client() as client:
        doc = client.post(
            "/api/documents/notes",
            json={"content": f"tagged note {uuid.uuid4()}", "filename": "t.md"},
        )
        assert doc.status_code == 200
        doc_id = doc.json()["id"]
        other = client.post(
            "/api/documents/notes",
            json={"content": f"other note {uuid.uuid4()}", "filename": "o.md"},
        )
        other_id = other.json()["id"]
        created = client.post("/api/tags", json={"name": f"主题-{uuid.uuid4().hex[:8]}"})
        assert created.status_code == 201
        tag_id = created.json()["id"]
        dup = client.post("/api/tags", json={"name": created.json()["name"]})
        assert dup.status_code == 409
        put = client.put(f"/api/documents/{doc_id}/tags", json={"tag_ids": [tag_id]})
        assert put.status_code == 200
        filtered = client.get("/api/documents", params={"tag_id": tag_id})
        assert filtered.status_code == 200
        ids = {item["id"] for item in filtered.json()}
        assert doc_id in ids
        assert other_id not in ids
        gone = client.delete(f"/api/tags/{tag_id}")
        assert gone.status_code == 200
        empty = client.get("/api/documents", params={"tag_id": tag_id})
        assert empty.json() == []
        session = session_scope()
        try:
            n = session.scalar(
                select(func.count()).select_from(DocumentTag).where(DocumentTag.tag_id == uuid.UUID(tag_id))
            )
            assert n == 0
        finally:
            session.close()
    reset_app_state()
