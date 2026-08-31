<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { listKnowledgeBases, type KnowledgeBase } from "../api";
import { runConflicts, runGaps, runOrganize, type ConflictReport, type GapReport, type OrganizeReport } from "../api-insights";

const HISTORY_KEY = "insights-history-v1";
const LEGACY_KEY = "insights-conflicts-v1";
const HISTORY_LIMIT = 20;

type Kind = "conflicts" | "gaps" | "organize";
type HistoryItem =
  | { id: string; kind: "conflicts"; kbId: string; kbName: string; at: number; report: ConflictReport }
  | { id: string; kind: "gaps"; kbId: string; kbName: string; at: number; report: GapReport }
  | { id: string; kind: "organize"; kbId: string; kbName: string; at: number; report: OrganizeReport };

const kbs = ref<KnowledgeBase[]>([]);
const selectedKbId = ref<string>("");
const loadingKind = ref<Kind | "">("");
const error = ref("");
const history = ref<HistoryItem[]>(loadHistory());
const activeId = ref<string | null>(history.value[0]?.id ?? null);

const active = computed(() => history.value.find((h) => h.id === activeId.value) ?? null);
const kbNameMap = computed(() => new Map(kbs.value.map((kb) => [kb.id, kb.name])));
const loading = computed(() => loadingKind.value !== "");

function asHistoryItem(raw: unknown): HistoryItem | null {
  if (!raw || typeof raw !== "object") return null;
  const h = raw as Record<string, unknown>;
  if (!h.id || !h.report || typeof h.report !== "object") return null;
  const report = h.report as Record<string, unknown>;
  const kbId = String(h.kbId || "");
  const base = {
    id: String(h.id),
    kbId,
    kbName: String(h.kbName || ""),
    at: Number(h.at) || 0,
  };
  if (h.kind === "organize" || "applied_tags" in report) {
    const r = report as Record<string, unknown>;
    return {
      ...base,
      kind: "organize",
      report: {
        applied: Array.isArray(r.applied) ? (r.applied as OrganizeReport["applied"]) : [],
        applied_tags: Boolean(r.applied_tags),
        duplicates: Array.isArray(r.duplicates) ? (r.duplicates as string[][]) : [],
        empty_summary: Array.isArray(r.empty_summary) ? (r.empty_summary as string[]) : [],
        bad_names: Array.isArray(r.bad_names) ? (r.bad_names as string[]) : [],
        untagged_total: Number(r.untagged_total) || 0,
      },
    };
  }
  if (h.kind === "gaps" || Array.isArray(report.gaps)) {
    return {
      ...base,
      kind: "gaps",
      report: {
        covered_topics: Array.isArray(report.covered_topics) ? (report.covered_topics as string[]) : [],
        gaps: Array.isArray(report.gaps) ? (report.gaps as GapReport["gaps"]) : [],
        truncated: Boolean(report.truncated),
      },
    };
  }
  return {
    ...base,
    kind: "conflicts",
    report: {
      conflicts: Array.isArray(report.conflicts) ? (report.conflicts as ConflictReport["conflicts"]) : [],
      truncated: Boolean(report.truncated),
    },
  };
}

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY) || localStorage.getItem(LEGACY_KEY);
    if (!raw) return [];
    const rows = JSON.parse(raw) as unknown[];
    return Array.isArray(rows) ? rows.map(asHistoryItem).filter((h): h is HistoryItem => h !== null) : [];
  } catch {
    return [];
  }
}

function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value.slice(0, HISTORY_LIMIT)));
}

function kbLabel(kbId: string, fallback?: string) {
  return kbNameMap.value.get(kbId) || fallback || "知识库";
}

function pushHistory(item: HistoryItem) {
  history.value = [item, ...history.value].slice(0, HISTORY_LIMIT);
  activeId.value = item.id;
  saveHistory();
}

function selectHistory(id: string) {
  activeId.value = id;
  const row = history.value.find((h) => h.id === id);
  if (row) selectedKbId.value = row.kbId;
}

