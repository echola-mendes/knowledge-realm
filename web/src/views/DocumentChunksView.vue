<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  chunkVectorStatusLabel,
  deleteDocument,
  getDocument,
  getParsedMarkdown,
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

const detailModal = ref(false);
const detailChunk = ref<DocumentChunkItem | null>(null);
const mdText = ref("");
const mdLoading = ref(false);
const mdError = ref("");
let mdLoaded = false;

const mdHighlight = computed(() => {
  if (!detailChunk.value) return "";
  return detailChunk.value.content.replace(/\s+/g, " ").trim().slice(0, 60);
});

async function openDetail(c: DocumentChunkItem) {
  detailChunk.value = c;
  detailModal.value = true;
  await loadMd();
  await nextTick();
  scrollToMdHit();
}

async function loadMd() {
  if (mdLoaded) return;
  mdLoading.value = true;
  mdError.value = "";
  try {
    mdText.value = await getParsedMarkdown(docId.value);
    mdLoaded = true;
  } catch (e) {
    mdError.value = e instanceof Error ? e.message : String(e);
  } finally {
    mdLoading.value = false;
  }
}

function scrollToMdHit() {
  document.querySelector(".detail-md-body mark.md-hit")?.scrollIntoView({ block: "center" });
}

function scrollToLocateHit() {
  document.querySelector(".locate-body mark.md-hit")?.scrollIntoView({ block: "center" });
}

const mdModal = ref(false);
const locateChunk = ref<DocumentChunkItem | null>(null);

async function openLocate(c: DocumentChunkItem) {
  locateChunk.value = c;
  mdModal.value = true;
  await loadMd();
  await nextTick();
  scrollToLocateHit();
}

function normIndexMap(text: string) {
  let norm = "";
  const map: number[] = [];
  let prevSpace = true;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      if (!prevSpace) {
        norm += " ";
        map.push(i);
        prevSpace = true;
      }
    } else {
      norm += ch;
      map.push(i);
      prevSpace = false;
    }
  }
  return { norm, map };
}

