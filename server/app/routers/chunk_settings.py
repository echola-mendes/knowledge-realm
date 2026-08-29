from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.chunk_settings import ChunkSettingsError, get_user_chunk_settings, upsert_user_chunk_settings
from app.deps import current_user, get_db
from app.models import User
from app.schemas import ChunkSettingsOut, ChunkSettingsPut

router = APIRouter(prefix="/api", tags=["chunk-settings"])


@router.get("/chunk-settings", response_model=ChunkSettingsOut)
def get_chunk_settings(user: User = Depends(current_user), session: Session = Depends(get_db)):
    settings = get_user_chunk_settings(session, user.id)
    return ChunkSettingsOut(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)


@router.put("/chunk-settings", response_model=ChunkSettingsOut)
def put_chunk_settings(
    body: ChunkSettingsPut,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
):
    try:
        settings = upsert_user_chunk_settings(
            session,
            user.id,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
    except ChunkSettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return ChunkSettingsOut(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
