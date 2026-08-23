from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.kb import resolve_knowledge_base_id
from app.models import Document, DocumentChunk, DocumentTag, KnowledgeBase, Tag
from app.schemas import DocumentOut, DocumentTagsPut, NoteCreate, UrlCreate
from app import index as index_mod
from app.storage import original_path, remove_document_files, write_original

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".markdown": "md", ".txt": "txt"}
UPLOAD_MAX_BYTES = 100 * 1024 * 1024
STATUS_PENDING = "pending"


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _normalize_ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _document_out(doc: Document, *, existed: bool = False) -> DocumentOut:
    return DocumentOut.model_validate(doc).model_copy(
        update={
            "existed": existed,
            "source_url": doc.source_url,
            "source_path": str(original_path(doc.id, doc.ext)),
        }
    )


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID | None = Form(None),
    session: Session = Depends(get_db),
):
    ext = _normalize_ext(file.filename or "")
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 100MB")
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, existed=True)
    doc_id = uuid.uuid4()
    write_original(doc_id, ext, data)
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename or f"upload{ext}",
        ext=ext,
        kind=ALLOWED[ext],
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=len(data),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, existed=False)


@router.post("/notes", response_model=DocumentOut)
def create_note(
    body: NoteCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
):
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="笔记内容为空")
    kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    data = text.encode("utf-8")
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, existed=True)
    doc_id = uuid.uuid4()
    write_original(doc_id, ".md", data)
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=body.filename or "笔记.md",
        ext=".md",
        kind="note",
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=len(data),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, existed=False)


@router.post("/url", response_model=DocumentOut)
def create_url_document(
    body: UrlCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="只支持 http/https 公开页")
    kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    checksum = hashlib.sha256(url.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, existed=True)
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=url,
        ext=".md",
        kind="url",
        source_url=url,
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=0,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, existed=False)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
):
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    stmt = select(Document).where(Document.knowledge_base_id == kb_id)
    if tag_id is not None:
        stmt = stmt.join(DocumentTag).where(DocumentTag.tag_id == tag_id)
    rows = session.scalars(stmt.order_by(Document.created_at.desc())).all()
    return [_document_out(row) for row in rows]


@router.put("/{document_id}/tags", response_model=DocumentOut)
def set_document_tags(
    document_id: uuid.UUID,
    body: DocumentTagsPut,
    session: Session = Depends(get_db),
):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    unique_ids = list(dict.fromkeys(body.tag_ids))
    for tag_id in unique_ids:
        if session.get(Tag, tag_id) is None:
            raise HTTPException(status_code=404, detail="标签不存在")
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    for tag_id in unique_ids:
        session.add(DocumentTag(document_id=document_id, tag_id=tag_id))
    session.commit()
    session.refresh(doc)
    return _document_out(doc)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _document_out(doc)


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    remove_document_files(doc)
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.delete(doc)
    session.commit()
    return {"ok": True}


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex_document_http(document_id: uuid.UUID, session: Session = Depends(get_db)):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    index_mod.reindex_document(document_id)
    session.refresh(doc)
    return _document_out(doc)


@router.post("/{document_id}/index", response_model=DocumentOut)
def index_document_http(document_id: uuid.UUID, session: Session = Depends(get_db)):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    index_mod.index_document(document_id)
    session.refresh(doc)
    return _document_out(doc)
