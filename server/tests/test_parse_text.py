from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Document
from app.parse import parse_text_document
from app.storage import parsed_dir
import uuid


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_parse_nonempty_txt_writes_md():
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("a.txt", b"hello parsed text", "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        md = parsed_dir(doc_id) / "document.md"
        js = parsed_dir(doc_id) / "document.json"
        assert md.read_text(encoding="utf-8") == "hello parsed text"
        assert js.is_file()
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parsed"
        finally:
            session.close()


def test_parse_blank_txt_fails_empty_content():
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("blank.txt", b"  \n\t  ", "text/plain")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_text_document(doc_id)
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parse_failed"
            assert doc.error_message is not None
            assert "empty_content" in doc.error_message
        finally:
            session.close()
    reset_app_state()
