from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Document, KnowledgeBase
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate
from app.storage import remove_knowledge_base_files

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


@router.get("", response_model=list[KnowledgeBaseOut])
def list_kbs(session: Session = Depends(get_db)):
    rows = session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)).all()
    return rows


@router.post("", response_model=KnowledgeBaseOut, status_code=201)
def create_kb(body: KnowledgeBaseCreate, session: Session = Depends(get_db)):
    kb = KnowledgeBase(name=body.name.strip(), is_default=False)
    session.add(kb)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="知识库名称已存在")
    session.refresh(kb)
    return kb


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_kb(kb_id: uuid.UUID, session: Session = Depends(get_db)):
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.put("/{kb_id}", response_model=KnowledgeBaseOut)
def update_kb(kb_id: uuid.UUID, body: KnowledgeBaseUpdate, session: Session = Depends(get_db)):
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    kb.name = body.name.strip()
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="知识库名称已存在")
    session.refresh(kb)
    return kb


@router.delete("/{kb_id}", status_code=204)
def delete_kb(kb_id: uuid.UUID, session: Session = Depends(get_db)):
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    docs = list(session.scalars(select(Document).where(Document.knowledge_base_id == kb_id)))
    remove_knowledge_base_files(docs)
    session.delete(kb)
    session.commit()
    return None
