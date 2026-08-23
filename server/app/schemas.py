from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class KnowledgeBaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    ext: str
    kind: str
    checksum: str | None
    status: str
    error_message: str | None = None
    source_url: str | None = None
    source_path: str | None = None
    byte_size: int
    existed: bool = False

    model_config = {"from_attributes": True}


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
