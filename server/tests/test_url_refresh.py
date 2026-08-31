from __future__ import annotations

import uuid

from app.db import session_scope
from app.models import Document
from sqlalchemy import select
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _make_url_doc(client, kb_id: str, url: str):
    import app.url_import as url_import

    original_fetch, original_extract = url_import.fetch_html, url_import.html_to_text
    url_import.fetch_html = lambda u: "<html/>"
    url_import.html_to_text = lambda h: "初始正文"
    try:
        res = client.post("/api/documents/url", json={"knowledge_base_id": kb_id, "url": url})
    finally:
        url_import.fetch_html, url_import.html_to_text = original_fetch, original_extract
    return res.json()


def test_refresh_changed_increments_version_and_reindexes(monkeypatch):
    import app.url_import as url_import
    from app import index as index_mod

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ref-{uuid.uuid4().hex[:8]}"}).json()
        doc = _make_url_doc(client, kb["id"], f"https://example.com/{uuid.uuid4().hex[:8]}")
        # 手工补 parsed + ready 状态，模拟已索引完成
        from app.storage import parsed_dir

        with session_scope() as s:
            d = s.get(Document, uuid.UUID(doc["id"]))
            parsed_dir(d.id).mkdir(parents=True, exist_ok=True)
            parsed_dir(d.id).joinpath("document.md").write_text("初始正文", encoding="utf-8")
            import hashlib

            d.checksum = hashlib.sha256("初始正文".encode()).hexdigest()
            d.status = "ready"
            s.commit()
        monkeypatch.setattr(index_mod, "embedding_keys_ready", lambda: True)

        def _inc(did):
            with session_scope() as s:
                d = s.get(Document, did)
                d.status = "ready"
                s.commit()
            return "ready"

        monkeypatch.setattr(index_mod, "index_document_incremental", _inc)
        monkeypatch.setattr(url_import, "fetch_html", lambda u: "<html/>")
        monkeypatch.setattr(url_import, "html_to_text", lambda h: "正文已经更新")
        res = client.post(f"/api/documents/{doc['id']}/refresh")
        assert res.status_code == 200
        assert res.headers.get("x-refresh-status") == "changed"
        body = res.json()
        assert body["version"] == 2
        assert body["status"] == "ready"
        rows = client.get(f"/api/documents/{doc['id']}/versions").json()
        assert sorted(r["version"] for r in rows) == [1, 2]


def test_refresh_unchanged_keeps_version(monkeypatch):
    import app.url_import as url_import
    from app import index as index_mod

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ref-{uuid.uuid4().hex[:8]}"}).json()
        doc = _make_url_doc(client, kb["id"], f"https://example.com/{uuid.uuid4().hex[:8]}")
        from app.storage import parsed_dir

        with session_scope() as s:
            d = s.get(Document, uuid.UUID(doc["id"]))
            parsed_dir(d.id).mkdir(parents=True, exist_ok=True)
            parsed_dir(d.id).joinpath("document.md").write_text("稳定正文", encoding="utf-8")
            import hashlib

            d.checksum = hashlib.sha256("稳定正文".encode()).hexdigest()
            d.status = "ready"
            s.commit()
        monkeypatch.setattr(index_mod, "embedding_keys_ready", lambda: True)
        monkeypatch.setattr(url_import, "fetch_html", lambda u: "<html/>")
        monkeypatch.setattr(url_import, "html_to_text", lambda h: "稳定正文")
        res = client.post(f"/api/documents/{doc['id']}/refresh")
        assert res.status_code == 200
        assert res.headers.get("x-refresh-status") == "unchanged"
        body = res.json()
        assert body["version"] == 1
        assert body["status"] == "ready"


def test_refresh_rejects_non_url(monkeypatch):
    from app import index as index_mod

    monkeypatch.setattr(index_mod, "embedding_keys_ready", lambda: True)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ref-{uuid.uuid4().hex[:8]}"}).json()
        doc = client.post(
            "/api/documents/notes",
            json={"knowledge_base_id": kb["id"], "content": "笔记内容"},
        ).json()
        res = client.post(f"/api/documents/{doc['id']}/refresh")
    assert res.status_code == 400


def test_refresh_kb_urls_queues_only_url_docs(monkeypatch):
    import app.routers.knowledge_bases as kb_router

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Ref-{uuid.uuid4().hex[:8]}"}).json()
        _make_url_doc(client, kb["id"], f"https://example.com/{uuid.uuid4().hex[:8]}")
        client.post("/api/documents/notes", json={"knowledge_base_id": kb["id"], "content": "x"})
        queued: list[uuid.UUID] = []
        monkeypatch.setattr(kb_router, "_refresh_url_task", lambda did: queued.append(did))
        res = client.post(f"/api/knowledge-bases/{kb['id']}/refresh-urls")
        assert res.status_code == 200
        assert res.json()["queued"] == 1
        assert len(queued) == 1
