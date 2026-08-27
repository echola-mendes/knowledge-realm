from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.passwords import hash_password, verify_password

DEFAULT_USER_NAME = "echola"


def ensure_default_user(session: Session) -> User:
    settings = get_settings()
    existing = session.scalar(select(User).where(User.username == settings.initial_username))
    if existing is not None:
        password = settings.initial_password
        if password and not verify_password(password, existing.password_hash):
            existing.password_hash = hash_password(password)
            session.commit()
            session.refresh(existing)
        return existing
    count = session.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        row = session.scalar(select(User).order_by(User.created_at))
        if row is None:
            raise RuntimeError("users 表异常")
        return row
    password = settings.initial_password
    if not password:
        raise RuntimeError("空用户表需要环境变量 INITIAL_PASSWORD")
    user = User(
        username=settings.initial_username,
        password_hash=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
