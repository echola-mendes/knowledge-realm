from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Tag
from app.schemas import TagCreate, TagOut

router = APIRouter(prefix="/api/tags", tags=["tags"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


@router.get("", response_model=list[TagOut])
def list_tags(session: Session = Depends(get_db)):
    return session.scalars(select(Tag).order_by(Tag.name)).all()


@router.post("", response_model=TagOut, status_code=201)
def create_tag(body: TagCreate, session: Session = Depends(get_db)):
    tag = Tag(name=body.name.strip())
    if not tag.name:
        raise HTTPException(status_code=400, detail="标签名为空")
    session.add(tag)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="标签名称已存在")
    session.refresh(tag)
    return tag


@router.delete("/{tag_id}")
def delete_tag(tag_id: uuid.UUID, session: Session = Depends(get_db)):
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    session.delete(tag)
    session.commit()
    return {"ok": True}
