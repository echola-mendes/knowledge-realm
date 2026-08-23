<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  createNote,
  deleteDocument,
  importUrl,
  listDocuments,
  reindexDocument,
  statusLabel,
  uploadFile,
  type DocumentItem,
} from "../api";
import { selectedKbId } from "../kb";

const docs = ref<DocumentItem[]>([]);
const error = ref("");
const note = ref("");
const url = ref("");
let timer: number | undefined;

async function refresh() {
  if (!selectedKbId.value) return;
  docs.value = await listDocuments(selectedKbId.value);
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
watch(selectedKbId, () => {
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
  </section>
  <table>
    <thead>
      <tr>
        <th>文件</th>
        <th>类型</th>
        <th>状态</th>
        <th>失败原因</th>
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
