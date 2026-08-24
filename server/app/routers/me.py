from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import AppUser
from app.schemas import UserOut
from app.user import DEFAULT_USER_NAME

router = APIRouter(prefix="/api", tags=["me"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


@router.get("/me", response_model=UserOut)
def get_me(session: Session = Depends(get_db)):
    row = session.scalar(select(AppUser).where(AppUser.name == DEFAULT_USER_NAME))
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return row