function clearHistory() {
  history.value = [];
  activeId.value = null;
  localStorage.removeItem(HISTORY_KEY);
  localStorage.removeItem(LEGACY_KEY);
}

function historyTitle(item: HistoryItem) {
  if (item.kind === "organize") {
    const first = item.report.applied[0]?.document?.trim();
    if (first) return first;
    return "整理报告";
  }
  if (item.kind === "gaps") {
    const first = item.report.gaps[0]?.topic?.trim();
    if (first) return first;
    return item.report.gaps.length ? "缺口报告" : "未发现缺口";
  }
  const first = item.report.conflicts[0]?.point?.trim();
  if (first) return first;
  return item.report.conflicts.length ? "冲突报告" : "未发现冲突";
}

function historyMeta(item: HistoryItem) {
  const kb = kbLabel(item.kbId, item.kbName);
  if (item.kind === "organize") return `${kb} · ${item.report.applied.length} 个标签应用 · ${timeAgo(item.at)}`;
  if (item.kind === "gaps") return `${kb} · ${item.report.gaps.length} 条缺口 · ${timeAgo(item.at)}`;
  return `${kb} · ${item.report.conflicts.length} 条冲突 · ${timeAgo(item.at)}`;
}

function timeAgo(at: number) {
  const m = Math.floor((Date.now() - at) / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m}分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}小时前`;
  return `${Math.floor(h / 24)}天前`;
}

onMounted(async () => {
  try {
    kbs.value = await listKnowledgeBases();
    if (kbs.value.length && !selectedKbId.value) selectedKbId.value = kbs.value[0].id;
    if (activeId.value) {
      const row = history.value.find((h) => h.id === activeId.value);
      if (row) selectedKbId.value = row.kbId;
    }
  } catch {
    /* ignore */
  }
});

async function analyze(kind: Kind) {
  if (!selectedKbId.value) return;
  loadingKind.value = kind;
  error.value = "";
  try {
    const kbId = selectedKbId.value;
    if (kind === "conflicts") {
      const data = await runConflicts(kbId);
      pushHistory({
        id: crypto.randomUUID(),
        kind: "conflicts",
        kbId,
        kbName: kbLabel(kbId),
        at: Date.now(),
        report: data,
      });
    } else if (kind === "gaps") {
      const data = await runGaps(kbId);
      pushHistory({
        id: crypto.randomUUID(),
        kind: "gaps",
        kbId,
        kbName: kbLabel(kbId),
        at: Date.now(),
        report: data,
      });
    } else {
      const data = await runOrganize(kbId);
      pushHistory({
        id: crypto.randomUUID(),
        kind: "organize",
        kbId,
        kbName: kbLabel(kbId),
        at: Date.now(),
        report: data,
      });
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : "请求失败";
  } finally {
    loadingKind.value = "";
  }
}
</script>

<template>
  <main class="page insights-page">
    <div class="insights-main">
      <div class="page-head">
        <div>
          <h1>知识洞察</h1>
          <p class="sub">检测冲突、分析缺口或自动整理。报告保存在本机浏览器，最多 {{ HISTORY_LIMIT }} 条。</p>
        </div>
      </div>

      <div class="card pad toolbar">
        <div class="form-row">
          <label>知识库</label>
          <select v-model="selectedKbId" class="input">
            <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
          <button class="btn btn-primary" :disabled="loading || !selectedKbId" @click="analyze('conflicts')">
            <span v-if="loadingKind === 'conflicts'">分析中…</span>
            <span v-else>检测冲突</span>
          </button>
          <button class="btn" :disabled="loading || !selectedKbId" @click="analyze('gaps')">
            <span v-if="loadingKind === 'gaps'">分析中…</span>
            <span v-else>分析缺口</span>
          </button>
          <button class="btn" :disabled="loading || !selectedKbId" @click="analyze('organize')">
            <span v-if="loadingKind === 'organize'">整理中…</span>
            <span v-else>自动整理</span>
          </button>
        </div>
        <p v-if="error" class="hint err">{{ error }}</p>
      </div>

      <div v-if="active?.kind === 'conflicts'" class="card pad">
        <h2 class="block-title">冲突检测报告</h2>
        <p v-if="active.report.truncated" class="hint warn">文档数量超过 30 篇，仅分析了最近 30 篇。</p>
        <div v-if="!active.report.conflicts.length" class="empty">未发现冲突</div>
        <div v-for="(item, idx) in active.report.conflicts" :key="idx" class="report-item">
          <div class="report-head">
            <span class="badge">#{{ idx + 1 }}</span>
            <strong>{{ item.point }}</strong>
          </div>
          <div class="report-meta">
            <span class="muted">涉及文档：</span>
            <span v-for="(name, i) in item.documents" :key="i" class="pill">{{ name }}</span>
          </div>
          <p class="report-body">{{ item.detail }}</p>
          <p v-if="item.suggestion" class="report-suggestion">
            <span class="muted">建议：</span>{{ item.suggestion }}
          </p>
        </div>
      </div>

      <div v-else-if="active?.kind === 'organize'" class="card pad">
        <h2 class="block-title">自动整理报告</h2>
        <p v-if="active.report.applied_tags" class="hint">已为 {{ active.report.applied.length }} 篇无标签文档补打标签。</p>
        <p v-else class="hint">本次仅生成报告，未实际修改标签。</p>

        <div v-if="active.report.applied.length" class="report-section">
          <h3 class="block-title">补打标签</h3>
          <div v-for="(item, idx) in active.report.applied" :key="idx" class="report-item">
            <div class="report-head">
              <span class="badge">#{{ idx + 1 }}</span>
              <strong>{{ item.document }}</strong>
            </div>
            <div class="report-meta">
              <span class="muted">标签：</span>
              <span v-for="(tag, i) in item.tags" :key="i" class="pill">{{ tag }}</span>
            </div>
          </div>
        </div>

        <div v-if="active.report.duplicates.length" class="report-section">
          <h3 class="block-title">疑似重复</h3>
          <div v-for="(group, idx) in active.report.duplicates" :key="idx" class="report-item">
            <div class="report-meta">
              <span class="muted">涉及文档：</span>
              <span v-for="(name, i) in group" :key="i" class="pill">{{ name }}</span>
            </div>
          </div>
        </div>

        <div v-if="active.report.empty_summary.length" class="report-section">
          <h3 class="block-title">空摘要文档</h3>
          <div class="report-meta">
            <span v-for="(name, i) in active.report.empty_summary" :key="i" class="pill">{{ name }}</span>
          </div>
        </div>

        <div v-if="active.report.bad_names.length" class="report-section">
          <h3 class="block-title">命名不规范</h3>
          <div class="report-meta">
            <span v-for="(name, i) in active.report.bad_names" :key="i" class="pill">{{ name }}</span>
          </div>
        </div>

        <div v-if="!active.report.applied.length && !active.report.duplicates.length && !active.report.empty_summary.length && !active.report.bad_names.length" class="empty">
          未发现需要整理的问题。
        </div>
      </div>

      <div v-else-if="active?.kind === 'gaps'" class="card pad">
        <h2 class="block-title">知识缺口报告</h2>
        <p v-if="active.report.truncated" class="hint warn">文档数量超过 30 篇，仅分析了最近 30 篇。</p>
        <div v-if="active.report.covered_topics.length" class="report-meta covered">
          <span class="muted">已覆盖：</span>
          <span v-for="(topic, i) in active.report.covered_topics" :key="i" class="pill">{{ topic }}</span>
        </div>
        <div v-if="!active.report.gaps.length" class="empty">未发现缺口</div>
        <div v-for="(item, idx) in active.report.gaps" :key="idx" class="report-item">
          <div class="report-head">
            <span class="badge">#{{ idx + 1 }}</span>
            <strong>{{ item.topic }}</strong>
          </div>
          <p v-if="item.evidence" class="report-body">
            <span class="muted">佐证：</span>{{ item.evidence }}
          </p>
          <p v-if="item.suggestion" class="report-suggestion">
            <span class="muted">建议：</span>{{ item.suggestion }}
          </p>
        </div>
      </div>
      <p v-else-if="!loading" class="empty-main">选择知识库并检测冲突、分析缺口或自动整理，或从右侧历史记录查看。</p>
    </div>

    <aside class="insights-side">
      <section class="card side-card">
        <header class="side-head">
          <h2><span class="side-ico dot"></span> 检测历史</h2>
          <button v-if="history.length" class="side-btn" type="button" @click="clearHistory">清空</button>
        </header>
        <ul v-if="history.length" class="history">
          <li v-for="item in history" :key="item.id">
            <button
              type="button"
              class="history-item"
              :class="{ on: item.id === activeId }"
              @click="selectHistory(item.id)"
            >
              <span class="history-q">
                <span class="kind-tag">{{ item.kind === "gaps" ? "缺口" : item.kind === "organize" ? "整理" : "冲突" }}</span>
                {{ historyTitle(item) }}
              </span>
              <span class="history-meta">{{ historyMeta(item) }}</span>
            </button>
          </li>
        </ul>
        <p v-else class="side-empty">检测后会自动保存在本机，刷新页面仍可查看。</p>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.insights-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem;
  font-size: 12.5px;
  background: transparent;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  box-sizing: border-box;
}
.insights-main {
  flex: 1;
  min-width: 0;
}
.insights-side {
  width: min(17rem, 26vw);
  flex-shrink: 0;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.45rem;
}
.page-head h1 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 0.25rem;
}
.sub {
  font-size: 0.75rem;
  color: var(--muted);
  margin: 0;
}
.block-title {
  font-size: 0.8rem;
  margin: 0 0 0.45rem;
  font-weight: 600;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.form-row label {
  font-size: 0.68rem;
  color: var(--muted);
}
.form-row select {
  min-width: 12rem;
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: inherit;
  background: var(--card);
}
.hint {
  font-size: 0.75rem;
  margin: 0.3rem 0 0;
}
.empty,
.empty-main {
  color: var(--muted);
  font-size: 0.75rem;
  padding: 1rem 0;
}
.empty-main {
  padding-left: 0.15rem;
}
.report-item {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.8rem 1rem;
  margin-bottom: 0.6rem;
  background: var(--card);
}
.report-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.35rem;
}
.badge {
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  border-radius: 6px;
  font-weight: 600;
}
.report-meta {
  margin-bottom: 0.3rem;
}
.report-meta.covered {
  margin-bottom: 0.7rem;
}
.pill {
  display: inline-block;
  background: #eef1f4;
  color: var(--muted);
  font-size: 0.68rem;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  margin-right: 0.3rem;
}
.report-body {
  font-size: 0.72rem;
  line-height: 1.5;
  margin: 0 0 0.3rem;
  color: var(--text);
}
.report-suggestion {
  font-size: 0.72rem;
  line-height: 1.5;
  margin: 0;
  color: var(--text);
}
.muted {
  color: var(--muted);
}
.toolbar {
  margin-bottom: 1rem;
}
.hint.err {
  color: var(--danger);
}
.hint.warn {
  color: var(--warn);
}
.kind-tag {
  display: inline-block;
  font-size: 0.62rem;
  font-weight: 600;
  color: var(--teal);
  background: var(--teal-soft);
  padding: 0.05rem 0.3rem;
  border-radius: 4px;
  margin-right: 0.25rem;
  vertical-align: middle;
}
.side-card {
  padding: 0.9rem 1rem;
}
.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
}
.side-head h2 {
  margin: 0;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.side-ico.dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--teal);
  display: inline-block;
}
.side-btn {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 0.75rem;
  cursor: pointer;
}
.side-btn:hover {
  color: var(--teal);
}
.history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.history-item {
  width: 100%;
  border: none;
  background: none;
  text-align: left;
  padding: 0.45rem;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}
.history-item:hover {
  background: #f1f5f9;
}
.history-item.on {
  background: var(--teal-soft);
}
.history-q {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-meta {
  color: var(--muted);
  font-size: 0.7rem;
}
.side-empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.45;
}
@media (max-width: 900px) {
  .insights-page {
    flex-direction: column;
  }
  .insights-side {
    width: 100%;
  }
}
</style>
