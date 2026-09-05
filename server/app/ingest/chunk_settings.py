from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingest.chunk import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from app.models import UserChunkSetting


class ChunkSettingsError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkSettings:
    chunk_size: int
    chunk_overlap: int


def validate_chunk_settings(*, chunk_size: int, chunk_overlap: int) -> ChunkSettings:
    if chunk_size <= 0:
        raise ChunkSettingsError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ChunkSettingsError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ChunkSettingsError("chunk_overlap must be < chunk_size")
    return ChunkSettings(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def get_user_chunk_settings(session: Session, user_id: uuid.UUID) -> ChunkSettings:
    row = session.get(UserChunkSetting, user_id)
    if row is None:
        return ChunkSettings(chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP)
    return ChunkSettings(chunk_size=row.chunk_size, chunk_overlap=row.chunk_overlap)


def upsert_user_chunk_settings(
    session: Session,
    user_id: uuid.UUID,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> ChunkSettings:
    settings = validate_chunk_settings(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    row = session.get(UserChunkSetting, user_id)
    if row is None:
        row = UserChunkSetting(
            user_id=user_id,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        session.add(row)
    else:
        row.chunk_size = settings.chunk_size
        row.chunk_overlap = settings.chunk_overlap
    session.flush()
    return settings
