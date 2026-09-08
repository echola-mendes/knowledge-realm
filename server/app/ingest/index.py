from __future__ import annotations

import logging
import uuid
from time import sleep
from typing import Any

from sqlalchemy import delete, select

from app.ingest.chunk import SectionSplit, split_markdown_sections
from app.ingest.chunk_settings import get_user_chunk_settings
from app.ingest.chunk_label import allocate_chunk_labels
from app.config import get_settings
from app.db import session_scope
from app.rag.es_bm25 import EsNotConfiguredError, delete_document_chunks, upsert_chunks
from app.models import Document, DocumentChunk, KnowledgeBase
from app.ingest.parse import DOCX_KIND, PDF_KIND, TEXT_KINDS, URL_KIND, parse_docx_document, parse_pdf_document, parse_text_document
from app.ingest.url_import import process_url_document
from app.ingest.storage import parsed_dir

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
    # 用量日志：Embedding 接口不透出精确 token，按「非 ASCII 字符 1 token、ASCII 每 4 字符 1 token」粗估
    approx = 0
    for t in texts:
        non_ascii = sum(1 for ch in t if ord(ch) > 127)
        approx += non_ascii + (len(t) - non_ascii + 3) // 4
    logging.getLogger(__name__).info(
        "embed usage: chunks=%d chars=%d approx_tokens=%d", len(texts), sum(len(t) for t in texts), approx
    )
    return vectors



def _align_keys_from_sections(sections: list[SectionSplit]) -> list[tuple]:
    keys: list[tuple] = []
    for sec in sections:
        parent_key = None
        if sec.parent is not None:
            parent_key = ("parent", sec.parent.heading, sec.parent.content)
            keys.append(parent_key)
        for child in sec.children:
            keys.append(("child", child.heading, child.content, parent_key))
    return keys


def _align_keys_from_db(chunks: list[DocumentChunk]) -> list[tuple]:
    by_id = {c.id: c for c in chunks}
    keys: list[tuple] = []
    for c in chunks:
        if getattr(c, "role", "child") == "parent":
            keys.append(("parent", c.heading, c.content))
            continue
        parent_key = None
        if c.parent_id and c.parent_id in by_id:
            p = by_id[c.parent_id]
            parent_key = ("parent", p.heading, p.content)
        keys.append(("child", c.heading, c.content, parent_key))
    return keys


def _plan_chunk_rows(sections: list[SectionSplit]) -> tuple[list[dict[str, Any]], list[str], list[tuple]]:
    """Build ordered parent/child rows; return rows, child texts, child align keys."""
    rows: list[dict[str, Any]] = []
    child_texts: list[str] = []
    child_keys: list[tuple] = []
    idx = 0
    for sec in sections:
        parent_key = None
        parent_id = None
        if sec.parent is not None:
            parent_id = uuid.uuid4()
            parent_key = ("parent", sec.parent.heading, sec.parent.content)
            rows.append(
                {
                    "id": parent_id,
                    "chunk_index": idx,
                    "content": sec.parent.content,
                    "page": sec.parent.page,
                    "heading": sec.parent.heading,
                    "role": "parent",
                    "parent_id": None,
                    "embedding": None,
                }
            )
            idx += 1
        for child in sec.children:
            child_id = uuid.uuid4()
            key = ("child", child.heading, child.content, parent_key)
            rows.append(
                {
                    "id": child_id,
                    "chunk_index": idx,
                    "content": child.content,
                    "page": child.page,
                    "heading": child.heading,
                    "role": "child",
                    "parent_id": parent_id,
                    "embedding": None,  # filled by caller
                }
            )
            child_texts.append(child.content)
            child_keys.append(key)
            idx += 1
    return rows, child_texts, child_keys


