export type KnowledgeBase = {
  id: string;
  name: string;
  is_default: boolean;
  is_enabled: boolean;
  created_at?: string | null;
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
  chunk_size?: number;
  chunk_overlap?: number;
};

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

export type Conversation = { id: string; knowledge_base_id: string; title: string };

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
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* keep raw text */
  }
  return text || fallback;
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
};

export function listMessages(conversationId: string) {
  return api<ChatMessage[]>(`/api/conversations/${conversationId}/messages`);
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

export type GraphEntity = { id: string; name: string; type: string };
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
  vector: RetrievalStage;
  bm25: RetrievalStage;
  rrf: RetrievalStage;
  rerank: RetrievalStage;
  final: RetrievalDebugRow[];
  candidates: RetrievalDebugRow[];
  evaluation: { k: number; recall: number | null; precision: number | null; relevant_doc_count: number };
  labels: Record<string, number>;
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

export function putRetrievalLabel(body: {
  query: string;
  knowledge_base_id?: string;
  document_id: string;
  relevance: number;
}) {
  return api<{ document_id: string; relevance: number }>("/api/retrieval-debug/labels", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
