<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  compareDocuments,
  createNote,
  deleteDocument,
  favoriteDocument,
  importUrl,
  listDocuments,
  listTags,
  reindexDocument,
  statusLabel,
  unfavoriteDocument,
  uploadFile,
  type DocumentItem,
  type TagItem,
} from "../api";
import { selectedKbId } from "../kb";

const md = new MarkdownIt();
const docs = ref<DocumentItem[]>([]);
const tags = ref<TagItem[]>([]);
const error = ref("");
const note = ref("");
const url = ref("");
const onlyFav = ref(false);
const filterTag = ref("");
const tagMenuOpen = ref(false);
const TAG_VISIBLE = 3;
const visibleTags = computed(() => tags.value.slice(0, TAG_VISIBLE));
const overflowTags = computed(() => tags.value.slice(TAG_VISIBLE));
const overflowSelected = computed(() => overflowTags.value.some((t) => t.id === filterTag.value));
const panel = ref<"" | "file" | "url" | "note">("");
const picked = ref<string[]>([]);
const pickMode = ref(false);
const comparing = ref(false);
const comparisonHtml = ref("");
const canCompare = computed(() => docs.value.length >= 2);
let timer: number | undefined;

async function refresh() {
  if (!selectedKbId.value) return;
  docs.value = await listDocuments(selectedKbId.value, {
    favorite: onlyFav.value || undefined,
    tagId: filterTag.value || undefined,
  });
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

function statusClass(status: string) {
  if (status === "ready") return "ok";
  if (status === "parse_failed" || status === "index_failed") return "bad";
  return "busy";
}

async function onUpload(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  error.value = "";
  try {
    await uploadFile(selectedKbId.value, file);
    await refresh();
    panel.value = "";
  } catch (e) {
    error.value = String(e);
  }
  input.value = "";
}

async function onNote() {
  error.value = "";
  try {
    await createNote(selectedKbId.value, note.value);
    note.value = "";
    await refresh();
    panel.value = "";
  } catch (e) {
    error.value = String(e);
  }
}

async function onUrl() {
  error.value = "";
  try {
    await importUrl(selectedKbId.value, url.value);
    url.value = "";
    await refresh();
    panel.value = "";
  } catch (e) {
    error.value = String(e);
  }
}

function closeTagMenu() {
  tagMenuOpen.value = false;
}

function pickOverflowTag(id: string) {
  filterTag.value = id;
  tagMenuOpen.value = false;
}

onMounted(() => {
  refresh().catch((e) => (error.value = String(e)));
  document.addEventListener("click", closeTagMenu);
  timer = window.setInterval(() => {
    if (docs.value.some((d) => busy(d.status))) {
      refresh().catch(() => undefined);
    }
  }, 2000);
});
onUnmounted(() => {
  document.removeEventListener("click", closeTagMenu);
  if (timer) window.clearInterval(timer);
});

function docTagNames(doc: DocumentItem) {
  return doc.tag_ids
    .map((id) => tags.value.find((t) => t.id === id)?.name)
    .filter((name): name is string => Boolean(name));
}

async function toggleFav(doc: DocumentItem) {
  if (doc.is_favorite) await unfavoriteDocument(doc.id);
  else await favoriteDocument(doc.id);
  await refresh();
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
  return docs.value.find((d) => d.id === id)?.filename || id;
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

watch([selectedKbId, onlyFav, filterTag], () => {
  picked.value = [];
  pickMode.value = false;
  comparisonHtml.value = "";
  refresh().catch((e) => (error.value = String(e)));
});
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1>文档</h1>
        <p class="sub">管理导入的 pdf、docx、md、txt、网页与笔记</p>
      </div>
      <div class="actions">
        <button class="btn btn-primary" type="button" @click="panel = panel === 'note' ? '' : 'note'">Markdown 笔记</button>
        <button class="btn" type="button" @click="panel = panel === 'file' ? '' : 'file'">上传文件</button>
        <button class="btn" type="button" @click="panel = panel === 'url' ? '' : 'url'">公开页 URL</button>
      </div>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <section v-if="panel === 'note'" class="card form">
      <textarea v-model="note" rows="5" placeholder="Markdown 笔记"></textarea>
      <button class="btn btn-primary" type="button" @click="onNote">创建笔记</button>
    </section>
    <section v-if="panel === 'file'" class="card form">
      <p class="sub">支持 pdf、docx、md、txt，单文件不超过 100MB</p>
      <label class="file-pick">
        <input
          class="sr-only"
          type="file"
          accept=".pdf,.docx,.md,.markdown,.txt"
          @change="onUpload"
        />
        <span class="btn btn-primary">选择文件</span>
      </label>
    </section>
    <section v-if="panel === 'url'" class="card form">
      <input v-model="url" placeholder="https://…" />
      <button class="btn btn-primary" type="button" @click="onUrl">导入网址</button>
    </section>

    <div class="filters">
      <div class="tag-row">
        <button class="pill" :class="{ on: !filterTag }" type="button" @click="filterTag = ''">全部</button>
        <button
          v-for="t in visibleTags"
          :key="t.id"
          class="pill"
          :class="{ on: filterTag === t.id }"
          type="button"
          @click="filterTag = t.id"
        >
          {{ t.name }}
        </button>
        <div v-if="overflowTags.length" class="tag-more">
          <button
            class="pill"
            :class="{ on: overflowSelected }"
            type="button"
            aria-label="更多标签"
            :aria-expanded="tagMenuOpen"
            @click.stop="tagMenuOpen = !tagMenuOpen"
          >
            …
          </button>
          <div v-if="tagMenuOpen" class="tag-pop" @click.stop>
            <button
              v-for="t in overflowTags"
              :key="t.id"
              class="tag-pop-item"
              :class="{ on: filterTag === t.id }"
              type="button"
              @click="pickOverflowTag(t.id)"
            >
              {{ t.name }}
            </button>
          </div>
        </div>
      </div>
      <div class="filter-right">
        <label class="fav"><input v-model="onlyFav" type="checkbox" /> 只看收藏</label>
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
    </div>

    <section v-if="comparisonHtml" class="card compare">
      <h2>对比结果</h2>
      <p class="sub">{{ pickName(picked[0]) }} 与 {{ pickName(picked[1]) }}</p>
      <article class="compare-body" v-html="comparisonHtml"></article>
    </section>

    <div class="table-wrap card">
      <table>
        <thead>
          <tr>
            <th v-if="pickMode" class="pick-h">
              对比
              <span class="pick-count">已选 {{ picked.length }}/2</span>
            </th>
            <th>文件名</th>
            <th>类型</th>
            <th>状态</th>
            <th>失败原因</th>
            <th>标签</th>
            <th>收藏</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in docs" :key="doc.id">
            <td v-if="pickMode">
              <input
                type="checkbox"
                :disabled="doc.status !== 'ready'"
                :checked="picked.includes(doc.id)"
                @change="togglePick(doc)"
              />
            </td>
            <td>
              <RouterLink :to="`/documents/${doc.id}`">{{ doc.filename }}</RouterLink>
            </td>
            <td><span class="kind">{{ doc.kind }}</span></td>
            <td>
              <span class="st" :class="statusClass(doc.status)">{{ statusLabel(doc.status) }}</span>
            </td>
            <td class="err">{{ doc.error_message || "" }}</td>
            <td class="tags-cell">
              <span v-for="name in docTagNames(doc)" :key="name" class="tag-chip">{{ name }}</span>
              <span v-if="!doc.tag_ids.length" class="muted">—</span>
            </td>
            <td>
              <button class="btn-link" type="button" @click="toggleFav(doc)">
                {{ doc.is_favorite ? "★" : "☆" }}
              </button>
            </td>
            <td class="ops">
              <button class="btn-link" type="button" @click="reindexDocument(doc.id).then(refresh)">重新处理</button>
              <button class="btn-danger" type="button" @click="deleteDocument(doc.id).then(refresh)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="count">共 {{ docs.length }} 篇</p>
    </div>
  </main>
</template>

<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.form {
  padding: 1rem;
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.form input:not([type="file"]),
.form textarea {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.65rem 0.8rem;
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
.file-pick {
  display: inline-flex;
  width: fit-content;
  cursor: pointer;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.8rem;
  align-items: center;
  margin-bottom: 1rem;
}
.tag-row,
.filter-right {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
}
.filter-right {
  margin-left: auto;
}
.tag-more {
  position: relative;
}
.tag-pop {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 20;
  min-width: 9rem;
  max-height: 16rem;
  overflow: auto;
  padding: 0.35rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.tag-pop-item {
  border: none;
  background: transparent;
  text-align: left;
  border-radius: 8px;
  padding: 0.35rem 0.55rem;
  cursor: pointer;
  color: var(--text);
}
.tag-pop-item:hover,
.tag-pop-item.on {
  background: var(--teal-soft);
  color: var(--teal);
}
.fav {
  color: var(--muted);
  font-size: 0.9rem;
}
.table-wrap {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
}
th,
td {
  padding: 0.75rem 0.8rem;
  text-align: left;
  border-bottom: 1px solid var(--line);
  font-size: 0.92rem;
  white-space: nowrap;
  word-break: keep-all;
  vertical-align: middle;
}
.pick-h {
  text-align: center;
  white-space: nowrap;
}
.pick-count {
  display: block;
  margin-top: 0.15rem;
  font-size: 0.72rem;
  font-weight: 400;
  color: var(--muted);
}
.tags-cell {
  white-space: nowrap;
}
.tag-chip {
  display: inline-flex;
  margin-right: 0.35rem;
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.45rem;
  font-size: 0.78rem;
  color: #556;
}
.muted {
  color: var(--muted);
}
.kind {
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.4rem;
  font-size: 0.78rem;
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
.count {
  padding: 0.6rem 0.8rem;
  color: var(--muted);
  font-size: 0.85rem;
}
.compare {
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
}
.compare h2 {
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
}
.compare-body {
  margin-top: 0.6rem;
  line-height: 1.65;
}
.compare-body :deep(p) {
  margin: 0.4rem 0;
}
</style>