def _persist_chunk_rows(
    session,
    doc: Document,
    rows: list[dict[str, Any]],
) -> None:
    labels = allocate_chunk_labels(session, len(rows))
    for row, label in zip(rows, labels, strict=True):
        session.add(
            DocumentChunk(
                id=row["id"],
                document_id=doc.id,
                chunk_index=row["chunk_index"],
                chunk_label=label,
                content=row["content"],
                page=row["page"],
                heading=row["heading"],
                metadata_={},
                role=row["role"],
                parent_id=row["parent_id"],
                embedding=row["embedding"],
            )
        )


def _upsert_child_chunks(doc: Document, rows: list[DocumentChunk]) -> None:
    children = [c for c in rows if c.role == "child"]
    upsert_chunks(
        [(c.id, c.content, doc.knowledge_base_id, doc.id, doc.kind) for c in children]
    )


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
        kb = session.get(KnowledgeBase, doc.knowledge_base_id)
        if kb is None:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "knowledge_base_missing"
            session.commit()
            return
        chunk_cfg = get_user_chunk_settings(session, kb.user_id)
        sections = split_markdown_sections(
            text,
            chunk_size=chunk_cfg.chunk_size,
            chunk_overlap=chunk_cfg.chunk_overlap,
        )
        planned, child_texts, _child_keys = _plan_chunk_rows(sections)
        if not planned or not child_texts:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "no_chunks"
            session.commit()
            return
        doc.status = STATUS_INDEXING
        session.commit()
        try:
            vectors = _embed_all(child_texts)
        except Exception as exc:  # noqa: BLE001
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = format_embed_error(exc)
            session.commit()
            return
        child_i = 0
        for row in planned:
            if row["role"] == "child":
                row["embedding"] = vectors[child_i]
                child_i += 1
        try:
            delete_document_chunks(doc.id)
        except EsNotConfiguredError as exc:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = str(exc)
            session.commit()
            return
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        _persist_chunk_rows(session, doc, planned)
        doc.status = STATUS_READY
        doc.error_message = None
        doc.chunk_size = chunk_cfg.chunk_size
        doc.chunk_overlap = chunk_cfg.chunk_overlap
        session.commit()
        rows = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc.id)).all()
        try:
            _upsert_child_chunks(doc, list(rows))
        except EsNotConfiguredError as exc:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = str(exc)
            session.commit()
            return
        _enrich_after_index(document_id)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        doc = session.get(Document, document_id)
        if doc is not None and doc.status == STATUS_INDEXING:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = f"index_error:{exc}"
            session.commit()
    finally:
        session.close()


def _enrich_after_index(document_id: uuid.UUID) -> None:
    from app.chains import enrich_document_after_ready

    enrich_document_after_ready(document_id)


