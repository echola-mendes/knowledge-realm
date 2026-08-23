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

async function onUpload(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  error.value = "";
  try {
    await uploadFile(selectedKbId.value, file);
    await refresh();
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
  <h1>文档</h1>
  <p v-if="error" class="err">{{ error }}</p>
  <section>
    <h2>导入</h2>
    <p><input type="file" @change="onUpload" /></p>
    <p>
      <input v-model="url" placeholder="公开页 URL" size="40" />
      <button type="button" @click="onUrl">导入网址</button>
    </p>
    <p>
      <textarea v-model="note" rows="4" cols="50" placeholder="Markdown 笔记"></textarea><br />
      <button type="button" @click="onNote">创建笔记</button>
    </p>
    <p>
      <input v-model="newTag" placeholder="新标签" />
      <button type="button" @click="onCreateTag">创建标签</button>
    </p>
    <p>
      <label><input v-model="onlyFav" type="checkbox" /> 只看收藏</label>
      <select v-model="filterTag">
        <option value="">全部标签</option>
        <option v-for="t in tags" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
    </p>
  </section>
  <table>
    <thead>
      <tr>
        <th>文件</th>
        <th>类型</th>
        <th>状态</th>
        <th>失败原因</th>
        <th>标签</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="doc in docs" :key="doc.id">
        <td>
          <RouterLink :to="`/documents/${doc.id}`">{{ doc.filename }}</RouterLink>
        </td>
        <td>{{ doc.kind }}</td>
        <td>{{ statusLabel(doc.status) }}</td>
        <td>{{ doc.error_message || "" }}</td>
        <td>
          <label v-for="t in tags" :key="t.id">
            <input
              type="checkbox"
              :checked="doc.tag_ids.includes(t.id)"
              @change="toggleTag(doc, t.id, $event)"
            />
            {{ t.name }}
          </label>
        </td>
        <td>
          <button type="button" @click="toggleFav(doc)">{{ doc.is_favorite ? "取消收藏" : "收藏" }}</button>
          <button type="button" @click="reindexDocument(doc.id).then(refresh)">重新处理</button>
          <button type="button" @click="deleteDocument(doc.id).then(refresh)">删除</button>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.err {
  color: #a30;
}
table {
  border-collapse: collapse;
  width: 100%;
}
th,
td {
  border: 1px solid #ddd;
  padding: 0.4rem;
  text-align: left;
}
</style>
