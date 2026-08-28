<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  compareDocuments,
  createNote,
  deleteDocument,
  documentFailureReason,
  documentStatusClass,
  documentStatusLabel,
  importUrl,
  listDocuments,
  listTags,
  reindexDocument,
  uploadFile,
  type DocumentItem,
  type TagItem,
} from "../api";
import { knowledgeBases, loadKnowledgeBases } from "../kb";

const md = new MarkdownIt();
const docs = ref<DocumentItem[]>([]);
const tags = ref<TagItem[]>([]);
const error = ref("");
const note = ref("");
const url = ref("");
const filterKb = ref("");
const filterName = ref("");
const filterStatus = ref("");
const filterTag = ref("");
const appliedKb = ref("");
const appliedName = ref("");
const appliedStatus = ref("");
const appliedTag = ref("");
const screen = ref<"list" | "import">("list");
const ingest = ref<"file" | "url" | "note">("file");
const uploadKbId = ref("");
const uploading = ref(false);
const importing = ref(false);
const dragOver = ref(false);
const picked = ref<string[]>([]);
const pickMode = ref(false);
const comparing = ref(false);
const comparisonHtml = ref("");
const reindexingIds = ref<Set<string>>(new Set());
const filteredDocs = computed(() => {
  const name = appliedName.value.trim().toLowerCase();
  return docs.value.filter((doc) => {
    if (appliedKb.value && doc.knowledge_base_id !== appliedKb.value) return false;
    if (name && !doc.filename.toLowerCase().includes(name)) return false;
    if (appliedStatus.value === "ready" && doc.status !== "ready") return false;
    if (appliedStatus.value === "failed" && doc.status !== "parse_failed" && doc.status !== "index_failed") return false;
    if (appliedStatus.value === "busy" && !busy(doc.status)) return false;
    if (appliedTag.value && !doc.tag_ids.includes(appliedTag.value)) return false;
    return true;
  });
});
const canCompare = computed(() => filteredDocs.value.filter((d) => d.status === "ready").length >= 2);
const notePreviewHtml = computed(() => {
  const raw = note.value.trim();
  if (!raw) return "<p class=\"empty\">预览将显示在这里</p>";
  return md.render(raw);
});
const pageSize = 20;
const page = ref(1);
const pageCount = computed(() => Math.max(1, Math.ceil(filteredDocs.value.length / pageSize)));
const pagedDocs = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filteredDocs.value.slice(start, start + pageSize);
});
let timer: number | undefined;

async function refresh() {
  await loadKnowledgeBases();
  if (!uploadKbId.value) {
    uploadKbId.value = knowledgeBases.value.find((k) => k.is_default)?.id || knowledgeBases.value[0]?.id || "";
  }
  docs.value = await listDocuments();
  tags.value = await listTags();
  const ids = new Set(docs.value.map((d) => d.id));
  picked.value = picked.value.filter((id) => ids.has(id));
  if (docs.value.length < 2) {
    pickMode.value = false;
    picked.value = [];
    comparisonHtml.value = "";
  }
}

function busy(status: string) {
  return status !== "ready" && status !== "parse_failed" && status !== "index_failed";
}

function reindexBusy(doc: DocumentItem) {
  return reindexingIds.value.has(doc.id);
}

function reindexLabel(doc: DocumentItem) {
  if (reindexingIds.value.has(doc.id)) return "处理中";
  if (doc.status === "indexing" || doc.status === "parsing") return "重试向量化";
  return "向量化";
}

async function onReindex(doc: DocumentItem) {
  if (reindexBusy(doc)) return;
  reindexingIds.value = new Set([...reindexingIds.value, doc.id]);
  try {
    await reindexDocument(doc.id);
    await refresh();
  } catch {
    await refresh();
  }
}

function failureReasonTitle(doc: DocumentItem) {
  const text = documentFailureReason(doc);
  return text === "—" ? undefined : text;
}

function formatApiError(e: unknown) {
  const msg = e instanceof Error ? e.message : String(e);
  return msg.replace(/^Error:\s*/, "");
}

