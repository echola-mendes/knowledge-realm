from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppUser

DEFAULT_USER_NAME = "echola"


def ensure_default_user(session: Session) -> AppUser | None:
    count = session.scalar(select(func.count()).select_from(AppUser)) or 0
    if count == 0:
        user = AppUser(name=DEFAULT_USER_NAME, phone=None)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    return session.scalar(select(AppUser).where(AppUser.name == DEFAULT_USER_NAME))
