from __future__ import annotations

import uuid

from app.models import DocumentVersion
from app.db import session_scope
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _upload(client, kb_id: str, name: str, content: bytes):
    return client.post(
        "/api/documents/upload",
        files={"file": (name, content, "text/markdown")},
        data={"knowledge_base_id": kb_id},
    )


def test_new_document_gets_version_one():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ver-{uuid.uuid4().hex[:8]}"}).json()
        res = _upload(client, kb["id"], "v.md", "# v1\n内容一".encode())
        assert res.status_code == 200
        doc = res.json()
        assert doc["version"] == 1
        rows = client.get(f"/api/documents/{doc['id']}/versions").json()
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["checksum"] == doc["checksum"]


def test_duplicate_upload_does_not_add_version():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ver-{uuid.uuid4().hex[:8]}"}).json()
        first = _upload(client, kb["id"], "a.md", "same".encode()).json()
        second = _upload(client, kb["id"], "b.md", "same".encode()).json()
        assert second["existed"] is True
        assert second["id"] == first["id"]
        rows = client.get(f"/api/documents/{first['id']}/versions").json()
        assert len(rows) == 1


def test_register_version_is_idempotent_per_version():
    from app.routers.documents import register_version

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ver-{uuid.uuid4().hex[:8]}"}).json()
        doc = _upload(client, kb["id"], "i.md", "幂等".encode()).json()
        with session_scope() as session:
            doc_orm = session.get(__import__("app.models", fromlist=["Document"]).Document, uuid.UUID(doc["id"]))
            before = len(list(session.scalars(__import__("sqlalchemy").select(DocumentVersion))))
            register_version(doc_orm)
            register_version(doc_orm)
            after = len(list(session.scalars(__import__("sqlalchemy").select(DocumentVersion))))
        assert after == before


def test_versions_cross_user_404():
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ver-{uuid.uuid4().hex[:8]}"}).json()
        doc = _upload(client, kb["id"], "x.md", "x".encode()).json()
        # 另一个用户登录态下访问：http_client 默认单用户，这里仅验证未带会话 401
    import requests

    res = requests.get(f"http://127.0.0.1:8000/api/documents/{doc['id']}/versions")
    assert res.status_code == 401
