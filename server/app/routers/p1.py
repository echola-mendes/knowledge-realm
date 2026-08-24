from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import session_scope
from app.llm import llm_keys_ready
from app.models import Document
from app.p1.chains import compare_documents, gather_document_text
from app.schemas import CompareOut, CompareRequest

router = APIRouter(prefix="/api", tags=["p1"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _load_ready(session: Session, document_id: uuid.UUID) -> Document:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="文档未完成")
    return doc


@router.post("/compare", response_model=CompareOut)
def compare(body: CompareRequest, session: Session = Depends(get_db)):
    if body.document_id_a == body.document_id_b:
        raise HTTPException(status_code=400, detail="须选择两篇不同文档")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    doc_a = _load_ready(session, body.document_id_a)
    doc_b = _load_ready(session, body.document_id_b)
    if doc_a.knowledge_base_id != doc_b.knowledge_base_id:
        raise HTTPException(status_code=400, detail="两篇文档须属于同一知识库")
    text_a = gather_document_text(session, doc_a)
    text_b = gather_document_text(session, doc_b)
    if not text_a or not text_b:
        raise HTTPException(status_code=400, detail="empty_content")
    comparison = compare_documents(text_a, doc_a.filename, text_b, doc_b.filename)
    return CompareOut(
        document_id_a=doc_a.id,
        document_id_b=doc_b.id,
        comparison=comparison,
    )
