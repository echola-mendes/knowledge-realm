from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.chunk import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from pydantic import BaseModel, Field, model_validator


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
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_enabled: bool | None = None


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
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    is_favorite: bool = False
    summary: str | None = None
    created_at: datetime | None = None
    created_by: str = ""
    chunk_size: int | None = None
    chunk_overlap: int | None = None

    model_config = {"from_attributes": True}


class DocumentChunkOut(BaseModel):
    id: uuid.UUID | None = None
    chunk_index: int
    chunk_label: str | None = None
    content: str
    page: int | None = None
    heading: str | None = None
    vector_status: str
    created_at: datetime | None = None


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
    created_after: datetime | None = None
    created_before: datetime | None = None


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
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationRename(BaseModel):
    title: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list | dict | None = None

    model_config = {"from_attributes": True}


class DocumentTagsPut(BaseModel):
    tag_ids: list[uuid.UUID] = Field(max_length=5)


class CompareRequest(BaseModel):
    document_id_a: uuid.UUID
    document_id_b: uuid.UUID


class CompareOut(BaseModel):
    document_id_a: uuid.UUID
    document_id_b: uuid.UUID
    comparison: str


class AgentRequest(BaseModel):
    task: str
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    allow_web: bool = False


class AgentOut(BaseModel):
    task: str
    knowledge_base_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: str
    citations: list[CitationOut]
    loop_count: int


class UserOut(BaseModel):
    id: uuid.UUID
    username: str

    model_config = {"from_attributes": True}


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    is_enabled: bool
    document_count: int = 0
    byte_size: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class GraphEntityOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str


class GraphLinkOut(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
    rel: str
    document_id: uuid.UUID | None = None


class DocumentGraphOut(BaseModel):
    document_id: uuid.UUID
    entities: list[GraphEntityOut]
    links: list[GraphLinkOut]


class KnowledgeGraphOut(BaseModel):
    entities: list[GraphEntityOut]
    links: list[GraphLinkOut]


class RelatedDocumentOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    score: float
    content: str


class RetrievalDebugRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    vector_k: int = Field(default=5, ge=1, le=100)
    bm25_k: int = Field(default=5, ge=1, le=100)
    rrf_k: int = Field(default=5, ge=1, le=100)
    rerank_k: int = Field(default=5, ge=1, le=100)
    vector_threshold: float = Field(default=0.30, ge=0, le=1)
    rrf_k_const: int = Field(default=60, ge=1, le=1000)
    eval_k: int = Field(default=5, ge=1, le=100)


class RetrievalDebugRow(BaseModel):
    rank: int
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    score: float
    vector_rank: int | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rrf_rank: int | None = None
    rrf_score: float | None = None
    rrf_from_vector: float | None = None
    rrf_from_bm25: float | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None
    final: bool = False


class RetrievalStageOut(BaseModel):
    requested_k: int
    actual_count: int
    threshold: float | None = None
    k_const: int | None = None
    candidate_count: int | None = None
    model: str | None = None
    rows: list[RetrievalDebugRow]


class RetrievalEvalOut(BaseModel):
    k: int
    recall: float | None = None
    precision: float | None = None
    relevant_chunk_count: int


class RetrievalTimingsOut(BaseModel):
    plan_ms: int = 0
    embed_ms: int = 0
    vector_ms: int = 0
    bm25_ms: int = 0
    rrf_ms: int = 0
    rerank_ms: int = 0
    final_ms: int = 0
    total_ms: int = 0


class RetrievalDebugResponse(BaseModel):
    query: str
    query_norm: str
    search_query: str | None = None
    next_action: Literal["search", "generate"] = "search"
    vector: RetrievalStageOut
    bm25: RetrievalStageOut
    rrf: RetrievalStageOut
    rerank: RetrievalStageOut
    final: list[RetrievalDebugRow]
    candidates: list[RetrievalDebugRow]
    evaluation: RetrievalEvalOut
    labels: dict[str, int]
    timings: RetrievalTimingsOut | None = None


class RetrievalLabelPut(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    chunk_id: uuid.UUID
    relevance: int = Field(ge=0, le=3)


class AnswerQualityRequest(BaseModel):
    query: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    contexts: list[str] = []


class AnswerQualityOut(BaseModel):
    faithfulness: int
    relevance: int
    completeness: int
    issues: list[str]


class RetrievalLabelOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    relevance: int


class DebugDatasetChunkOut(BaseModel):
    chunk_id: uuid.UUID
    chunk_label: str
    document_id: uuid.UUID
    document_name: str
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str
    chunk_index: int
    content: str


class ChunkSettingsOut(BaseModel):
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP


class ChunkSettingsPut(BaseModel):
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)

    @model_validator(mode="after")
    def overlap_lt_size(self) -> ChunkSettingsPut:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        return self

