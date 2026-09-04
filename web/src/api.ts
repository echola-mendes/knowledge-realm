export type KnowledgeBase = {
  id: string;
  name: string;
  is_default: boolean;
  is_enabled: boolean;
  document_count: number;
  byte_size: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DocumentItem = {
  id: string;
  knowledge_base_id: string;
  filename: string;
  ext: string;
  kind: string;
  status: string;
  error_message: string | null;
  source_url: string | null;
  tag_ids: string[];
  is_favorite: boolean;
  summary: string | null;
  byte_size: number;
  created_at?: string | null;
  created_by?: string;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  version?: number;
};

export type DocumentVersionItem = {
  version: number;
  checksum?: string | null;
  byte_size: number;
  created_at?: string | null;
};

export function listDocumentVersions(documentId: string) {
  return api<DocumentVersionItem[]>(`/api/documents/${documentId}/versions`);
}

export type RefreshUrlResult = DocumentItem & { refresh_status?: "changed" | "unchanged" };

export async function refreshUrlDocument(documentId: string): Promise<RefreshUrlResult> {
  const res = await fetch(`/api/documents/${documentId}/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(messageFromErrorBody(await res.text(), res.statusText));
  }
  const body = (await res.json()) as DocumentItem;
  const status = res.headers.get("x-refresh-status");
  return {
    ...body,
    refresh_status: status === "changed" || status === "unchanged" ? status : undefined,
  };
}

export function refreshKbUrls(kbId: string) {
  return api<{ queued: number }>(`/api/knowledge-bases/${kbId}/refresh-urls`, { method: "POST" });
}

export type TagItem = { id: string; name: string };

export type SearchHit = {
  document_id: string;
  document_name: string;
  chunk_id: string;
  content: string;
  score: number;
  page: number | null;
  heading: string | null;
  kind?: string;
  knowledge_base_name?: string | null;
  tags?: string[];
  created_at?: string | null;
};

export type Citation = {
  document_id: string;
  document_name: string;
  chunk_id: string;
  page_start: number | null;
  page_end: number | null;
  content: string;
  score: number;
};

export type ConversationMode = "chat" | "knowledge" | "agent" | "report";

export type Conversation = {
  id: string;
  knowledge_base_id: string;
  title: string;
  mode?: ConversationMode;
  updated_at?: string | null;
};

export type AppUser = { id: string; username: string };

export function getMe() {
  return api<AppUser>("/api/auth/me");
}

export function login(username: string, password: string) {
  return api<AppUser>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return api<void>("/api/auth/logout", { method: "POST" });
}

export function messageFromErrorBody(text: string, fallback = "请求失败"): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string };
      if (typeof first?.msg === "string") return first.msg;
    }
  } catch {
    /* keep raw text */
  }
  const trimmed = text.trim();
  if (trimmed && trimmed !== fallback) return trimmed;
  return fallback;
}

const FAILURE_LABELS: Record<string, string> = {
  missing_original: "原文文件缺失，请删除后重新上传",
  empty_content: "文档内容为空",
  invalid_utf8: "文件编码无效",
  parse_timeout: "解析超时",
  no_parsed_markdown: "缺少解析结果",
  no_chunks: "无法生成切片",
  "未配置 Embedding API Key": "未配置 Embedding API Key",
  url_timeout: "URL 抓取超时",
  url_fetch_failed: "URL 抓取失败",
};

export function documentFailureReason(doc: DocumentItem): string {
  if (doc.status !== "index_failed" && doc.status !== "parse_failed") return "—";
  const raw = doc.error_message?.trim();
  if (!raw) return "未知错误";
  if (FAILURE_LABELS[raw]) return FAILURE_LABELS[raw];
  if (raw.startsWith("parse_error:")) return `解析失败：${raw.slice("parse_error:".length)}`;
  if (raw.startsWith("embed_failed:")) return `向量化失败：${raw.slice("embed_failed:".length)}`;
  if (raw.startsWith("index_error:")) return `向量化失败：${raw.slice("index_error:".length)}`;
  return raw;
}

/** @deprecated use documentFailureReason */
export function vectorFailureReason(doc: DocumentItem): string {
  return documentFailureReason(doc);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) {
    throw new Error(messageFromErrorBody(await res.text(), res.statusText));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as T;
}

export function listKnowledgeBases() {
  return api<KnowledgeBase[]>("/api/knowledge-bases");
}

export function createKnowledgeBase(name: string) {
  return api<KnowledgeBase>("/api/knowledge-bases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function updateKnowledgeBase(id: string, body: { name?: string; is_enabled?: boolean }) {
  return api<KnowledgeBase>(`/api/knowledge-bases/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteKnowledgeBase(id: string) {
  return api<void>(`/api/knowledge-bases/${id}`, { method: "DELETE" });
}

export function listDocuments(
  knowledgeBaseId?: string,
  opts?: { favorite?: boolean; tagId?: string },
) {
  const q = new URLSearchParams();
  if (knowledgeBaseId) q.set("knowledge_base_id", knowledgeBaseId);
  if (opts?.favorite) q.set("favorite", "true");
  if (opts?.tagId) q.set("tag_id", opts.tagId);
  const suffix = q.toString() ? `?${q}` : "";
  return api<DocumentItem[]>(`/api/documents${suffix}`);
}

export function listTags() {
  return api<TagItem[]>("/api/tags");
}

export function createTag(name: string) {
  return api<TagItem>("/api/tags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function setDocumentTags(id: string, tagIds: string[]) {
  return api<DocumentItem>(`/api/documents/${id}/tags`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag_ids: tagIds }),
  });
}

export function favoriteDocument(id: string) {
  return api<DocumentItem>(`/api/documents/${id}/favorite`, { method: "POST" });
}

export function unfavoriteDocument(id: string) {
  return api<{ ok: boolean }>(`/api/documents/${id}/favorite`, { method: "DELETE" });
}

export function searchChunks(body: {
  query: string;
  knowledge_base_id?: string;
  tag_id?: string;
  kind?: string;
  k?: number;
  created_after?: string;
  created_before?: string;
}) {
  return api<SearchHit[]>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listConversations(knowledgeBaseId?: string) {
  const q = knowledgeBaseId ? `?knowledge_base_id=${knowledgeBaseId}` : "";
  return api<Conversation[]>(`/api/conversations${q}`);
}

export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  citations?: Citation[] | null;
  plan_html?: {
    html?: string | null;
    url?: string | null;
    key?: string | null;
    note?: string;
    plan_id?: string;
  } | null;
  travel?: Record<string, unknown> | null;
  pending_action?: {
    tool: string;
    args?: Record<string, unknown>;
    summary: string;
    confirmed?: boolean | null;
  } | null;
  bookings?: Array<Record<string, unknown>> | null;
};

export function listMessages(conversationId: string) {
  return api<ChatMessage[]>(`/api/conversations/${conversationId}/messages`);
}

export function patchConversation(
  conversationId: string,
  body: { title?: string; mode?: ConversationMode },
) {
  return api<Conversation>(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function renameConversation(conversationId: string, title: string) {
  return patchConversation(conversationId, { title });
}

export function deleteConversation(conversationId: string) {
  return api<{ ok: boolean }>(`/api/conversations/${conversationId}`, { method: "DELETE" });
}

export function getHealth() {
  return api<{ status: string; ai_configured: boolean; host: string }>("/health");
}

export function createNote(knowledgeBaseId: string, content: string, filename?: string) {
  return api<DocumentItem>("/api/documents/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, filename, knowledge_base_id: knowledgeBaseId }),
  });
}

export function importUrl(knowledgeBaseId: string, url: string) {
  return api<DocumentItem>("/api/documents/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, knowledge_base_id: knowledgeBaseId }),
  });
}

export async function uploadFile(knowledgeBaseId: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  body.append("knowledge_base_id", knowledgeBaseId);
  return api<DocumentItem>("/api/documents/upload", { method: "POST", body });
}

export function reindexDocument(id: string) {
  return api<DocumentItem>(`/api/documents/${id}/reindex`, { method: "POST" });
}

export function deleteDocument(id: string) {
  return api<{ ok: boolean }>(`/api/documents/${id}`, { method: "DELETE" });
}

export function getDocument(id: string) {
  return api<DocumentItem>(`/api/documents/${id}`);
}

export type DocumentChunkMeta = {
  heading: string | null;
  page: number | null;
  level: number | null;
  table: boolean;
  faq: boolean;
};

export type DocumentChunkItem = {
  id: string | null;
  chunk_index: number;
  chunk_label: string | null;
  content: string;
  page: number | null;
  heading: string | null;
  vector_status: "ready" | "indexing" | "pending";
  created_at: string | null;
  quality_labels: string[];
  meta: DocumentChunkMeta | null;
};

export function listDocumentChunks(id: string) {
  return api<DocumentChunkItem[]>(`/api/documents/${id}/chunks`);
}

export function reindexDocumentChunk(documentId: string, chunkId: string) {
  return api<DocumentChunkItem>(`/api/documents/${documentId}/chunks/${chunkId}/reindex`, { method: "POST" });
}

export function chunkVectorStatusLabel(status: string): string {
  if (status === "ready") return "已完成";
  if (status === "indexing") return "向量中";
  if (status === "pending") return "未向量";
  return status;
}

export function summarizeDocument(id: string) {
  return api<DocumentItem>(`/api/documents/${id}/summarize`, { method: "POST" });
}

export function autoTagDocument(id: string) {
  return api<DocumentItem>(`/api/documents/${id}/auto-tags`, { method: "POST" });
}

export type CompareResult = {
  document_id_a: string;
  document_id_b: string;
  comparison: string;
};

export function compareDocuments(documentIdA: string, documentIdB: string) {
  return api<CompareResult>("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id_a: documentIdA, document_id_b: documentIdB }),
  });
}

