from __future__ import annotations

import uuid
from time import sleep

from sqlalchemy import delete

from app.chunk import split_markdown
from app.config import get_settings
from app.db import session_scope
from app.models import Document, DocumentChunk
from app.parse import DOCX_KIND, PDF_KIND, TEXT_KINDS, URL_KIND, parse_docx_document, parse_pdf_document, parse_text_document
from app.url_import import process_url_document
from app.storage import parsed_dir

STATUS_PARSED = "parsed"
STATUS_PARSE_FAILED = "parse_failed"
STATUS_INDEXING = "indexing"
STATUS_READY = "ready"
STATUS_INDEX_FAILED = "index_failed"
EMBED_BATCH = 10
EMBED_TRIES = 3
QUOTA_HINT = (
    "额度不足或当前 Embedding 模型不可用。"
    "请将 .env 的 EMBEDDING_MODEL 改为 text-embedding-v4 后重启（不会自动换模型）。"
)


def embedding_keys_ready() -> bool:
    s = get_settings()
    return bool((s.embedding_api_key or s.llm_api_key).strip())


def is_quota_or_v3_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    needles = (
        "insufficient_quota",
        "quota",
        "arrearage",
        "freequota",
        "exceeded",
        "余额",
        "额度",
        "text-embedding-v3",
        "forbidden",
        "accessdenied",
    )
    return any(n in text for n in needles)


def format_embed_error(exc: BaseException) -> str:
    if is_quota_or_v3_error(exc):
        return QUOTA_HINT
    return f"embed_failed:{exc}"


def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(
        api_key=(s.embedding_api_key or s.llm_api_key).strip(),
        base_url=s.embedding_base_url,
    )
    kwargs: dict = {"model": s.embedding_model, "input": texts}
    if s.embedding_dim:
        kwargs["dimensions"] = s.embedding_dim
    last: BaseException | None = None
    for attempt in range(EMBED_TRIES):
        try:
            resp = client.embeddings.create(**kwargs)
            return [item.embedding for item in resp.data]
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < EMBED_TRIES - 1:
                sleep(0.05)
    assert last is not None
    raise last


def _embed_all(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        vectors.extend(embed_texts(batch))
    return vectors


def index_document(document_id: uuid.UUID) -> None:
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.status == STATUS_PARSE_FAILED:
            return
        if doc.status == STATUS_READY:
            return
        md_path = parsed_dir(doc.id) / "document.md"
        if not md_path.is_file():
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "no_parsed_markdown"
            session.commit()
            return
        if not embedding_keys_ready():
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "未配置 Embedding API Key"
            session.commit()
            return
        text = md_path.read_text(encoding="utf-8")
        pieces = split_markdown(text)
        if not pieces:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "no_chunks"
            session.commit()
            return
        doc.status = STATUS_INDEXING
        session.commit()
        try:
            vectors = _embed_all([p.content for p in pieces])
        except Exception as exc:  # noqa: BLE001
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = format_embed_error(exc)
            session.commit()
            return
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        for i, (piece, vec) in enumerate(zip(pieces, vectors, strict=True)):
            session.add(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=piece.content,
                    page=piece.page,
                    heading=piece.heading,
                    metadata_={},
                    embedding=vec,
                )
            )
        doc.status = STATUS_READY
        doc.error_message = None
        session.commit()
    finally:
        session.close()


def reindex_document(document_id: uuid.UUID) -> None:
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            return
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        doc.status = "pending"
        doc.error_message = None
        session.commit()
    finally:
        session.close()
    process_document(document_id)


def process_document(document_id: uuid.UUID) -> None:
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        kind = doc.kind if doc is not None else None
    finally:
        session.close()
    if kind in TEXT_KINDS:
        parse_text_document(document_id)
    elif kind == PDF_KIND:
        parse_pdf_document(document_id)
    elif kind == DOCX_KIND:
        parse_docx_document(document_id)
    elif kind == URL_KIND:
        process_url_document(document_id)
    index_document(document_id)