function openImport() {
  error.value = "";
  ingest.value = "file";
  screen.value = "import";
}

function backToList() {
  screen.value = "list";
}

async function afterImport() {
  await refresh();
  screen.value = "list";
}

async function sendFile(file: File) {
  if (uploading.value) return;
  error.value = "";
  uploading.value = true;
  try {
    await uploadFile(uploadKbId.value, file);
    await afterImport();
  } catch (e) {
    error.value = formatApiError(e);
  } finally {
    uploading.value = false;
  }
}

async function onUpload(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) await sendFile(file);
  input.value = "";
}

function onDrop(ev: DragEvent) {
  ev.preventDefault();
  dragOver.value = false;
  const file = ev.dataTransfer?.files?.[0];
  if (file) void sendFile(file);
}

async function onNote() {
  if (importing.value) return;
  error.value = "";
  importing.value = true;
  try {
    await createNote(uploadKbId.value, note.value);
    note.value = "";
    await afterImport();
  } catch (e) {
    error.value = formatApiError(e);
  } finally {
    importing.value = false;
  }
}

async function onUrl() {
  if (importing.value) return;
  error.value = "";
  importing.value = true;
  try {
    await importUrl(uploadKbId.value, url.value);
    url.value = "";
    await afterImport();
  } catch (e) {
    error.value = formatApiError(e);
  } finally {
    importing.value = false;
  }
}

onMounted(() => {
  refresh().catch((e) => (error.value = formatApiError(e)));
  timer = window.setInterval(() => {
    if (docs.value.some((d) => busy(d.status)) || reindexingIds.value.size) {
      refresh().catch(() => undefined);
    }
  }, 2000);
});
onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});

watch(docs, (rows) => {
  if (!reindexingIds.value.size) return;
  const next = new Set(reindexingIds.value);
  let changed = false;
  for (const id of reindexingIds.value) {
    const doc = rows.find((d) => d.id === id);
    if (!doc || !busy(doc.status)) {
      next.delete(id);
      changed = true;
    }
  }
  if (changed) reindexingIds.value = next;
});

