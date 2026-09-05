import uuid

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.ingest.index import index_document, process_document
from app.main import create_app, reset_app_state
from app.models import Document, DocumentChunk
from app.ingest.parse import parse_text_document
from app.ingest.storage import parsed_dir


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


SAMPLE_HTML = """
<html><head><title>公开文章</title></head>
<body>
<article>
<h1>可见标题</h1>
<p>这是一段用于抽取的正文，必须出现在解析稿里。</p>
</article>
</body></html>
"""


def test_create_note_reaches_ready_with_chunks(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    body = f"# 笔记\n\n内容 {uuid.uuid4()}"
    with _client() as client:
        res = client.post("/api/documents/notes", json={"content": body, "filename": "n.md"})
        assert res.status_code == 200
        doc_id = uuid.UUID(res.json()["id"])
        assert res.json()["kind"] == "note"
        parse_text_document(doc_id)
        index_document(doc_id)
        detail = client.get(f"/api/documents/{doc_id}")
        assert detail.json()["status"] == "ready"
        session = session_scope()
        try:
            n = session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
            assert n > 0
        finally:
            session.close()


def test_create_note_filename_from_heading():
    body = f"# 退款\n\n说明 {uuid.uuid4()}"
    with _client() as client:
        res = client.post("/api/documents/notes", json={"content": body})
        assert res.status_code == 200
        assert res.json()["filename"] == "退款.md"
        assert res.json()["kind"] == "note"


def test_create_note_filename_from_first_line_when_no_heading():
    body = f"纯文本标题行\n\n正文 {uuid.uuid4()}"
    with _client() as client:
        res = client.post("/api/documents/notes", json={"content": body})
        assert res.status_code == 200
        assert res.json()["filename"] == "纯文本标题行.md"

def test_url_import_from_mocked_html(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.ingest.url_import.fetch_html", lambda url: SAMPLE_HTML)
    with _client() as client:
        res = client.post("/api/documents/url", json={"url": "https://example.com/article"})
        assert res.status_code == 200
        doc_id = uuid.UUID(res.json()["id"])
        assert res.json()["source_url"] == "https://example.com/article"
        process_document(doc_id)
        md = (parsed_dir(doc_id) / "document.md").read_text(encoding="utf-8")
        assert "正文" in md
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "ready"
            assert doc.kind == "url"
        finally:
            session.close()


def test_url_empty_or_timeout_fails(monkeypatch):
    monkeypatch.setattr("app.ingest.url_import.fetch_html", lambda url: "<html><body></body></html>")
    with _client() as client:
        empty = client.post("/api/documents/url", json={"url": "https://example.com/empty"})
        doc_id = uuid.UUID(empty.json()["id"])
        process_document(doc_id)
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parse_failed"
            assert doc.error_message == "empty_content"
        finally:
            session.close()

    def boom(url: str) -> str:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.ingest.url_import.fetch_html", boom)
    with _client() as client:
        timed = client.post("/api/documents/url", json={"url": "https://example.com/slow"})
        doc_id = uuid.UUID(timed.json()["id"])
        process_document(doc_id)
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parse_failed"
            assert doc.error_message == "url_timeout"
        finally:
            session.close()
    reset_app_state()
