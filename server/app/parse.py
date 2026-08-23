from __future__ import annotations

import json
import uuid
from time import monotonic

from app.db import session_scope
from app.models import Document
from app.storage import original_path, parsed_dir

PARSE_TIMEOUT_SEC = 60
STATUS_PARSING = "parsing"
STATUS_PARSED = "parsed"
STATUS_PARSE_FAILED = "parse_failed"
TEXT_KINDS = {"txt", "md"}
PDF_KIND = "pdf"
DOCX_KIND = "docx"


def _write_parsed(doc_id: uuid.UUID, markdown: str, pages: list[dict]) -> None:
    out = parsed_dir(doc_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "document.md").write_text(markdown, encoding="utf-8")
    (out / "document.json").write_text(
        json.dumps({"pages": pages}, ensure_ascii=False),
        encoding="utf-8",
    )


def _fail(session, doc: Document, reason: str) -> None:
    doc.status = STATUS_PARSE_FAILED
    doc.error_message = reason
    session.commit()


def _succeed(session, doc: Document) -> None:
    doc.status = STATUS_PARSED
    doc.error_message = None
    session.commit()


def parse_text_document(document_id: uuid.UUID) -> None:
    started = monotonic()
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.kind not in TEXT_KINDS:
            return
        doc.status = STATUS_PARSING
        session.commit()
        path = original_path(doc.id, doc.ext)
        raw = path.read_bytes()
        if monotonic() - started > PARSE_TIMEOUT_SEC:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "parse_timeout"
            session.commit()
            return
        text = raw.decode("utf-8")
        if not text.strip():
            _fail(session, doc, "empty_content")
            return
        _write_parsed(doc.id, text, [{"page": None, "text": text}])
        _succeed(session, doc)
    except UnicodeDecodeError:
        doc = session.get(Document, document_id)
        if doc is not None:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "invalid_utf8"
            session.commit()
    finally:
            session.close()


def parse_pdf_document(document_id: uuid.UUID) -> None:
    import pymupdf

    started = monotonic()
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.kind != PDF_KIND:
            return
        doc.status = STATUS_PARSING
        session.commit()
        path = original_path(doc.id, doc.ext)
        pages_out: list[dict] = []
        md_parts: list[str] = []
        with pymupdf.open(path) as pdf:
            for i, page in enumerate(pdf, start=1):
                if monotonic() - started > PARSE_TIMEOUT_SEC:
                    _fail(session, doc, "parse_timeout")
                    return
                text = page.get_text() or ""
                pages_out.append({"page": i, "text": text})
                md_parts.append(f"## Page {i}\n\n{text}")
        combined = "\n\n".join(md_parts)
        if not "".join(p["text"] for p in pages_out).strip():
            _fail(session, doc, "empty_content")
            return
        _write_parsed(doc.id, combined, pages_out)
        _succeed(session, doc)
    except Exception:
        doc = session.get(Document, document_id)
        if doc is not None:
            _fail(session, doc, "parse_error")
    finally:
        session.close()


def parse_docx_document(document_id: uuid.UUID) -> None:
    from docx import Document as DocxFile

    started = monotonic()
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.kind != DOCX_KIND:
            return
        doc.status = STATUS_PARSING
        session.commit()
        path = original_path(doc.id, doc.ext)
        if monotonic() - started > PARSE_TIMEOUT_SEC:
            _fail(session, doc, "parse_timeout")
            return
        loaded = DocxFile(str(path))
        paragraphs = [p.text for p in loaded.paragraphs]
        text = "\n".join(paragraphs)
        if not text.strip():
            _fail(session, doc, "empty_content")
            return
        _write_parsed(doc.id, text, [{"page": None, "text": text}])
        _succeed(session, doc)
    except Exception:
        doc = session.get(Document, document_id)
        if doc is not None:
            _fail(session, doc, "parse_error")
    finally:
        session.close()
