<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  listConversations,
  listDocuments,
  listKnowledgeBases,
  listTags,
  type Conversation,
  type DocumentItem,
} from "../api";
import { selectedKbId } from "../kb";

const router = useRouter();
const q = ref("");
const kbCount = ref(0);
const docCount = ref(0);
const tagCount = ref(0);
const recentDocs = ref<DocumentItem[]>([]);
const recentChats = ref<Conversation[]>([]);

onMounted(async () => {
  const [kbs, tags] = await Promise.all([listKnowledgeBases(), listTags()]);
  kbCount.value = kbs.length;
  tagCount.value = tags.length;
  if (selectedKbId.value) {
    const docs = await listDocuments(selectedKbId.value);
    docCount.value = docs.length;
    recentDocs.value = docs.slice(0, 5);
  }
  recentChats.value = (await listConversations(selectedKbId.value || undefined)).slice(0, 5);
});

function goChat() {
  router.push({ path: "/chat", query: q.value ? { q: q.value } : {} });
}
</script>

<template>
  <h1>首页</h1>
  <p>
    <input v-model="q" placeholder="向当前知识库提问" size="40" @keyup.enter="goChat" />
    <button type="button" @click="goChat">提问</button>
  </p>
  <p>知识库 {{ kbCount }} · 文档 {{ docCount }} · 标签 {{ tagCount }}</p>
  <h2>最近文档</h2>
  <ul>
    <li v-for="d in recentDocs" :key="d.id">
      <RouterLink :to="`/documents/${d.id}`">{{ d.filename }}</RouterLink>
    </li>
  </ul>
  <h2>最近对话</h2>
  <ul>
    <li v-for="c in recentChats" :key="c.id">
      <RouterLink :to="{ path: '/chat', query: { c: c.id } }">{{ c.title }}</RouterLink>
    </li>
  </ul>
</template>
