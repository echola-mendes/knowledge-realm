export type KnowledgeBase = {
  id: string;
  name: string;
  is_default: boolean;
};

export type DocumentItem = {
  id: string;
  knowledge_base_id: string;
  filename: string;
  kind: string;
  status: string;
  error_message: string | null;
  source_url: string | null;
  tag_ids: string[];
  is_favorite: boolean;
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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
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

export function listDocuments(
  knowledgeBaseId: string,
  opts?: { favorite?: boolean; tagId?: string },
) {
  const q = new URLSearchParams({ knowledge_base_id: knowledgeBaseId });
  if (opts?.favorite) q.set("favorite", "true");
  if (opts?.tagId) q.set("tag_id", opts.tagId);
  return api<DocumentItem[]>(`/api/documents?${q}`);
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

export function getParsedMarkdown(id: string) {
  return api<string>(`/api/documents/${id}/parsed.md`);
}

export function statusLabel(status: string): string {
  if (status === "ready") return "已完成";
  if (status === "parse_failed" || status === "index_failed") return "处理失败";
  return "处理中";
}
