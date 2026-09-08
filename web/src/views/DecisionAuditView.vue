<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getDecision,
  listDecisions,
  type DecisionRunDetailItem,
  type DecisionRunItem,
} from "../api";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const error = ref("");
const runs = ref<DecisionRunItem[]>([]);
const detail = ref<DecisionRunDetailItem | null>(null);
const expanded = ref<Set<string>>(new Set());

const filterMode = ref("");
const filterStatus = ref("");
const filterConversation = ref("");
const filterStart = ref("");
const filterEnd = ref("");
const page = ref(0);
const LIMIT = 50;

const runId = computed(() => {
  const id = route.params.id;
  return typeof id === "string" ? id : "";
});

const MODE_LABELS: Record<string, string> = { chat: "Chat", knowledge: "知识 Agent" };
const NODE_LABELS: Record<string, string> = { route: "路由", retrieve: "检索", generate: "生成" };
const ASSEMBLY_LABELS: Record<string, string> = {
  child_only: "单块",
  parent: "父块",
  heading_expand: "同节扩窗",
  expanded: "扩窗",
};

function modeLabel(mode: string): string {
  return MODE_LABELS[mode] ?? mode;
}

function nodeLabel(nodeType: string): string {
  return NODE_LABELS[nodeType] ?? nodeType;
}

function assemblyLabel(kind: unknown): string {
  if (typeof kind !== "string") return "";
  return ASSEMBLY_LABELS[kind] ?? kind;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("zh-CN", { hour12: false });
}

function statusClass(status: string): string {
  if (status === "success") return "st-ok";
  if (status === "failed") return "st-err";
  return "st-warn";
}

function statusLabel(status: string): string {
  if (status === "success") return "成功";
  if (status === "failed") return "失败";
  return "进行中";
}

function truncate(text: string, max = 60): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function excerptOf(item: Record<string, unknown>): string {
  if (typeof item.original_excerpt === "string" && item.original_excerpt) {
    return item.original_excerpt;
  }
  if (typeof item.excerpt === "string") {
    return item.excerpt;
  }
  return "";
}

function contextExcerptOf(item: Record<string, unknown>): string {
  if (typeof item.excerpt === "string") {
    return item.excerpt;
  }
  return "";
}