def index_document_incremental(document_id: uuid.UUID) -> str:
    """差量重索引：新旧切片按 role + (heading, content) + parent 结构对齐，未变更 child 复用 embedding。

    返回 "ready"（有差量并完成）/"unchanged"（切片完全一致）/"failed"。
    全新文档（无现有切片）行为等同 index_document。
    """
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            return "failed"
        md_path = parsed_dir(doc.id) / "document.md"
        if not md_path.is_file():
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "no_parsed_markdown"
            session.commit()
            return "failed"
        if not embedding_keys_ready():
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "未配置 Embedding API Key"
            session.commit()
            return "failed"
        text = md_path.read_text(encoding="utf-8")
        kb = session.get(KnowledgeBase, doc.knowledge_base_id)
        if kb is None:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "knowledge_base_missing"
            session.commit()
            return "failed"
        chunk_cfg = get_user_chunk_settings(session, kb.user_id)
        sections = split_markdown_sections(
            text,
            chunk_size=chunk_cfg.chunk_size,
            chunk_overlap=chunk_cfg.chunk_overlap,
        )
        planned, child_texts, child_keys = _plan_chunk_rows(sections)
        if not planned or not child_texts:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = "no_chunks"
            session.commit()
            return "failed"
        existing = list(
            session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id).order_by(DocumentChunk.chunk_index)
            ).all()
        )
        new_keys = _align_keys_from_sections(sections)
        old_keys = _align_keys_from_db(existing)
        if new_keys == old_keys:
            doc.status = STATUS_READY
            doc.error_message = None
            session.commit()
            return "unchanged"
        doc.status = STATUS_INDEXING
        session.commit()
        # 未变更 child 按 (role, heading, content, parent_key) 复用向量
        reusable: dict[tuple, Any] = {}
        by_id = {c.id: c for c in existing}
        for chunk in existing:
            if chunk.role != "child" or chunk.embedding is None:
                continue
            parent_key = None
            if chunk.parent_id and chunk.parent_id in by_id:
                p = by_id[chunk.parent_id]
                parent_key = ("parent", p.heading, p.content)
            reusable[("child", chunk.heading, chunk.content, parent_key)] = chunk.embedding
        vectors: list[list[float] | list] = []
        missing: list[int] = []
        for i, key in enumerate(child_keys):
            vec = reusable.get(key)
            if vec is not None:
                vectors.append(vec)
            else:
                vectors.append([])
                missing.append(i)
        if missing:
            try:
                fresh = _embed_all([child_texts[i] for i in missing])
            except Exception as exc:  # noqa: BLE001
                doc.status = STATUS_INDEX_FAILED
                doc.error_message = format_embed_error(exc)
                session.commit()
                return "failed"
            for pos, vec in zip(missing, fresh, strict=True):
                vectors[pos] = vec
        child_i = 0
        for row in planned:
            if row["role"] == "child":
                row["embedding"] = vectors[child_i]
                child_i += 1
        try:
            delete_document_chunks(doc.id)
        except EsNotConfiguredError as exc:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = str(exc)
            session.commit()
            return "failed"
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        _persist_chunk_rows(session, doc, planned)
        doc.status = STATUS_READY
        doc.error_message = None
        doc.chunk_size = chunk_cfg.chunk_size
        doc.chunk_overlap = chunk_cfg.chunk_overlap
        session.commit()
        rows = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc.id)).all()
        try:
            _upsert_child_chunks(doc, list(rows))
        except EsNotConfiguredError as exc:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = str(exc)
            session.commit()
            return "failed"
        return "ready"
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        doc = session.get(Document, document_id)
        if doc is not None and doc.status == STATUS_INDEXING:
            doc.status = STATUS_INDEX_FAILED
            doc.error_message = f"index_error:{exc}"
            session.commit()
        return "failed"
    finally:
        session.close()


def reindex_document(document_id: uuid.UUID) -> None:
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            return
        try:
            delete_document_chunks(document_id)
        except EsNotConfiguredError:
            pass
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        doc.status = "pending"
        doc.error_message = None
        session.commit()
    finally:
        session.close()
    process_document(document_id)


def reindex_chunk(chunk_id: uuid.UUID) -> bool:
    """仅重新向量化一条切片，不重跑整篇文档解析。成功返回 True，切片不存在返回 False。"""
    if not embedding_keys_ready():
        raise RuntimeError("未配置 Embedding API Key")
    session = session_scope()
    try:
        chunk = session.get(DocumentChunk, chunk_id)
        if chunk is None:
            return False
        if chunk.role == "parent" or chunk.embedding is None:
            raise RuntimeError("parent 切片不可单独向量化")
        doc = session.get(Document, chunk.document_id)
        if doc is None:
            return False
        try:
            vectors = embed_texts([chunk.content])
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(format_embed_error(exc)) from exc
        chunk.embedding = vectors[0]
        session.commit()
        try:
            upsert_chunks(
                [(chunk.id, chunk.content, doc.knowledge_base_id, doc.id, doc.kind)]
            )
        except EsNotConfiguredError:
            pass
        return True
    finally:
        session.close()


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
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None or doc.status == STATUS_PARSE_FAILED:
            return
    finally:
        session.close()
    index_document(document_id)