export function getParsedMarkdown(id: string) {
  return api<string>(`/api/documents/${id}/parsed.md`);
}

export type GraphEntity = { id: string; name: string; type: string; created_at?: string | null; source_doc_count?: number; description?: string | null; confidence?: number | null };
export type GraphLink = { from_id: string; to_id: string; rel: string; document_id: string | null };
export type KnowledgeGraph = { entities: GraphEntity[]; links: GraphLink[] };
export type RelatedDocument = {
  document_id: string;
  document_name: string;
  score: number;
  content: string;
};

export function getKnowledgeGraph(opts: { knowledgeBaseId?: string; documentId?: string }) {
  const q = new URLSearchParams();
  if (opts.knowledgeBaseId) q.set("knowledge_base_id", opts.knowledgeBaseId);
  if (opts.documentId) q.set("document_id", opts.documentId);
  return api<KnowledgeGraph>(`/api/graph?${q}`);
}


export function searchKnowledgeGraph(knowledgeBaseId: string, query: string, k = 20) {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, query, k: String(k) });
  return api<SearchHit[]>(`/api/graph/search?${params}`);
}



export type GraphDocumentOut = { document_id: string; document_name: string; version: number };

export type GraphPathOut = { entities: GraphEntity[]; rels: string[] };

export type GraphSearchDetailOut = {
  query: string;
  entities: GraphEntity[];
  links: GraphLink[];
  documents: SearchHit[];
  paths: GraphPathOut[];
};