async function loadList() {
  loading.value = true;
  error.value = "";
  try {
    runs.value = await listDecisions({
      mode: filterMode.value || undefined,
      status: filterStatus.value || undefined,
      conversation_id: filterConversation.value.trim() || undefined,
      start: filterStart.value || undefined,
      end: filterEnd.value || undefined,
      limit: LIMIT,
      offset: page.value * LIMIT,
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function loadDetail() {
  loading.value = true;
  error.value = "";
  detail.value = null;
  try {
    detail.value = await getDecision(runId.value);
    expanded.value = new Set(detail.value?.spans.map((span) => span.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function toggle(spanId: string) {
  const next = new Set(expanded.value);
  if (next.has(spanId)) {
    next.delete(spanId);
  } else {
    next.add(spanId);
  }
  expanded.value = next;
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function openDetail(run: DecisionRunItem) {
  router.push(`/monitoring/decisions/${run.id}`);
}

function backToList() {
  router.push("/monitoring/decisions");
}

function applyFilters() {
  page.value = 0;
  void loadList();
}

onMounted(() => {
  if (runId.value) {
    void loadDetail();
  } else {
    void loadList();
  }
});

watch(runId, (id) => {
  expanded.value = new Set();
  if (id) {
    void loadDetail();
  } else {
    void loadList();
  }
});
</script>

<template>
  <main v-if="runId" class="page docs-page">
    <div class="page-head">
      <div>
        <h1>决策链详情</h1>
        <p class="sub">该轮回答的路由、检索证据、上下文组装与生成摘要。</p>
      </div>
      <div class="toolbar-actions">
        <button class="btn" type="button" @click="backToList">返回列表</button>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>
    <p v-else-if="loading" class="hint">加载中…</p>

    <template v-if="detail">
      <section class="card pad run-meta">
        <dl>
          <div><dt>模式</dt><dd>{{ modeLabel(detail.mode) }}</dd></div>
          <div><dt>状态</dt><dd :class="statusClass(detail.status)">{{ statusLabel(detail.status) }}</dd></div>
          <div><dt>时间</dt><dd>{{ formatTime(detail.created_at) }}</dd></div>
          <div><dt>问题</dt><dd>{{ detail.query }}</dd></div>
        </dl>
      </section>

      <section class="span-flow">
        <article
          v-for="span in detail.spans"
          :key="span.id"
          class="card pad span-card"
        >
          <button class="span-head" type="button" @click="toggle(span.id)">
            <span class="seq">{{ span.seq }}</span>
            <strong>{{ nodeLabel(span.node_type) }}</strong>
            <span class="muted">{{ span.rationale || "—" }}</span>
            <span class="arrow">{{ expanded.has(span.id) ? "▾" : "▸" }}</span>
          </button>
          <div v-if="expanded.has(span.id)" class="span-body">
            <div v-if="span.decision" class="span-block">
              <h4>决策</h4>
              <pre>{{ pretty(span.decision) }}</pre>
            </div>
            <div v-if="span.rationale" class="span-block">
              <h4>理由</h4>
              <p>{{ span.rationale }}</p>
            </div>
            <div v-if="span.evidence_refs && span.evidence_refs.length" class="span-block">
              <h4>证据（{{ span.evidence_refs.length }}）</h4>
              <ul class="evidence">
                <li v-for="(item, i) in span.evidence_refs" :key="i" class="evidence-item">
                  <div class="evidence-head">
                    <span class="ev-type">{{ item.type }}</span>
                    <span v-if="item.assembly" class="ev-assembly">{{ assemblyLabel(item.assembly) }}</span>
                    <code>{{ item.id }}</code>
                    <em v-if="typeof item.score === 'number'">score {{ item.score }}</em>
                    <span v-if="item.document_name" class="muted">{{ item.document_name }}</span>
                  </div>
                  <p v-if="excerptOf(item)" class="ev-excerpt"><strong>命中块：</strong>{{ excerptOf(item) }}</p>
                  <p
                    v-if="contextExcerptOf(item) && contextExcerptOf(item) !== excerptOf(item)"
                    class="ev-excerpt"
                  >
                    <strong>送入 LLM：</strong>{{ contextExcerptOf(item) }}
                  </p>
                  <p v-if="typeof item.context_chars === 'number'" class="ev-meta muted">
                    上下文 {{ item.context_chars }} 字
                  </p>
                </li>
              </ul>
            </div>
            <div v-if="span.metrics" class="span-block">
              <h4>指标</h4>
              <pre>{{ pretty(span.metrics) }}</pre>
            </div>
          </div>
        </article>
        <p v-if="!detail.spans.length" class="hint">该轮没有记录到决策节点。</p>
      </section>
    </template>
  </main>

  <main v-else class="page docs-page">
    <div class="page-head">
      <div>
        <h1>决策审计</h1>
        <p class="sub">每轮 AI 回答的决策链：路由、证据与生成摘要。</p>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <section class="card pad toolbar">
      <div class="filters">
        <label>
          模式
          <select v-model="filterMode" @change="applyFilters">
            <option value="">全部</option>
            <option value="chat">Chat</option>
            <option value="knowledge">知识 Agent</option>
          </select>
        </label>
        <label>
          状态
          <select v-model="filterStatus" @change="applyFilters">
            <option value="">全部</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="running">进行中</option>
          </select>
        </label>
        <label>
          会话 ID
          <input v-model="filterConversation" placeholder="conversation_id" @keydown.enter="applyFilters" />
        </label>
        <label>
          从
          <input v-model="filterStart" type="date" @change="applyFilters" />
        </label>
        <label>
          至
          <input v-model="filterEnd" type="date" @change="applyFilters" />
        </label>
      </div>
      <div class="toolbar-actions">
        <button class="btn btn-primary" type="button" @click="applyFilters">查询</button>
      </div>
    </section>

    <section class="card pad list-card">
      <p v-if="loading" class="hint">加载中…</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>模式</th>
              <th>问题摘要</th>
              <th>状态</th>
              <th class="ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!runs.length">
              <td colspan="5" class="empty">还没有决策链记录。</td>
            </tr>
            <tr v-for="run in runs" :key="run.id">
              <td>{{ formatTime(run.created_at) }}</td>
              <td>{{ modeLabel(run.mode) }}</td>
              <td>{{ truncate(run.query) }}</td>
              <td><span :class="statusClass(run.status)">{{ statusLabel(run.status) }}</span></td>
              <td class="ops">
                <button class="btn btn-text" type="button" @click="openDetail(run)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="runs.length === LIMIT" class="pager">
        <button class="btn" type="button" @click="page += 1; loadList()">下一页</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.docs-page {
  width: 100%;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  box-sizing: border-box;
}
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}
.page-head h1 {
  margin: 0 0 0.2rem;
  font-size: 1.15rem;
  color: var(--text);
}
.page-head .sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.78rem;
}
.hint {
  color: var(--muted);
  margin: 0;
}
.hint.err {
  color: var(--danger);
}
.toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.filters {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  align-items: flex-end;
}
.filters label {
  display: grid;
  gap: 0.2rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.filters input,
.filters select {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.32rem 0.5rem;
  font: inherit;
  color: var(--text);
  background: var(--card);
  min-width: 8rem;
}
.filters input[type="date"] {
  min-width: 0;
}
.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}
.table-wrap table {
  width: 100%;
  border-collapse: collapse;
}
.table-wrap th,
.table-wrap td {
  text-align: left;
  padding: 0.45rem 0.5rem;
  border-bottom: 1px solid var(--line);
}
.table-wrap th {
  color: var(--muted);
  font-weight: 600;
  font-size: 0.72rem;
}
.table-wrap td.empty {
  color: var(--muted);
  text-align: center;
  padding: 1.2rem 0;
}
.ops {
  text-align: right;
}
.btn-text {
  border: none;
  background: transparent;
  color: var(--teal);
  cursor: pointer;
  padding: 0;
  font: inherit;
}
.btn-text:hover {
  text-decoration: underline;
}
.st-ok {
  color: var(--ok);
  font-weight: 600;
}
.st-err {
  color: var(--danger);
  font-weight: 600;
}
.st-warn {
  color: var(--warn);
  font-weight: 600;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5rem;
}
.run-meta dl {
  margin: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.3rem 0.8rem;
}
.run-meta dt {
  color: var(--muted);
}
.run-meta dd {
  margin: 0;
  color: var(--text);
}
.span-flow {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.span-card {
  padding: 0;
}
.span-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.75rem;
  background: transparent;
  border: none;
  font: inherit;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  box-sizing: border-box;
}
.span-head:hover {
  background: #f8fafc;
}
.span-head .seq {
  width: 1.3rem;
  height: 1.3rem;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.7rem;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.span-head .muted {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.span-head .arrow {
  color: #94a3b8;
}
.span-body {
  border-top: 1px solid var(--line);
  padding: 0.6rem 0.75rem 0.75rem;
  display: grid;
  gap: 0.6rem;
}
.span-block h4 {
  margin: 0 0 0.25rem;
  font-size: 0.72rem;
  color: var(--muted);
  font-weight: 600;
}
.span-block p {
  margin: 0;
}
.span-block pre {
  margin: 0;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.45rem 0.6rem;
  font-size: 0.72rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.evidence {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.5rem;
}
.evidence-item {
  display: grid;
  gap: 0.2rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px dashed var(--line);
}
.evidence-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.evidence-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.evidence .ev-type {
  background: var(--chrome);
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-size: 0.68rem;
  color: var(--muted);
}
.ev-assembly {
  background: #ecfeff;
  color: #0e7490;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-size: 0.68rem;
}
.evidence code {
  font-size: 0.7rem;
  color: var(--teal);
  word-break: break-all;
}
.evidence em {
  color: var(--muted);
  font-style: normal;
  font-size: 0.7rem;
}
.ev-excerpt {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text);
  line-height: 1.35;
}
.ev-meta {
  margin: 0;
  font-size: 0.68rem;
}
.muted {
  color: var(--muted);
}
</style>
