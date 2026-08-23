from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    content: str = Field(min_length=1)
    filename: str | None = None
    knowledge_base_id: uuid.UUID | None = None


class UrlCreate(BaseModel):
    url: str = Field(min_length=8)
    knowledge_base_id: uuid.UUID | None = None


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


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    kind: str | None = None
    k: int = Field(default=5, ge=1, le=20)


class SearchHitOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    content: str
    score: float
    page: int | None = None
    heading: str | None = None
    kind: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    k: int = Field(default=5, ge=1, le=20)


class CitationOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    page_start: int | None = None
    page_end: int | None = None
    content: str
    score: float


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    citations: list[CitationOut]


class ConversationOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list | dict | None = None

    model_config = {"from_attributes": True}


class DocumentTagsPut(BaseModel):
    tag_ids: list[uuid.UUID]


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