export function searchKnowledgeGraphDetails(
  knowledgeBaseId: string,
  query: string,
  depth = 2,
  rel?: string,
  k = 5,
) {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, query, k: String(k), depth: String(depth) });
  if (rel) params.set("rel", rel);
  return api<GraphSearchDetailOut>(`/api/graph/search/details?${params}`);
}

export function getGraphDocuments(ids: string[]) {
  if (!ids.length) return Promise.resolve([] as GraphDocumentOut[]);
  const params = new URLSearchParams();
  ids.forEach((id) => params.append("ids", id));
  return api<GraphDocumentOut[]>(`/api/graph/documents?${params}`);
}


export function extractDocumentGraph(id: string) {
  return api<KnowledgeGraph>(`/api/documents/${id}/graph`, { method: "POST" });
}

export function listRelatedDocuments(id: string) {
  return api<RelatedDocument[]>(`/api/documents/${id}/related`);
}

export function statusLabel(status: string): string {
  if (status === "ready") return "已完成";
  if (status === "parse_failed" || status === "index_failed") return "处理失败";
  return "处理中";
}

export function documentStatusLabel(status: string): string {
  if (status === "pending") return "待处理";
  if (status === "parsing") return "解析中";
  if (status === "parsed") return "待向量化";
  if (status === "indexing") return "向量化中";
  if (status === "ready") return "已完成";
  if (status === "parse_failed") return "解析失败";
  if (status === "index_failed") return "向量化失败";
  return status;
}

