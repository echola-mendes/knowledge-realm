<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  chunkVectorStatusLabel,
  deleteDocument,
  getDocument,
  listDocumentChunks,
  reindexDocumentChunk,
  type DocumentChunkItem,
  type DocumentItem,
} from "../api";

const route = useRoute();
const router = useRouter();
const docId = computed(() => String(route.params.id || ""));
const doc = ref<DocumentItem | null>(null);
const chunks = ref<DocumentChunkItem[]>([]);
const error = ref("");
const reindexingIds = ref<Set<string>>(new Set());
const pageSize = 20;
const page = ref(1);
let timer: number | undefined;

const pageCount = computed(() => Math.max(1, Math.ceil(chunks.value.length / pageSize)));
const pagedChunks = computed(() => {
  const start = (page.value - 1) * pageSize;
  return chunks.value.slice(start, start + pageSize);
});

const needsPoll = computed(
  () =>
    reindexingIds.value.size > 0 ||
    doc.value?.status === "indexing" ||
    doc.value?.status === "parsing" ||
    chunks.value.some((c) => c.vector_status === "indexing" || c.vector_status === "pending"),
);

function displayTitle(filename: string) {
  return filename.replace(/\.[^.]+$/, "");
}

function formatTime(raw?: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.replace("T", " ").slice(0, 19);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function chunkPreview(content: string, limit = 80) {
  const text = content.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function charCount(content: string) {
  return [...content].length;
}

function rowKey(c: DocumentChunkItem) {
  return c.id || `preview-${c.chunk_index}`;
}

function statusClass(status: string) {
  if (status === "ready") return "ok";
  if (status === "indexing") return "busy";
  return "idle";
}

function chunkBusy(c: DocumentChunkItem) {
  return Boolean(c.id && reindexingIds.value.has(c.id));
}

function chunkReindexLabel(c: DocumentChunkItem) {
  if (chunkBusy(c)) return "处理中";
  if (c.vector_status === "indexing") return "重试向量化";
  if (c.vector_status === "pending") return "向量化";
  return "向量化";
}

async function refresh() {
  if (!docId.value) return;
  doc.value = await getDocument(docId.value);
  chunks.value = await listDocumentChunks(docId.value);
}

async function onReindexChunk(c: DocumentChunkItem) {
  if (!doc.value || !c.id || chunkBusy(c)) return;
  reindexingIds.value = new Set([...reindexingIds.value, c.id]);
  try {
    await reindexDocumentChunk(doc.value.id, c.id);
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    const next = new Set(reindexingIds.value);
    next.delete(c.id);
    reindexingIds.value = next;
  }
}

async function onDelete() {
  if (!doc.value) return;
  await deleteDocument(doc.value.id);
  await router.push("/documents");
}

onMounted(() => {
  refresh().catch((e: Error) => {
    error.value = e.message;
  });
  timer = window.setInterval(() => {
    if (needsPoll.value) refresh().catch(() => undefined);
  }, 2000);
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});

watch(docId, () => {
  page.value = 1;
  error.value = "";
  reindexingIds.value = new Set();
  refresh().catch((e: Error) => {
    error.value = e.message;
  });
});

watch(pageCount, (n) => {
  if (page.value > n) page.value = n;
});
</script>

<template>
  <main class="page docs-page">
    <div class="page-head">
      <div>
        <h1 class="crumb-title">
          <RouterLink class="crumb-link" to="/documents">文档</RouterLink>
          <span class="crumb-sep" aria-hidden="true">›</span>
          <span v-if="doc">{{ displayTitle(doc.filename) }}</span>
          <span v-else>…</span>
          <span class="crumb-sep" aria-hidden="true">›</span>
          <span>切片</span>
        </h1>
        <p v-if="doc" class="sub">共 {{ chunks.length }} 条切片</p>
        <p v-else class="sub">加载文档信息…</p>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <section class="card pad list-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>序号</th>
              <th>编号</th>
              <th>切片</th>
              <th>字符数</th>
              <th>状态</th>
              <th>创建时间</th>
              <th class="ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in pagedChunks" :key="rowKey(c)">
              <td class="seq">{{ (page - 1) * pageSize + i + 1 }}</td>
              <td class="label-cell">{{ c.chunk_label || "—" }}</td>
              <td class="chunk-cell">
                <span class="chunk-text" :title="c.content.length > 80 ? c.content : undefined">{{
                  chunkPreview(c.content)
                }}</span>
              </td>
              <td class="num-cell">{{ charCount(c.content) }}</td>
              <td class="status-cell">
                <span class="pill status-pill" :class="statusClass(c.vector_status)">
                  {{ chunkVectorStatusLabel(c.vector_status) }}
                </span>
              </td>
              <td>{{ formatTime(c.created_at) }}</td>
              <td class="ops">
                <button
                  class="btn-link reindex-btn"
                  type="button"
                  :disabled="!c.id || chunkBusy(c)"
                  @click="onReindexChunk(c)"
                >
                  {{ chunkReindexLabel(c) }}
                </button>
                <button class="btn-danger" type="button" @click="onDelete">删除</button>
              </td>
            </tr>
            <tr v-if="!chunks.length">
              <td colspan="7" class="empty">暂无切片。文档解析或向量化完成后会在此展示。</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="chunks.length" class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="page -= 1">上一页</button>
        <span>{{ page }} / {{ pageCount }}</span>
        <button class="btn" type="button" :disabled="page >= pageCount" @click="page += 1">下一页</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.docs-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  background: transparent;
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.docs-page .btn {
  padding: 0.5rem 0.85rem;
  border-radius: 10px;
  font-size: inherit;
  cursor: pointer;
}
.docs-page .page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.45rem;
  flex-shrink: 0;
}
.docs-page .hint {
  flex-shrink: 0;
}
.crumb-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.3;
  color: var(--text);
}
.crumb-link {
  color: var(--teal);
  text-decoration: none;
  font-weight: 700;
}
.crumb-link:hover {
  text-decoration: underline;
}
.crumb-sep {
  color: var(--muted);
  font-weight: 500;
}
.ops {
  text-align: left;
  white-space: nowrap;
  width: 1%;
  vertical-align: middle;
}
td.ops {
  display: flex;
  gap: 0.35rem;
  align-items: center;
  justify-content: flex-start;
}
.ops > * {
  flex-shrink: 0;
}
.ops .reindex-btn {
  display: inline-block;
  min-width: 3em;
  text-align: left;
}
.ops .btn-link:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  text-decoration: none;
}
.hint {
  color: var(--muted);
  font-size: 0.75rem;
}
.hint.err {
  color: var(--danger);
}
.pad {
  padding: 1rem 1.1rem;
}
.list-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-bottom: 0;
}
.list-card .table-wrap {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: auto;
  max-width: 100%;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.45rem;
  margin-top: 0.55rem;
  flex-shrink: 0;
  color: var(--muted);
}
.pager .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
.list-card th,
.list-card td {
  padding: 0.4rem 0.45rem;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  vertical-align: middle;
  text-align: left;
}
.list-card th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--card);
  color: var(--muted);
  font-weight: 500;
}
.list-card tbody td {
  min-height: 36px;
  padding-top: 0.55rem;
  padding-bottom: 0.55rem;
  line-height: 1.45;
  box-sizing: border-box;
}
tbody tr:nth-child(odd) {
  background: var(--card);
}
tbody tr:nth-child(even) {
  background: var(--bg);
}
.seq {
  color: var(--muted);
  width: 2.2rem;
}
.label-cell {
  font-family: ui-monospace, monospace;
  font-weight: 600;
  color: var(--teal);
}
.chunk-cell {
  max-width: 28rem;
  white-space: nowrap;
}
.chunk-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}
.num-cell {
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.status-cell .status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  margin: 0;
  padding: 0.08rem 0.45rem;
  font-size: 0.62rem;
  line-height: 1.45;
  cursor: default;
}
.pill.ok {
  background: #ecfdf5;
  color: #059669;
}
.pill.busy {
  background: #fff7ed;
  color: #ea580c;
}
.pill.idle {
  background: #f3f4f6;
  color: #6b7280;
}
.empty {
  color: var(--muted);
  text-align: left;
}
</style>
