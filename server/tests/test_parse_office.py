import io
import uuid

from docx import Document as DocxFile
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Document
from app.parse import parse_docx_document, parse_pdf_document
from app.storage import parsed_dir


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def _make_text_pdf(text: str) -> bytes:
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text, fontname="china-s")
    data = pdf.tobytes()
    pdf.close()
    return data


def _make_empty_pdf() -> bytes:
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page()
    data = pdf.tobytes()
    pdf.close()
    return data


def _make_docx(*paragraphs: str) -> bytes:
    doc = DocxFile()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_parse_pdf_with_selectable_text():
    phrase = f"可选中文字 {uuid.uuid4()}"
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("a.pdf", _make_text_pdf(phrase), "application/pdf")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_pdf_document(doc_id)
        md = (parsed_dir(doc_id) / "document.md").read_text(encoding="utf-8")
        assert "Page 1" in md
        assert phrase in md
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parsed"
        finally:
            session.close()


def test_parse_docx_two_paragraphs():
    a, b = "第一段可见", "第二段可见"
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={
                "file": (
                    "a.docx",
                    _make_docx(a, b),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_docx_document(doc_id)
        md = (parsed_dir(doc_id) / "document.md").read_text(encoding="utf-8")
        assert a in md
        assert b in md
        session = session_scope()
        try:
            doc = session.get(Document, doc_id)
            assert doc is not None
            assert doc.status == "parsed"
        finally:
            session.close()


def test_parse_empty_pdf_fails():
    with _client() as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("empty.pdf", _make_empty_pdf(), "application/pdf")},
        )
        doc_id = uuid.UUID(res.json()["id"])
        parse_pdf_document(doc_id)
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