export function documentStatusClass(status: string): string {
  if (status === "ready") return "ok";
  if (status === "parse_failed" || status === "index_failed") return "bad";
  if (status === "indexing" || status === "parsing") return "busy";
  return "idle";
}

export type RetrievalDebugRow = {
  rank: number;
  document_id: string;
  document_name: string;
  chunk_id: string;
  score: number;
  vector_rank: number | null;
  vector_score: number | null;
  bm25_rank: number | null;
  bm25_score: number | null;
  rrf_rank: number | null;
  rrf_score: number | null;
  rrf_from_vector: number | null;
  rrf_from_bm25: number | null;
  rerank_rank: number | null;
  rerank_score: number | null;
  final: boolean;
};

export type RetrievalStage = {
  requested_k: number;
  actual_count: number;
  threshold?: number | null;
  k_const?: number | null;
  candidate_count?: number | null;
  model?: string | null;
  rows: RetrievalDebugRow[];
};

export type RetrievalDebugResponse = {
  query: string;
  query_norm: string;
  search_query?: string | null;
  next_action?: "search" | "generate";
  vector: RetrievalStage;
  bm25: RetrievalStage;
  rrf: RetrievalStage;
  rerank: RetrievalStage;
  final: RetrievalDebugRow[];
  candidates: RetrievalDebugRow[];
  evaluation: { k: number; recall: number | null; precision: number | null; relevant_chunk_count: number };
  labels: Record<string, number>;
  timings?: {
    plan_ms: number;
    embed_ms: number;
    vector_ms: number;
    bm25_ms: number;
    rrf_ms: number;
    rerank_ms: number;
    final_ms: number;
    total_ms: number;
  } | null;
};

export type DebugDatasetChunk = {
  chunk_id: string;
  chunk_label: string;
  document_id: string;
  document_name: string;
  knowledge_base_id: string;
  knowledge_base_name: string;
  chunk_index: number;
  content: string;
};

export type RetrievalDebugParams = {
  query: string;
  knowledge_base_id?: string;
  vector_k: number;
  bm25_k: number;
  rrf_k: number;
  rerank_k: number;
  vector_threshold: number;
  rrf_k_const: number;
  eval_k: number;
};

