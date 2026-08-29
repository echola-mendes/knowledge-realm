<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  updateKnowledgeBase,
  type KnowledgeBase,
} from "../api";
import { knowledgeBases, loadKnowledgeBases } from "../kb";

const createName = ref("");
const filterQuery = ref("");
const filterStatus = ref("");
const appliedQuery = ref("");
const appliedStatus = ref("");
const renaming = ref("");
const renameValue = ref("");
const error = ref("");
const busy = ref(false);
const pageSize = 20;
const page = ref(1);

const filteredRows = computed(() => {
  const q = appliedQuery.value.trim();
  return knowledgeBases.value.filter((kb) => {
    if (appliedStatus.value === "on" && !kb.is_enabled) return false;
    if (appliedStatus.value === "off" && kb.is_enabled) return false;
    if (!q) return true;
    const label = kb.is_default ? "默认" : kb.name;
    return label.includes(q) || kb.name.includes(q);
  });
});

const pageCount = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize)));
const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filteredRows.value.slice(start, start + pageSize);
});

onMounted(() => {
  loadKnowledgeBases().catch((e: Error) => {
    error.value = e.message;
  });
});

watch(pageCount, (n) => {
  if (page.value > n) page.value = n;
});

async function refresh() {
  await loadKnowledgeBases();
}

function applyFilters() {
  appliedQuery.value = filterQuery.value;
  appliedStatus.value = filterStatus.value;
  page.value = 1;
}

function displayName(kb: KnowledgeBase) {
  return kb.is_default ? "默认" : kb.name;
}

function kbKind(kb: KnowledgeBase) {
  if (kb.name.startsWith("测试库-")) return "测试库";
  if (kb.is_default) return "默认库";
  return "自定义";
}

function formatTime(raw?: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.replace("T", " ").slice(0, 19);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function formatSize(n: number) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function addKb() {
  const n = createName.value.trim();
  if (!n || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await createKnowledgeBase(n);
    createName.value = "";
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "创建失败";
  } finally {
    busy.value = false;
  }
}

function startRename(kb: KnowledgeBase) {
  renaming.value = kb.id;
  renameValue.value = displayName(kb);
}

async function saveRename(kb: KnowledgeBase) {
  const n = renameValue.value.trim();
  if (!n || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await updateKnowledgeBase(kb.id, { name: n });
    renaming.value = "";
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "改名失败";
  } finally {
    busy.value = false;
  }
}

async function toggleEnabled(kb: KnowledgeBase, on: boolean) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await updateKnowledgeBase(kb.id, { is_enabled: on });
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "更新失败";
  } finally {
    busy.value = false;
  }
}

async function removeKb(kb: KnowledgeBase) {
  if (kb.is_default || busy.value) return;
  if (!confirm(`删除知识库「${displayName(kb)}」？文档与切片会一并删除。`)) return;
  busy.value = true;
  error.value = "";
  try {
    await deleteKnowledgeBase(kb.id);
    await refresh();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "删除失败";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="page docs-page">
    <div class="page-head">
      <div>
        <h1>知识库管理</h1>
        <p class="sub">开关控制是否参与搜索与问答。检索默认使用全部已开启的库。</p>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <section class="card pad toolbar">
      <div class="filters">
        <input
          v-model="filterQuery"
          type="search"
          placeholder="知识库名称"
          aria-label="知识库名称"
          @keydown.enter.prevent="applyFilters"
        />
        <select v-model="filterStatus" class="filter" :class="{ hinting: !filterStatus }" aria-label="状态">
          <option value="" disabled hidden>状态</option>
          <option value="on">已开启</option>
          <option value="off">已关闭</option>
        </select>
        <input
          v-model="createName"
          maxlength="200"
          placeholder="新建知识库名称"
          aria-label="新建知识库名称"
          @keydown.enter.prevent="addKb"
        />
      </div>
      <div class="toolbar-actions">
        <button class="btn btn-primary" type="button" @click="applyFilters">查询</button>
        <button class="btn btn-primary" type="button" :disabled="busy || !createName.trim()" @click="addKb">创建</button>
      </div>
    </section>

    <section class="card pad list-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>序号</th>
              <th>知识库</th>
              <th>类型</th>
              <th>文档数</th>
              <th>大小</th>
              <th>创建时间</th>
              <th>开启</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(kb, i) in pagedRows" :key="kb.id">
              <td class="seq">{{ (page - 1) * pageSize + i + 1 }}</td>
              <td class="file-cell">
                <template v-if="renaming === kb.id">
                  <input v-model="renameValue" maxlength="200" @keydown.enter="saveRename(kb)" @keydown.esc="renaming = ''" />
                </template>
                <strong v-else>{{ displayName(kb) }}</strong>
              </td>
              <td>{{ kbKind(kb) }}</td>
              <td>{{ kb.document_count ?? 0 }}</td>
              <td class="muted">{{ formatSize(kb.byte_size || 0) }}</td>
              <td class="muted">{{ formatTime(kb.created_at) }}</td>
              <td>
                <label class="toggle">
                  <span class="sr">是否开启知识库</span>
                  <input
                    type="checkbox"
                    role="switch"
                    :checked="kb.is_enabled"
                    @change="toggleEnabled(kb, ($event.target as HTMLInputElement).checked)"
                  />
                </label>
              </td>
              <td class="ops">
                <template v-if="renaming === kb.id">
                  <button class="btn-link" type="button" :disabled="busy" @click="saveRename(kb)">保存</button>
                  <button class="btn-link" type="button" @click="renaming = ''">取消</button>
                </template>
                <template v-else>
                  <button class="btn-link" type="button" @click="startRename(kb)">改名</button>
                  <button class="btn-danger" type="button" :disabled="kb.is_default" @click="removeKb(kb)">删除</button>
                </template>
              </td>
            </tr>
            <tr v-if="!filteredRows.length">
              <td colspan="8" class="empty">没有匹配的知识库</td>
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
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
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
.hint.err {
  color: var(--danger);
}
.pad {
  padding: 1rem 1.1rem;
}
.toolbar.pad {
  padding: 0.45rem 0.55rem;
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
.file-cell {
  white-space: nowrap;
}
.file-cell input {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.28rem 0.4rem;
  font-size: inherit;
}
.seq {
  color: var(--muted);
  width: 2.2rem;
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
.muted {
  color: var(--muted);
  white-space: nowrap;
}
.ops {
  display: flex;
  gap: 0.7rem;
  white-space: nowrap;
}
.empty {
  color: var(--muted);
}
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.toggle {
  display: inline-flex;
  cursor: pointer;
  margin: 0;
}
.toggle input {
  appearance: none;
  -webkit-appearance: none;
  width: 2.1rem;
  height: 1.15rem;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 999px;
  background: #cbd5e1;
  position: relative;
  cursor: pointer;
}
.toggle input::after {
  content: "";
  position: absolute;
  top: 0.12rem;
  left: 0.12rem;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 50%;
  background: #fff;
}
.toggle input:checked {
  background: #2563eb;
}
.toggle input:checked::after {
  left: 1.05rem;
}
</style>
