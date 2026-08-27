<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  compareDocuments,
  createNote,
  deleteDocument,
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
    error.value = String(e);
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
    error.value = String(e);
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
    error.value = String(e);
  } finally {
    importing.value = false;
  }
}

onMounted(() => {
  refresh().catch((e) => (error.value = String(e)));
  timer = window.setInterval(() => {
    if (docs.value.some((d) => busy(d.status))) {
      refresh().catch(() => undefined);
    }
  }, 2000);
});
onUnmounted(() => {
  if (timer) window.clearInterval(timer);
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
    error.value = String(e);
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
  <main v-if="screen === 'import'" class="page docs-page">
    <div class="page-head">
      <div>
        <h1>导入</h1>
        <p class="sub">写入所选知识库。完成后返回文档列表。</p>
      </div>
      <div class="head-actions">
        <button class="btn" type="button" @click="backToList">返回文档列表</button>
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
        <textarea id="import-note" v-model="note" rows="8" placeholder="笔记" :disabled="importing"></textarea>
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
              <th>创建时间</th>
              <th>创建人</th>
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
              <td>{{ formatTime(doc.created_at) }}</td>
              <td>{{ doc.created_by || "—" }}</td>
              <td class="ops">
                <button class="btn-link" type="button" @click="reindexDocument(doc.id).then(refresh)">重新处理</button>
                <button class="btn-danger" type="button" @click="deleteDocument(doc.id).then(refresh)">删除</button>
              </td>
            </tr>
            <tr v-if="!filteredDocs.length">
              <td :colspan="pickMode ? 12 : 11" class="empty">没有符合条件的文档。可调整筛选，或点「导入」。</td>
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
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 1rem;
  font-size: 12.5px;
  background: transparent;
  height: 100%;
  min-height: 0;
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
.import-panel {
  max-width: 36rem;
  margin-bottom: 1rem;
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
  overflow: auto;
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
th,
td {
  text-align: left;
  padding: 0.4rem 0.45rem;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  vertical-align: middle;
}
.list-card tbody td {
  min-height: 36px;
  padding-top: 0.55rem;
  padding-bottom: 0.55rem;
  line-height: 1.45;
  box-sizing: border-box;
}
.file-cell {
  white-space: nowrap;
}
.tags-cell .pill {
  margin-right: 0.2rem;
  padding: 0.08rem 0.45rem;
  font-size: 0.62rem;
  cursor: default;
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
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--card);
  color: var(--muted);
  font-weight: 500;
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
  gap: 0.7rem;
  white-space: nowrap;
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