export function runRetrievalDebug(body: RetrievalDebugParams) {
  return api<RetrievalDebugResponse>("/api/retrieval-debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listDebugDatasetChunks() {
  return api<DebugDatasetChunk[]>("/api/retrieval-debug/dataset-chunks");
}

export function listRetrievalLabels(query: string, knowledge_base_id?: string) {
  const params = new URLSearchParams({ query });
  if (knowledge_base_id) params.set("knowledge_base_id", knowledge_base_id);
  return api<{ chunk_id: string; document_id: string; relevance: number }[]>(
    `/api/retrieval-debug/labels?${params}`,
  );
}

export function putRetrievalLabel(body: {
  query: string;
  knowledge_base_id?: string;
  chunk_id: string;
  relevance: number;
}) {
  return api<{ chunk_id: string; document_id: string; relevance: number }>("/api/retrieval-debug/labels", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type ChunkSettings = {
  chunk_size: number;
  chunk_overlap: number;
};

export function getChunkSettings() {
  return api<ChunkSettings>("/api/chunk-settings");
}

export function putChunkSettings(body: ChunkSettings) {
  return api<ChunkSettings>("/api/chunk-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type RagMetrics = {
  faithfulness: number | null;
  answer_relevance: number | null;
  answer_correctness: number | null;
  semantic_similarity: number | null;
};

export type RagEvalCase = {
  query_norm: string;
  knowledge_base_id: string | null;
  gt_answer: string;
};

export function getRagEvalCase(query: string, knowledge_base_id?: string) {
  const params = new URLSearchParams({ query });
  if (knowledge_base_id) params.set("knowledge_base_id", knowledge_base_id);
  return api<RagEvalCase>(`/api/retrieval-debug/eval-cases?${params}`);
}

export function putRagEvalCase(body: { query: string; knowledge_base_id?: string; gt_answer: string }) {
  return api<RagEvalCase>("/api/retrieval-debug/eval-cases", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function computeRagMetrics(body: {
  query: string;
  answer: string;
  contexts: string[];
  gt_answer?: string | null;
}) {
  return api<RagMetrics>("/api/retrieval-debug/rag-metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type AnswerQuality = {
  faithfulness: number;
  relevance: number;
  completeness: number;
  issues: string[];
};

export function judgeAnswerQuality(body: { query: string; answer: string; contexts: string[] }) {
  return api<AnswerQuality>("/api/retrieval-debug/answer-quality", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type AgentTraceStep = {
  type: "step";
  node: "reason" | "run_tool" | "generate" | string;
  elapsed_ms: number;
  action?: string;
  query?: string;
  subtasks?: string[];
  tool?: string;
  hits?: number;
  answer_len?: number;
  tokens?: TokenUsage;
};

export type AgentTraceFinal = {
  type: "final";
  task: string;
  knowledge_base_id: string | null;
  answer: string;
  citations: Citation[];
  loop_count: number;
  tokens?: TokenUsage;
};

export type AgentTraceEvent = AgentTraceStep | AgentTraceFinal;

export type AgentTraceParams = {
  query: string;
  knowledge_base_id?: string;
  task?: "agent" | "report";
  allow_web?: boolean;
};

export async function streamAgentTrace(
  body: AgentTraceParams,
  onEvent: (event: AgentTraceEvent) => void,
): Promise<void> {
  const res = await fetch("/api/agent/trace", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new Error(messageFromErrorBody(await res.text(), res.statusText));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)) as AgentTraceEvent);
    }
  }
}

export type RecommendationItem = {
  document_id: string;
  document_name: string;
  knowledge_base_id: string;
  score: number;
  kind: string;
};

export function listRecommendations() {
  return api<RecommendationItem[]>("/api/recommendations");
}

export type PlanRecordItem = {
  id: string;
  title: string;
  origin: string | null;
  destination: string | null;
  depart_date: string | null;
  trip_type: string;
  nights: number | null;
  conversation_id: string | null;
  url: string | null;
  minio_key: string | null;
  created_at?: string | null;
};

export function listPlans() {
  return api<PlanRecordItem[]>("/api/plans");
}

export type ScheduledTaskItem = {
  id: number;
  name: string;
  task_type: string;
  schedule_type: "INTERVAL" | "CRON";
  schedule_config: Record<string, unknown>;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type TaskTypeItem = {
  task_type: string;
  label: string;
};

export type TaskExecutionItem = {
  id: number;
  task_id: number;
  run_id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at?: string | null;
};

export type TaskWrite = {
  name: string;
  task_type: string;
  schedule_type: "INTERVAL" | "CRON";
  schedule_config: Record<string, unknown>;
  enabled?: boolean;
};

export function listTasks() {
  return api<ScheduledTaskItem[]>("/api/tasks");
}

export function listTaskTypes() {
  return api<TaskTypeItem[]>("/api/tasks/types");
}

export function createTask(body: TaskWrite) {
  return api<ScheduledTaskItem>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateTask(id: number, body: Partial<Omit<TaskWrite, "task_type">>) {
  return api<ScheduledTaskItem>(`/api/tasks/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteTask(id: number) {
  return api<{ ok: boolean }>(`/api/tasks/${id}`, { method: "DELETE" });
}

export function enableTask(id: number) {
  return api<ScheduledTaskItem>(`/api/tasks/${id}/enable`, { method: "POST" });
}

export function disableTask(id: number) {
  return api<ScheduledTaskItem>(`/api/tasks/${id}/disable`, { method: "POST" });
}

export function runTask(id: number) {
  return api<{ execution_id: number; run_id: string }>(`/api/tasks/${id}/run`, { method: "POST" });
}

export function listTaskExecutions(id: number) {
  return api<TaskExecutionItem[]>(`/api/tasks/${id}/executions`);
}