const locateSegments = computed(() => {
  const text = mdText.value;
  const c = locateChunk.value;
  if (!text || !c) return [];
  const { norm, map } = normIndexMap(text);
  const key = c.content.replace(/\s+/g, " ").trim();
  const idxN = norm.indexOf(key);
  if (idxN < 0) return [{ text, hit: false }];
  const idx = map[idxN];
  const lastMap = map[Math.min(idxN + key.length - 1, map.length - 1)];
  const end = Math.min(text.length, lastMap + 1);
  const heads = [...text.matchAll(/^## Page \d+[^\n]*$/gm)].map((m) => ({ index: m.index ?? 0 }));
  let start = 0;
  let stop = text.length;
  if (heads.length) {
    for (const h of heads) {
      if (h.index <= idx) start = h.index;
      else {
        stop = h.index;
        break;
      }
    }
    if (end > stop) {
      const firstStop = stop;
      let stop2 = text.length;
      for (const h of heads) {
        if (h.index > firstStop) {
          stop2 = h.index;
          break;
        }
      }
      stop = stop2;
    }
  } else {
    start = Math.max(0, idx - 200);
    stop = Math.min(text.length, end + 200);
  }
  const hitEnd = Math.min(end, stop);
  const segs = [{ text: text.slice(start, idx), hit: false }, { text: text.slice(idx, hitEnd), hit: true }];
  if (hitEnd < stop) segs.push({ text: text.slice(hitEnd, stop), hit: false });
  return segs;
});

function detailIndex() {
  if (!detailChunk.value) return -1;
  return chunks.value.findIndex((c) => rowKey(c) === rowKey(detailChunk.value!));
}

function neighborChunk(offset: -1 | 1) {
  const idx = detailIndex();
  if (idx < 0) return null;
  return chunks.value[idx + offset] ?? null;
}

const prevChunk = computed(() => neighborChunk(-1));
const nextChunk = computed(() => neighborChunk(1));

function neighborText(c: DocumentChunkItem | null) {
  if (!c) return "";
  const text = c.content.replace(/\s+/g, " ").trim();
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

const Q_LABEL_CLASS: Record<string, string> = {
  正常: "q-ok",
  过短切片: "q-warn",
  超长切片: "q-warn",
  疑似断句: "q-warn",
  残缺表格: "q-bad",
};

function qClass(label: string) {
  return Q_LABEL_CLASS[label] || "q-warn";
}

function levelTag(level: number | null) {
  if (level === 1) return "H1";
  if (level === 2) return "H2";
  if (level === 3) return "H3";
  return "";
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
  mdLoaded = false;
  mdText.value = "";
  detailModal.value = false;
  detailChunk.value = null;
  mdModal.value = false;
  locateChunk.value = null;
  refresh().catch((e: Error) => {
    error.value = e.message;
  });
});

watch(pageCount, (n) => {
  if (page.value > n) page.value = n;
});

const mdSegments = computed(() => {
  const text = mdText.value;
  const key = mdHighlight.value;
  if (!text) return [];
  if (!key) return [{ text, hit: false }];
  const idx = text.replace(/\s+/g, " ").indexOf(key);
  if (idx < 0) return [{ text, hit: false }];
  const start = Math.max(0, idx - 200);
  return [
    { text: text.slice(start, idx), hit: false },
    { text: text.slice(idx, idx + 240), hit: true },
    { text: text.slice(idx + 240, idx + 2440), hit: false },
  ];
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
              <th>元数据</th>
              <th>质量标签</th>
              <th>原文位置</th>
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
                <span
                  class="chunk-text clickable"
                  :title="c.content.length > 80 ? c.content : undefined"
                  role="button"
                  tabindex="0"
                  @click="openDetail(c)"
                  @keydown.enter="openDetail(c)"
                >{{
                  chunkPreview(c.content)
                }}</span>
              </td>
              <td class="num-cell">{{ charCount(c.content) }}</td>
              <td class="meta-cell">
                <span v-if="c.meta?.heading" class="meta-heading">
                  <em v-if="levelTag(c.meta.level)" class="lv-tag">{{ levelTag(c.meta.level) }}</em>
                  <span class="meta-heading-text" :title="c.meta.heading">{{ c.meta.heading }}</span>
                </span>
                <span v-else class="meta-none">—</span>
                <span class="meta-sub">
                  页码：{{ c.meta?.page ?? c.page ?? "—" }}
                  <em v-if="c.meta?.table" class="meta-flag">表格保护</em>
                  <em v-if="c.meta?.faq" class="meta-flag">FAQ合并</em>
                </span>
              </td>
              <td class="quality-cell">
                <span
                  v-for="label in c.quality_labels?.length ? c.quality_labels : ['正常']"
                  :key="label"
                  class="pill q-pill"
                  :class="qClass(label)"
                >
                  {{ label }}
                </span>
              </td>
              <td class="md-cell">
                <button class="btn-link md-btn" type="button" @click="openLocate(c)">定位</button>
              </td>
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
              <td colspan="10" class="empty">暂无切片。文档解析或向量化完成后会在此展示。</td>
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

    <div v-if="detailModal && detailChunk" class="detail-mask" @click.self="detailModal = false">
      <div class="detail-modal">
        <header class="detail-head">
          <h3>
            切片详情
            <span class="detail-label">{{ detailChunk.chunk_label || `预览 #${detailChunk.chunk_index + 1}` }}</span>
          </h3>
          <button class="btn" type="button" @click="detailModal = false">关闭</button>
        </header>

        <div class="detail-meta">
          <span><em class="meta-k">序号</em>{{ detailChunk.chunk_index + 1 }}</span>
          <span><em class="meta-k">字符数</em>{{ charCount(detailChunk.content) }}</span>
          <span><em class="meta-k">向量状态</em>{{ chunkVectorStatusLabel(detailChunk.vector_status) }}</span>
          <span><em class="meta-k">创建时间</em>{{ formatTime(detailChunk.created_at) }}</span>
          <span>
            <em class="meta-k">章节</em>
            <template v-if="detailChunk.meta?.heading">
              <em v-if="levelTag(detailChunk.meta.level)" class="lv-tag">{{ levelTag(detailChunk.meta.level) }}</em>
              {{ detailChunk.meta.heading }}
            </template>
            <template v-else>—</template>
          </span>
          <span><em class="meta-k">页码</em>{{ detailChunk.meta?.page ?? detailChunk.page ?? "—" }}</span>
          <span>
            <em class="meta-k">特殊标记</em>
            <template v-if="detailChunk.meta?.table || detailChunk.meta?.faq">
              <em v-if="detailChunk.meta?.table" class="meta-flag">表格保护</em>
              <em v-if="detailChunk.meta?.faq" class="meta-flag">FAQ合并</em>
            </template>
            <template v-else>无</template>
          </span>
          <span>
            <em class="meta-k">质量标签</em>
            <em
              v-for="label in detailChunk.quality_labels?.length ? detailChunk.quality_labels : ['正常']"
              :key="label"
              class="pill q-pill"
              :class="qClass(label)"
            >
              {{ label }}
            </em>
          </span>
        </div>

        <section class="detail-sec">
          <h4>完整内容</h4>
          <div class="detail-content">{{ detailChunk.content }}</div>
        </section>

        <section class="detail-sec">
          <h4>上下文预览</h4>
          <div class="detail-ctx">
            <div class="ctx-card" :class="{ none: !prevChunk }">
              <span class="ctx-title">
                前一段{{ prevChunk ? `（${prevChunk.chunk_label || `#${prevChunk.chunk_index + 1}`}）` : "" }}
              </span>
              <p v-if="prevChunk" class="ctx-text" role="button" @click="openDetail(prevChunk)">{{ neighborText(prevChunk) }}</p>
              <p v-else class="ctx-text muted">无（已是第一条切片）</p>
            </div>
            <div class="ctx-card" :class="{ none: !nextChunk }">
              <span class="ctx-title">
                后一段{{ nextChunk ? `（${nextChunk.chunk_label || `#${nextChunk.chunk_index + 1}`}）` : "" }}
              </span>
              <p v-if="nextChunk" class="ctx-text" role="button" @click="openDetail(nextChunk)">{{ neighborText(nextChunk) }}</p>
              <p v-else class="ctx-text muted">无（已是最后一条切片）</p>
            </div>
          </div>
        </section>

        <section class="detail-sec detail-md">
          <h4>在 MD 原文中的位置</h4>
          <p v-if="mdLoading" class="hint">加载原文…</p>
          <p v-else-if="mdError" class="hint err">{{ mdError }}</p>
          <div v-else class="detail-md-body">
            <template v-for="(seg, i) in mdSegments" :key="i">
              <mark v-if="seg.hit" class="md-hit">{{ seg.text }}</mark>
              <span v-else>{{ seg.text }}</span>
            </template>
          </div>
        </section>
      </div>
    </div>

    <div v-if="mdModal && locateChunk" class="detail-mask" @click.self="mdModal = false">
      <div class="locate-modal">
        <header class="detail-head">
          <h3>
            原文定位
            <span class="detail-label">{{ locateChunk.chunk_label || `#${locateChunk.chunk_index + 1}` }}</span>
          </h3>
          <button class="btn" type="button" @click="mdModal = false">关闭</button>
        </header>
        <p v-if="mdLoading" class="hint">加载原文…</p>
        <p v-else-if="mdError" class="hint err">{{ mdError }}</p>
        <div v-else class="locate-body">
          <template v-for="(seg, i) in locateSegments" :key="i">
            <mark v-if="seg.hit" class="md-hit">{{ seg.text }}</mark>
            <span v-else>{{ seg.text }}</span>
          </template>
        </div>
      </div>
    </div>
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
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 0.72rem;
}
.list-card th:nth-child(1) { width: 3%; }
.list-card th:nth-child(2) { width: 6%; }
.list-card th:nth-child(3) { width: 40%; }
.list-card th:nth-child(4) { width: 5%; }
.list-card th:nth-child(5) { width: 11%; }
.list-card th:nth-child(6) { width: 7%; }
.list-card th:nth-child(7) { width: 6%; }
.list-card th:nth-child(8) { width: 5%; }
.list-card th:nth-child(9) { width: 9%; }
.list-card th:nth-child(10) { width: 8%; }
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
  font-weight: 400;
  color: var(--text);
}
.chunk-cell {
  width: 20%;
  max-width: 20%;
  min-width: 8rem;
  white-space: nowrap;
}
.chunk-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chunk-text.clickable {
  cursor: pointer;
  color: var(--text);
  border-bottom: 1px dashed #cbd5e1;
}
.chunk-text.clickable:hover {
  color: var(--teal);
  border-bottom-color: var(--teal);
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
.meta-cell {
  max-width: 12rem;
  white-space: normal;
}
.meta-heading {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.lv-tag {
  font-style: normal;
  background: #eff6ff;
  color: #2563eb;
  border-radius: 4px;
  padding: 0.02rem 0.25rem;
  font-size: 0.6rem;
  font-weight: 700;
  flex-shrink: 0;
}
.meta-heading-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}
.meta-none {
  color: var(--muted);
}
.meta-sub {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--muted);
  font-size: 0.66rem;
  margin-top: 0.1rem;
}
.meta-flag {
  font-style: normal;
  background: #f5f3ff;
  color: #7c3aed;
  border-radius: 4px;
  padding: 0.02rem 0.25rem;
  font-size: 0.6rem;
  flex-shrink: 0;
}
.quality-cell {
  white-space: normal;
  max-width: 7rem;
}
.q-pill {
  display: inline-flex;
  margin: 0.05rem 0.2rem 0.05rem 0;
  padding: 0.05rem 0.4rem;
  font-size: 0.62rem;
  border-radius: 999px;
  cursor: default;
}
.q-ok {
  background: #ecfdf5;
  color: #059669;
}
.q-warn {
  background: #fff7ed;
  color: #ea580c;
}
.q-bad {
  background: #fff1f2;
  color: #e11d48;
}
.md-cell {
  white-space: nowrap;
}
.md-btn {
  font-size: 0.7rem;
}
.detail-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.detail-modal {
  width: min(58rem, 94vw);
  height: min(42rem, 90vh);
  background: #fff;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  padding: 1rem 1.2rem;
  overflow: hidden;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
  flex-shrink: 0;
}
.detail-head h3 {
  margin: 0;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.detail-label {
  color: var(--teal);
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
}
.detail-meta {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.3rem 1rem;
  padding: 0.55rem 0.75rem;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 10px;
  font-size: 0.74rem;
  color: var(--text);
  flex-shrink: 0;
}
.detail-meta > span {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  min-width: 0;
  flex-wrap: wrap;
}
.meta-k {
  font-style: normal;
  color: var(--muted);
  flex-shrink: 0;
}
.detail-sec {
  margin-top: 0.7rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.detail-sec h4 {
  margin: 0 0 0.35rem;
  font-size: 0.8rem;
  color: var(--text);
  flex-shrink: 0;
}
.detail-content {
  flex: 1;
  min-height: 4rem;
  max-height: 11rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.6rem 0.8rem;
  font-size: 0.76rem;
  line-height: 1.7;
  color: var(--text);
  background: #fff;
}
.detail-ctx {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
}
.ctx-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.5rem 0.7rem;
  min-width: 0;
}
.ctx-card.none {
  background: #fafafa;
}
.ctx-title {
  display: block;
  color: var(--muted);
  font-size: 0.66rem;
  margin-bottom: 0.25rem;
}
.ctx-text {
  margin: 0;
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--text);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.ctx-text:not(.muted) {
  cursor: pointer;
}
.ctx-text:not(.muted):hover {
  color: var(--teal);
}
.ctx-text.muted {
  color: var(--muted);
}
.detail-md {
  flex: 1;
  min-height: 5rem;
}
.detail-md-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.72rem;
  line-height: 1.7;
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.8rem 1rem;
}
.detail-md-body mark.md-hit {
  background: #fef08a;
  border-radius: 3px;
  padding: 0.05rem 0;
}
.locate-modal {
  width: min(52rem, 92vw);
  height: min(36rem, 86vh);
  background: #fff;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  padding: 1rem 1.2rem;
  overflow: hidden;
}
.locate-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.72rem;
  line-height: 1.7;
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.8rem 1rem;
}
.locate-body mark.md-hit {
  background: #fef08a;
  border-radius: 3px;
  padding: 0.05rem 0;
}
</style>