function formatSize(n: number) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(raw?: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.replace("T", " ").slice(0, 19);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fileType(doc: DocumentItem) {
  const ext = (doc.ext || "").replace(/^\./, "");
  return ext || doc.kind || "—";
}

function togglePick(doc: DocumentItem) {
  if (doc.status !== "ready") return;
  const i = picked.value.indexOf(doc.id);
  if (i >= 0) {
    picked.value = picked.value.filter((id) => id !== doc.id);
    return;
  }
  if (picked.value.length >= 2) {
    picked.value = [picked.value[1], doc.id];
    return;
  }
  picked.value = [...picked.value, doc.id];
}

function pickName(id: string) {
  const doc = docs.value.find((d) => d.id === id);
  return doc ? displayTitle(doc.filename) : id;
}

function displayTitle(filename: string) {
  const name = filename.trim();
  if (/^https?:\/\//i.test(name)) {
    try {
      return new URL(name).hostname || name;
    } catch {
      return name;
    }
  }
  const base = name.replace(/\\/g, "/").split("/").pop() || name;
  const i = base.lastIndexOf(".");
  return i > 0 ? base.slice(0, i) : base;
}

function tagNames(doc: DocumentItem) {
  return doc.tag_ids
    .map((id) => tags.value.find((t) => t.id === id)?.name)
    .filter((name): name is string => Boolean(name));
}

function visibleTags(doc: DocumentItem) {
  return tagNames(doc).slice(0, 3);
}

function overviewText(doc: DocumentItem) {
  return (doc.summary || "").trim();
}

function overviewShort(doc: DocumentItem) {
  const text = overviewText(doc);
  if (!text) return "—";
  return text.length > 15 ? `${text.slice(0, 15)}…` : text;
}

function clickCompare() {
  if (!pickMode.value) {
    pickMode.value = true;
    return;
  }
  if (picked.value.length === 0) {
    pickMode.value = false;
    comparisonHtml.value = "";
    return;
  }
  onCompare();
}

async function onCompare() {
  if (picked.value.length !== 2 || comparing.value) return;
  error.value = "";
  comparisonHtml.value = "";
  comparing.value = true;
  try {
    const result = await compareDocuments(picked.value[0], picked.value[1]);
    comparisonHtml.value = md.render(result.comparison);
  } catch (e) {
    error.value = formatApiError(e);
  } finally {
    comparing.value = false;
  }
}

function applyFilters() {
  appliedKb.value = filterKb.value;
  appliedName.value = filterName.value;
  appliedStatus.value = filterStatus.value;
  appliedTag.value = filterTag.value;
  picked.value = [];
  pickMode.value = false;
  comparisonHtml.value = "";
  page.value = 1;
}

watch(pageCount, (n) => {
  if (page.value > n) page.value = n;
});

</script>

<template>
  <main v-if="screen === 'import'" class="page docs-page import-screen">
    <div class="page-head">
      <div>
        <h1 class="crumb-title">
          <button type="button" class="crumb-link" @click="backToList">文档</button>
          <span class="crumb-sep" aria-hidden="true">›</span>
          <span>导入</span>
        </h1>
        <p class="sub">写入所选知识库。完成后返回文档列表。</p>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>
    <section class="card pad import-panel">
      <label for="upload-kb">目标知识库</label>
      <select id="upload-kb" v-model="uploadKbId">
        <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
          {{ kb.is_default ? "默认" : kb.name }}
        </option>
      </select>
      <div class="tabs" role="tablist" aria-label="导入方式">
        <button type="button" role="tab" :class="{ on: ingest === 'file' }" :aria-selected="ingest === 'file'" @click="ingest = 'file'">
          文件
        </button>
        <button type="button" role="tab" :class="{ on: ingest === 'url' }" :aria-selected="ingest === 'url'" @click="ingest = 'url'">
          网址
        </button>
        <button type="button" role="tab" :class="{ on: ingest === 'note' }" :aria-selected="ingest === 'note'" @click="ingest = 'note'">
          笔记
        </button>
      </div>

      <div v-if="ingest === 'file'" class="ingest-body">
        <p class="tiny">pdf / docx / md / txt，不超过 100MB</p>
        <label
          class="drop"
          :class="{ over: dragOver, busy: uploading }"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop="onDrop"
        >
          <input
            class="sr-only"
            type="file"
            accept=".pdf,.docx,.md,.markdown,.txt"
            :disabled="uploading"
            @change="onUpload"
          />
          <span>{{ uploading ? "上传中…" : "选择文件或拖到此处" }}</span>
        </label>
      </div>
      <div v-else-if="ingest === 'url'" class="ingest-body">
        <label for="import-url">公开页 URL</label>
        <input id="import-url" v-model="url" placeholder="https://…" :disabled="importing" />
        <button class="btn btn-primary" type="button" :disabled="importing || !url.trim()" @click="onUrl">
          {{ importing ? "导入中…" : "导入网址" }}
        </button>
      </div>
      <div v-else class="ingest-body">
        <label for="import-note">Markdown 笔记</label>
        <p class="tiny">左侧写 Markdown 原文；右侧即时预览。首个标题会作为文件名。</p>
        <div class="note-compose">
          <div class="note-pane">
            <span class="pane-label">原文</span>
            <textarea
              id="import-note"
              v-model="note"
              rows="10"
              placeholder="# 标题&#10;&#10;正文…"
              :disabled="importing"
            ></textarea>
          </div>
          <div class="note-pane">
            <span class="pane-label">预览</span>
            <div class="note-preview" v-html="notePreviewHtml"></div>
          </div>
        </div>
        <button class="btn btn-primary" type="button" :disabled="importing || !note.trim()" @click="onNote">
          {{ importing ? "创建中…" : "创建笔记" }}
        </button>
      </div>
    </section>
  </main>

  <main v-else class="page docs-page">
    <div class="page-head">
      <div>
        <h1>文档</h1>
        <p class="sub">列表展示全部知识库。导入会写入导入页所选的库。</p>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <section class="card pad toolbar">
      <div class="filters">
        <select v-model="filterKb" class="filter" :class="{ hinting: !filterKb }" aria-label="知识库">
          <option value="" disabled hidden>知识库</option>
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
            {{ kb.is_default ? "默认" : kb.name }}
          </option>
        </select>
        <input
          v-model="filterName"
          type="search"
          placeholder="文件名"
          aria-label="文件名"
          @keydown.enter.prevent="applyFilters"
        />
        <select v-model="filterStatus" class="filter" :class="{ hinting: !filterStatus }" aria-label="状态">
          <option value="" disabled hidden>状态</option>
          <option value="ready">已完成</option>
          <option value="busy">处理中</option>
          <option value="failed">处理失败</option>
        </select>
        <select v-model="filterTag" class="filter" :class="{ hinting: !filterTag }" aria-label="标签">
          <option value="" disabled hidden>标签</option>
          <option v-for="t in tags" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>
      <div class="toolbar-actions">
        <button class="btn btn-primary" type="button" @click="applyFilters">查询</button>
        <button class="btn btn-primary" type="button" @click="openImport">导入</button>
        <button
          v-if="canCompare"
          class="btn btn-primary"
          type="button"
          :disabled="comparing || (pickMode && picked.length === 1)"
          @click="clickCompare"
        >
          {{ comparing ? "对比中…" : pickMode && picked.length === 2 ? "开始对比" : "对比" }}
        </button>
      </div>
    </section>

    <section v-if="comparisonHtml" class="card pad">
      <h2>对比结果</h2>
      <p class="tiny">{{ pickName(picked[0]) }} 与 {{ pickName(picked[1]) }}</p>
      <article class="compare-body" v-html="comparisonHtml"></article>
    </section>

    <section class="card pad list-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-if="pickMode">
                对比
                <span class="pick-count">{{ picked.length }}/2</span>
              </th>
              <th>序号</th>
              <th>文件名</th>
              <th>概述</th>
              <th>标签</th>
              <th>文件类型</th>
              <th>文件大小</th>
              <th>切片长度</th>
              <th>重叠长度</th>
              <th class="status-cell">状态</th>
              <th>失败原因</th>
              <th>创建人</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(doc, i) in pagedDocs" :key="doc.id" :class="{ on: pickMode && picked.includes(doc.id) }">
              <td v-if="pickMode">
                <input
                  type="checkbox"
                  :disabled="doc.status !== 'ready'"
                  :checked="picked.includes(doc.id)"
                  :aria-label="`对比 ${displayTitle(doc.filename)}`"
                  @change="togglePick(doc)"
                />
              </td>
              <td class="seq">{{ (page - 1) * pageSize + i + 1 }}</td>
              <td class="file-cell">
                <RouterLink :to="`/documents/${doc.id}`">{{ displayTitle(doc.filename) }}</RouterLink>
              </td>
              <td class="overview">
                <span>{{ overviewShort(doc) }}</span>
                <span v-if="overviewText(doc).length > 15" class="tip">{{ overviewText(doc) }}</span>
              </td>
              <td class="tags-cell">
                <template v-if="tagNames(doc).length">
                  <span
                    v-for="name in visibleTags(doc)"
                    :key="name"
                    class="pill"
                    :title="tagNames(doc).join(' · ')"
                  >{{ name }}</span>
                  <span v-if="tagNames(doc).length > 3" class="pill" :title="tagNames(doc).join(' · ')">…</span>
                </template>
                <span v-else>—</span>
              </td>
              <td>{{ fileType(doc) }}</td>
              <td>{{ formatSize(doc.byte_size || 0) }}</td>
              <td>{{ doc.chunk_size ?? "—" }}</td>
              <td>{{ doc.chunk_overlap ?? "—" }}</td>
              <td class="status-cell">
                <span class="pill status-pill" :class="documentStatusClass(doc.status)">
                  {{ documentStatusLabel(doc.status) }}
                </span>
              </td>
              <td class="fail-reason">
                <span class="fail-text" :title="failureReasonTitle(doc)">{{ documentFailureReason(doc) }}</span>
              </td>
              <td>{{ doc.created_by || "—" }}</td>
              <td>{{ formatTime(doc.created_at) }}</td>
              <td class="ops">
                <RouterLink class="btn-link" :to="`/documents/${doc.id}/chunks`">切片</RouterLink>
                <button
                  class="btn-link reindex-btn"
                  type="button"
                  :disabled="reindexBusy(doc)"
                  @click="onReindex(doc)"
                >
                  {{ reindexLabel(doc) }}
                </button>
                <button class="btn-danger" type="button" @click="deleteDocument(doc.id).then(refresh)">删除</button>
              </td>
            </tr>
            <tr v-if="!filteredDocs.length">
              <td :colspan="pickMode ? 14 : 13" class="empty">没有符合条件的文档。可调整筛选，或点「导入」。</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
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
.docs-page .page-head h1 {
  font-size: 1.05rem;
}
.docs-page .page-head {
  margin-bottom: 0.45rem;
}
.docs-page .page-head,
.docs-page .toolbar,
.docs-page .hint {
  flex-shrink: 0;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}
.toolbar {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 0.35rem;
  margin-bottom: 0.4rem;
  padding: 0.45rem 0.55rem;
  align-items: center;
}
.filters {
  width: 80%;
  display: flex;
  gap: 0.35rem;
  min-width: 0;
}
.filters select,
.filters input {
  flex: 1 1 0;
  min-width: 0;
  padding: 0.28rem 0.4rem;
  margin: 0;
}
.filters select.hinting {
  color: var(--muted);
}
.filters input::placeholder {
  color: var(--muted);
}
.toolbar-actions {
  display: flex;
  gap: 0.35rem;
  margin-left: auto;
  flex-shrink: 0;
}
.hint,
.tiny {
  color: var(--muted);
  font-size: 0.75rem;
}
.tiny {
  margin: 0.2rem 0 0.5rem;
}
.hint.err {
  color: var(--danger);
}
.pad {
  padding: 1rem 1.1rem;
}
.toolbar.pad {
  padding: 0.45rem 0.55rem;
}
.pad h2 {
  margin: 0 0 0.4rem;
  font-size: 0.78rem;
}
.docs-page.pad label:not(.drop) {
  display: block;
  font-size: 0.68rem;
  color: var(--muted);
  margin: 0.3rem 0 0.15rem;
}
.pad textarea,
.pad input:not([type="file"]):not([type="checkbox"]),
.pad select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
  background: #fff;
}
.toolbar select,
.toolbar input {
  padding: 0.28rem 0.4rem;
}
.import-screen {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}
.import-screen .import-panel {
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  max-width: none;
  margin-bottom: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
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
  border: none;
  background: none;
  padding: 0;
  margin: 0;
  font: inherit;
  font-weight: 700;
  color: var(--teal);
  cursor: pointer;
}
.crumb-link:hover {
  text-decoration: underline;
}
.crumb-sep {
  color: var(--muted);
  font-weight: 500;
}
.import-panel {
  max-width: none;
  width: 100%;
  margin-bottom: 0;
}
.note-compose {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
  margin: 0.35rem 0 0;
  min-width: 0;
}
.note-pane {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.pane-label {
  font-size: 0.68rem;
  color: var(--muted);
}
.note-pane textarea {
  flex: 1;
  min-height: 12rem;
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.72rem;
  line-height: 1.5;
}
.note-preview {
  flex: 1;
  min-height: 12rem;
  max-height: 22rem;
  overflow: auto;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--text);
}
.note-preview :deep(h1),
.note-preview :deep(h2),
.note-preview :deep(h3) {
  margin: 0.35rem 0 0.45rem;
  line-height: 1.3;
}
.note-preview :deep(h1) { font-size: 1.15rem; }
.note-preview :deep(h2) { font-size: 1.02rem; }
.note-preview :deep(h3) { font-size: 0.9rem; }
.note-preview :deep(p) {
  margin: 0.35rem 0;
}
.note-preview :deep(ul),
.note-preview :deep(ol) {
  margin: 0.35rem 0;
  padding-left: 1.2rem;
}
.note-preview :deep(.empty) {
  margin: 0;
  color: var(--muted);
}
@media (max-width: 640px) {
  .note-compose {
    grid-template-columns: 1fr;
  }
}
.tabs {
  display: flex;
  flex-wrap: nowrap;
  gap: 0;
  margin: 0.55rem 0;
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
}
.tabs button {
  border: none;
  background: none;
  border-radius: 0;
  padding: 0.35rem 0.7rem 0.45rem;
  cursor: pointer;
  color: var(--muted);
  font-size: 0.72rem;
  white-space: nowrap;
  box-shadow: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tabs button.on {
  background: none;
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.tabs button:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
}
.ingest-body {
  margin-top: 0.35rem;
}
.ingest-body .btn {
  width: 100%;
  margin-top: 0.35rem;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
.drop {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 10.5rem;
  padding: 1.2rem;
  text-align: center;
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: var(--bg);
  cursor: pointer;
  color: var(--muted);
  margin: 0.3rem 0 0;
}
.import-screen .drop {
  flex: 1;
  min-height: 14rem;
}
.import-screen .ingest-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.import-screen .note-compose {
  flex: 1;
  min-height: 0;
}
.import-screen .note-pane textarea,
.import-screen .note-preview {
  min-height: 0;
  flex: 1;
  max-height: none;
}
.drop:hover,
.drop.over {
  border-color: var(--teal);
  background: var(--teal-soft);
  color: var(--teal);
}
.drop.busy {
  pointer-events: none;
  opacity: 0.7;
}
.drop:focus-within {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
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
}
.list-card th {
  text-align: left;
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--card);
  color: var(--muted);
  font-weight: 500;
}
.list-card td {
  text-align: left;
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
tbody tr.on {
  background: var(--teal-soft);
}
.file-cell {
  white-space: nowrap;
}
.tags-cell .pill {
  margin: 0 0.1rem;
  padding: 0.08rem 0.45rem;
  font-size: 0.62rem;
  cursor: default;
}
.status-cell .status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
.pill.bad {
  background: #fef2f2;
  color: #dc2626;
}
.fail-reason {
  max-width: 10rem;
  color: var(--text);
}
.fail-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}
.ops .btn-link:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  text-decoration: none;
}
.seq {
  color: var(--muted);
  width: 2.2rem;
}
.overview {
  position: relative;
  max-width: 12rem;
  color: var(--text);
}
.overview .tip {
  display: none;
  position: absolute;
  left: 0;
  top: calc(100% - 0.15rem);
  z-index: 6;
  min-width: 12rem;
  max-width: 22rem;
  padding: 0.4rem 0.55rem;
  background: #fff;
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  border-radius: 8px;
  white-space: normal;
  color: var(--text);
  font-size: 0.68rem;
  line-height: 1.45;
}
.overview:hover .tip {
  display: block;
}
.pick-count {
  display: block;
  font-size: 0.62rem;
  font-weight: 400;
  color: var(--muted);
}
.tag-chip {
  display: inline-flex;
  margin-right: 0.3rem;
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 6px;
  padding: 0.08rem 0.4rem;
  font-size: 0.68rem;
}
.empty {
  color: var(--muted);
}
.st.ok {
  color: var(--ok);
}
.st.bad {
  color: var(--danger);
}
.st.busy {
  color: var(--warn);
}
.ops {
  display: flex;
  gap: 0.35rem;
  white-space: nowrap;
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
.compare-body {
  margin-top: 0.4rem;
  line-height: 1.65;
  font-size: 0.78rem;
}
.compare-body :deep(p) {
  margin: 0.4rem 0;
}
</style>
