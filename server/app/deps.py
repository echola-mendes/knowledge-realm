from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import User


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def current_user(request: Request, session: Session = Depends(get_db)) -> User:
    raw = request.session.get("user_id")
    if not raw:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        uid = uuid.UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="未登录") from exc
    user = session.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return user
