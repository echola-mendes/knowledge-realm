from __future__ import annotations

import json
import uuid

import httpx
import trafilatura

from app.db import session_scope
from app.models import Document
from app.ingest.parse import STATUS_PARSE_FAILED, STATUS_PARSED, STATUS_PARSING, URL_KIND
from app.ingest.storage import parsed_dir

URL_TIMEOUT_SEC = 20.0


def fetch_html(url: str) -> str:
    response = httpx.get(
        url,
        timeout=URL_TIMEOUT_SEC,
        follow_redirects=True,
        headers={"User-Agent": "knowledge-realm/1.0"},
    )
    response.raise_for_status()
    return response.text


def html_to_text(html: str) -> str:
    return (trafilatura.extract(html) or "").strip()


def process_url_document(document_id: uuid.UUID) -> None:
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.kind != URL_KIND or not doc.source_url:
            return
        doc.status = STATUS_PARSING
        session.commit()
        try:
            html = fetch_html(doc.source_url)
            text = html_to_text(html)
        except httpx.TimeoutException:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "url_timeout"
            session.commit()
            return
        except Exception:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "url_fetch_failed"
            session.commit()
            return
        if not text:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "empty_content"
            session.commit()
            return
        out = parsed_dir(doc.id)
        out.mkdir(parents=True, exist_ok=True)
        (out / "document.md").write_text(text, encoding="utf-8")
        (out / "document.json").write_text(
            json.dumps({"pages": [{"page": None, "text": text}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        doc.status = STATUS_PARSED
        doc.error_message = None
        session.commit()
    finally:
        session.close()


def fetch_url_document(document_id: uuid.UUID) -> str:
    """重新抓取 url 文档并写 parsed 目录。返回 "changed" / "unchanged" / "failed"。"""
    import hashlib

    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.kind != URL_KIND or not doc.source_url:
            return "failed"
        prev_status = doc.status
        doc.status = STATUS_PARSING
        session.commit()
        try:
            html = fetch_html(doc.source_url)
            text = html_to_text(html)
        except httpx.TimeoutException:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "url_timeout"
            session.commit()
            return "failed"
        except Exception:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "url_fetch_failed"
            session.commit()
            return "failed"
        if not text:
            doc.status = STATUS_PARSE_FAILED
            doc.error_message = "empty_content"
            session.commit()
            return "failed"
        old_md = parsed_dir(doc.id) / "document.md"
        old_text = old_md.read_text(encoding="utf-8") if old_md.is_file() else ""
        changed = hashlib.sha256(text.encode()).hexdigest() != hashlib.sha256(old_text.encode()).hexdigest()
        out = parsed_dir(doc.id)
        out.mkdir(parents=True, exist_ok=True)
        (out / "document.md").write_text(text, encoding="utf-8")
        (out / "document.json").write_text(
            json.dumps({"pages": [{"page": None, "text": text}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        # 未变更：恢复抓取前状态（通常 ready），避免检索不可见
        from app.ingest.index import STATUS_READY

        doc.status = STATUS_PARSED if changed else (STATUS_READY if prev_status == STATUS_READY else prev_status)
        doc.error_message = None
        session.commit()
        return "changed" if changed else "unchanged"
    finally:
        session.close()
