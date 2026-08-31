import { api } from "./api";

export type ConflictItem = {
  documents: string[];
  point: string;
  detail: string;
  suggestion: string;
};

export type ConflictReport = {
  conflicts: ConflictItem[];
  truncated: boolean;
};

export type GapItem = {
  topic: string;
  evidence: string;
  suggestion: string;
};

export type GapReport = {
  covered_topics: string[];
  gaps: GapItem[];
  truncated: boolean;
};

export function runConflicts(kbId: string) {
  return api<ConflictReport>(`/api/knowledge-bases/${kbId}/insights/conflicts`, {
    method: "POST",
  });
}

export function runGaps(kbId: string) {
  return api<GapReport>(`/api/knowledge-bases/${kbId}/insights/gaps`, {
    method: "POST",
  });
}
export type OrganizeAppliedItem = {
  document: string;
  tags: string[];
};

export type OrganizeReport = {
  applied: OrganizeAppliedItem[];
  applied_tags: boolean;
  duplicates: string[][];
  empty_summary: string[];
  bad_names: string[];
  untagged_total: number;
};

export function runOrganize(kbId: string, applyTags: boolean = true) {
  return api<OrganizeReport>(`/api/knowledge-bases/${kbId}/insights/organize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ apply_tags: applyTags }),
  });
}
