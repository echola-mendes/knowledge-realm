from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

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
    version: int = 1

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    version: int
    checksum: str | None = None
    byte_size: int
    created_at: datetime | None = None

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
    knowledge_base_name: str | None = None
    tags: list[str] = []
    created_at: datetime | None = None


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
    mode: str = "chat"
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationPatch(BaseModel):
    title: str | None = None
    mode: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list | dict | None = None
    plan_html: dict | None = None
    travel: dict | None = None
    pending_action: dict | None = None
    bookings: list[dict] | None = None

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
    hitl_confirm: bool | None = None


class AgentOut(BaseModel):
    task: str
    knowledge_base_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: str
    citations: list[CitationOut]
    loop_count: int
    intent: str | None = None
    report_url: str | None = None
    pending_action: dict[str, Any] | None = None
    bookings: list[dict[str, Any]] | None = None


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
    created_at: datetime | None = None
    source_doc_count: int = 0
    description: str | None = None
    confidence: float | None = None


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


class RagEvalCasePut(BaseModel):
    query: str = Field(min_length=1)
    knowledge_base_id: uuid.UUID | None = None
    gt_answer: str = Field(min_length=1)


class RagEvalCaseOut(BaseModel):
    query_norm: str
    knowledge_base_id: uuid.UUID | None = None
    gt_answer: str


class RagMetricsRequest(BaseModel):
    query: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    contexts: list[str] = []
    gt_answer: str | None = None


class RagMetricsOut(BaseModel):
    faithfulness: float | None
    answer_relevance: float | None
    answer_correctness: float | None
    semantic_similarity: float | None


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



class ConflictItem(BaseModel):
    documents: list[str] = Field(default_factory=list)
    point: str
    detail: str
    suggestion: str


class ConflictReport(BaseModel):
    conflicts: list[ConflictItem] = Field(default_factory=list)
    truncated: bool = False


class GapItem(BaseModel):
    topic: str
    evidence: str = ""
    suggestion: str = ""


class GapReport(BaseModel):
    covered_topics: list[str] = Field(default_factory=list)
    gaps: list[GapItem] = Field(default_factory=list)
    truncated: bool = False


class OrganizeAppliedItem(BaseModel):
    document: str
    tags: list[str] = Field(default_factory=list)


class OrganizeBody(BaseModel):
    apply_tags: bool = True


class OrganizeReport(BaseModel):
    applied: list[OrganizeAppliedItem] = Field(default_factory=list)
    applied_tags: bool
    duplicates: list[list[str]] = Field(default_factory=list)
    empty_summary: list[str] = Field(default_factory=list)
    bad_names: list[str] = Field(default_factory=list)
    untagged_total: int = 0

class RecommendationOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    knowledge_base_id: uuid.UUID
    score: float
    kind: str

class GraphSearchOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    content: str
    score: float
    page: int | None = None
    heading: str | None = None
    kind: str


class GraphSearchDocumentOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    score: float
    chunk_id: uuid.UUID
    content: str
    page: int | None = None
    heading: str | None = None
    kind: str


class GraphPathOut(BaseModel):
    entities: list[GraphEntityOut]
    rels: list[str]


class GraphDocumentOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    version: int


class GraphSearchDetailOut(BaseModel):
    query: str
    entities: list[GraphEntityOut]
    links: list[GraphLinkOut]
    documents: list[GraphSearchDocumentOut]
    paths: list[GraphPathOut]


class PlanRecordOut(BaseModel):
    id: uuid.UUID
    title: str
    origin: str | None = None
    destination: str | None = None
    depart_date: str | None = None
    trip_type: str = "other"
    nights: int | None = None
    conversation_id: uuid.UUID | None = None
    url: str | None = None
    minio_key: str | None = None
    created_at: datetime | None = None

class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=64)
    schedule_type: Literal["INTERVAL", "CRON"]
    schedule_config: dict[str, Any]
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    schedule_type: Literal["INTERVAL", "CRON"] | None = None
    schedule_config: dict[str, Any] | None = None
    enabled: bool | None = None


class TaskOut(BaseModel):
    id: int
    name: str
    task_type: str
    schedule_type: str
    schedule_config: dict[str, Any]
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExecutionOut(BaseModel):
    id: int
    task_id: int
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskTypeOut(BaseModel):
    task_type: str
    label: str


class NewsHotItemOut(BaseModel):
    id: int
    rank: int
    title: str
    summary: str | None = None
    category: str
    source: str
    published_at: datetime | None = None
    heat_score: float | None = None


class NewsHotOut(BaseModel):
    date: date
    category: str
    items: list[NewsHotItemOut]


class NewsDetailOut(BaseModel):
    id: int
    title: str
    summary: str | None = None
    content: str | None = None
    url: str
    source: str
    category: str
    published_at: datetime | None = None
    collected_at: datetime | None = None
    heat_score: float | None = None
    importance_score: int | None = None

    model_config = {"from_attributes": True}


class NewsSettingsOut(BaseModel):
    enabled_categories: list[str]


class NewsSettingsIn(BaseModel):
    enabled_categories: list[str]
