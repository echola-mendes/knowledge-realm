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
};

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

export function listDocuments(knowledgeBaseId: string) {
  const q = new URLSearchParams({ knowledge_base_id: knowledgeBaseId });
  return api<DocumentItem[]>(`/api/documents?${q}`);
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
