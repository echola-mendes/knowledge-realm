<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  createNote,
  createTag,
  deleteDocument,
  favoriteDocument,
  importUrl,
  listDocuments,
  listTags,
  reindexDocument,
  setDocumentTags,
  statusLabel,
  unfavoriteDocument,
  uploadFile,
  type DocumentItem,
  type TagItem,
} from "../api";
import { selectedKbId } from "../kb";

const docs = ref<DocumentItem[]>([]);
const tags = ref<TagItem[]>([]);
const error = ref("");
const note = ref("");
const url = ref("");
const newTag = ref("");
const onlyFav = ref(false);
const filterTag = ref("");
const panel = ref<"" | "file" | "url" | "note">("");
let timer: number | undefined;

async function refresh() {
  if (!selectedKbId.value) return;
  docs.value = await listDocuments(selectedKbId.value, {
    favorite: onlyFav.value || undefined,
    tagId: filterTag.value || undefined,
  });
  tags.value = await listTags();
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

async function onCreateTag() {
  if (!newTag.value.trim()) return;
  await createTag(newTag.value.trim());
  newTag.value = "";
  await refresh();
}

function toggleTag(doc: DocumentItem, tagId: string, ev: Event) {
  const on = (ev.target as HTMLInputElement).checked;
  const next = on ? [...doc.tag_ids, tagId] : doc.tag_ids.filter((id) => id !== tagId);
  setDocumentTags(doc.id, next).then(refresh);
}

async function toggleFav(doc: DocumentItem) {
  if (doc.is_favorite) await unfavoriteDocument(doc.id);
  else await favoriteDocument(doc.id);
  await refresh();
}

watch([selectedKbId, onlyFav, filterTag], () => {
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
        <button class="btn btn-primary" type="button" @click="panel = panel === 'file' ? '' : 'file'">上传文件</button>
        <button class="btn" type="button" @click="panel = panel === 'url' ? '' : 'url'">公开页 URL</button>
        <button class="btn" type="button" @click="panel = panel === 'note' ? '' : 'note'">Markdown 笔记</button>
      </div>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <section v-if="panel === 'file'" class="card form">
      <input type="file" @change="onUpload" />
    </section>
    <section v-if="panel === 'url'" class="card form">
      <input v-model="url" placeholder="https://…" />
      <button class="btn btn-primary" type="button" @click="onUrl">导入网址</button>
    </section>
    <section v-if="panel === 'note'" class="card form">
      <textarea v-model="note" rows="5" placeholder="Markdown 笔记"></textarea>
      <button class="btn btn-primary" type="button" @click="onNote">创建笔记</button>
    </section>

    <div class="filters">
      <button class="pill" :class="{ on: !filterTag }" type="button" @click="filterTag = ''">全部</button>
      <button
        v-for="t in tags"
        :key="t.id"
        class="pill"
        :class="{ on: filterTag === t.id }"
        type="button"
        @click="filterTag = t.id"
      >
        {{ t.name }}
      </button>
      <input v-model="newTag" class="new-tag" placeholder="+ 新建标签" @keyup.enter="onCreateTag" />
      <label class="fav"><input v-model="onlyFav" type="checkbox" /> 只看收藏</label>
    </div>

    <div class="table-wrap card">
      <table>
        <thead>
          <tr>
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
            <td>
              <RouterLink :to="`/documents/${doc.id}`">{{ doc.filename }}</RouterLink>
            </td>
            <td><span class="kind">{{ doc.kind }}</span></td>
            <td>
              <span class="st" :class="statusClass(doc.status)">{{ statusLabel(doc.status) }}</span>
            </td>
            <td class="err">{{ doc.error_message || "" }}</td>
            <td>
              <label v-for="t in tags" :key="t.id" class="tag-ck">
                <input
                  type="checkbox"
                  :checked="doc.tag_ids.includes(t.id)"
                  @change="toggleTag(doc, t.id, $event)"
                />
                {{ t.name }}
              </label>
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
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
  margin-bottom: 1rem;
}
.new-tag {
  border: 1px dashed var(--line);
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  background: transparent;
}
.fav {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.9rem;
}
.table-wrap {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
}
th,
td {
  padding: 0.75rem 0.8rem;
  text-align: left;
  border-bottom: 1px solid var(--line);
  font-size: 0.92rem;
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
.tag-ck {
  margin-right: 0.5rem;
  font-size: 0.8rem;
  color: #556;
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
</style>
