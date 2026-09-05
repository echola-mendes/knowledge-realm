from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.es_bm25 import EsNotConfiguredError, delete_knowledge_base_chunks
from app.models import Document, DocumentVersion, KnowledgeBase, User
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate
from app.ingest.storage import remove_knowledge_base_files

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _owned(session: Session, kb_id: uuid.UUID, user_id: uuid.UUID) -> KnowledgeBase:
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None or kb.user_id != user_id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


def _kb_stats(session: Session, kb_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not kb_ids:
        return {}
    rows = session.execute(
        select(
            Document.knowledge_base_id,
            func.count(Document.id),
            func.coalesce(func.sum(Document.byte_size), 0),
        )
        .where(Document.knowledge_base_id.in_(kb_ids))
        .group_by(Document.knowledge_base_id)
    ).all()
    return {kb_id: (int(count), int(total)) for kb_id, count, total in rows}


def _out(kb: KnowledgeBase, document_count: int = 0, byte_size: int = 0) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        is_default=kb.is_default,
        is_enabled=kb.is_enabled,
        document_count=document_count,
        byte_size=byte_size,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _out_with_stats(session: Session, kb: KnowledgeBase) -> KnowledgeBaseOut:
    stats = _kb_stats(session, [kb.id])
    count, size = stats.get(kb.id, (0, 0))
    return _out(kb, count, size)


@router.get("", response_model=list[KnowledgeBaseOut])
def list_kbs(session: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = list(
        session.scalars(
            select(KnowledgeBase).where(KnowledgeBase.user_id == user.id).order_by(KnowledgeBase.created_at)
        ).all()
    )
    stats = _kb_stats(session, [kb.id for kb in rows])
    return [_out(kb, *stats.get(kb.id, (0, 0))) for kb in rows]


@router.post("", response_model=KnowledgeBaseOut, status_code=201)
def create_kb(body: KnowledgeBaseCreate, session: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = KnowledgeBase(user_id=user.id, name=body.name.strip(), is_default=False)
    session.add(kb)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="知识库名称已存在")
    session.refresh(kb)
    return _out(kb)


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_kb(kb_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    return _out_with_stats(session, _owned(session, kb_id, user.id))


@router.put("/{kb_id}", response_model=KnowledgeBaseOut)
def update_kb(
    kb_id: uuid.UUID,
    body: KnowledgeBaseUpdate,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    kb = _owned(session, kb_id, user.id)
    if body.name is None and body.is_enabled is None:
        raise HTTPException(status_code=400, detail="请提供名称或开启状态")
    if body.name is not None:
        kb.name = body.name.strip()
    if body.is_enabled is not None:
        kb.is_enabled = body.is_enabled
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="知识库名称已存在")
    session.refresh(kb)
    return _out_with_stats(session, kb)


@router.delete("/{kb_id}", status_code=204)
def delete_kb(kb_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _owned(session, kb_id, user.id)
    docs = list(session.scalars(select(Document).where(Document.knowledge_base_id == kb_id)))
    remove_knowledge_base_files(docs)
    try:
        delete_knowledge_base_chunks(kb_id)
    except EsNotConfiguredError:
        pass
    session.delete(kb)
    session.commit()


@router.post("/{kb_id}/refresh-urls")
def refresh_kb_urls(
    kb_id: uuid.UUID,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """后台逐个刷新库内全部 url 文档（P3-AUTO-1）。立即返回待刷新数量。"""
    _owned(session, kb_id, user.id)
    url_doc_ids = [
        row.id
        for row in session.scalars(
            select(Document).where(Document.knowledge_base_id == kb_id, Document.kind == "url")
        ).all()
    ]
    for doc_id in url_doc_ids:
        background.add_task(_refresh_url_task, doc_id)
    return {"queued": len(url_doc_ids)}


def _refresh_url_task(document_id: uuid.UUID) -> None:
    """BackgroundTasks 里的单文档刷新：抓取→版本→增量索引。"""
    import hashlib

    from app.ingest import index as index_mod
    from app.db import session_scope
    from app.models import Document
    from app.ingest.storage import parsed_dir
    from app.ingest.url_import import fetch_url_document

    result = fetch_url_document(document_id)
    if result != "changed":
        return
    session = session_scope()
    try:
        doc = session.get(Document, document_id)
        if doc is None:
            return
        md_path = parsed_dir(doc.id) / "document.md"
        if not md_path.is_file():
            return
        md = md_path.read_text(encoding="utf-8")
        new_checksum = hashlib.sha256(md.encode("utf-8")).hexdigest()
        if new_checksum != (doc.checksum or ""):
            doc.version += 1
            doc.checksum = new_checksum
            doc.byte_size = len(md.encode("utf-8"))
            session.commit()
            session.refresh(doc)
            exists = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == doc.id, DocumentVersion.version == doc.version
                )
            )
            if exists is None:
                session.add(
                    DocumentVersion(
                        document_id=doc.id,
                        version=doc.version,
                        checksum=doc.checksum,
                        byte_size=doc.byte_size,
                    )
                )
                session.commit()
    finally:
        session.close()
    index_mod.index_document_incremental(document_id)
