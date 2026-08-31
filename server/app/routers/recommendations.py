from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.models import User
from app.recommendations import recommend_documents
from app.schemas import RecommendationOut

router = APIRouter(prefix="/api", tags=["recommendations"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return recommend_documents(session, user.id)
