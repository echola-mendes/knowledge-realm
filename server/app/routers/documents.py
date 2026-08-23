from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.kb import resolve_knowledge_base_id
from app.models import Document, KnowledgeBase
from app.schemas import DocumentOut
from app import index as index_mod
from app.storage import write_original

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
        return DocumentOut.model_validate(existing).model_copy(update={"existed": True})
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
    return DocumentOut.model_validate(doc).model_copy(update={"existed": False})


@router.post("/{document_id}/index", response_model=DocumentOut)
def index_document_http(document_id: uuid.UUID, session: Session = Depends(get_db)):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    index_mod.index_document(document_id)
    session.refresh(doc)
    return DocumentOut.model_validate(doc).model_copy(update={"existed": False})
