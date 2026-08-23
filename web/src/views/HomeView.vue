<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  listConversations,
  listDocuments,
  listKnowledgeBases,
  listTags,
  type Conversation,
  type DocumentItem,
  type TagItem,
} from "../api";
import { selectedKb, selectedKbId } from "../kb";

const router = useRouter();
const q = ref("");
const kbCount = ref(0);
const docCount = ref(0);
const tagCount = ref(0);
const recentDocs = ref<DocumentItem[]>([]);
const recentChats = ref<Conversation[]>([]);
const tags = ref<TagItem[]>([]);

const kbLabel = computed(() => (selectedKb.value?.is_default ? "默认" : selectedKb.value?.name || "默认"));

function tagName(id: string) {
  return tags.value.find((t) => t.id === id)?.name;
}

onMounted(async () => {
  const [kbs, tagRows] = await Promise.all([listKnowledgeBases(), listTags()]);
  kbCount.value = kbs.length;
  tags.value = tagRows;
  tagCount.value = tagRows.length;
  const kbId = selectedKbId.value || kbs.find((k) => k.is_default)?.id || kbs[0]?.id;
  if (kbId) {
    const docs = await listDocuments(kbId);
    docCount.value = docs.length;
    recentDocs.value = docs.slice(0, 4);
  }
  recentChats.value = (await listConversations(kbId || undefined)).slice(0, 4);
});

function goChat() {
  router.push({ path: "/chat", query: q.value ? { q: q.value } : {} });
}
</script>

<template>
  <main class="page">
    <section class="card hero">
      <span class="badge">当前知识库：{{ kbLabel }}</span>
      <h1>今天，想从知识库里发现什么？</h1>
      <p class="sub">向当前库提问，回答会带来源引用；也可先去搜索只看相似片段。</p>
      <div class="ask">
        <input
          v-model="q"
          placeholder="例如：梳理文档的核心结论…"
          @keyup.enter="goChat"
        />
        <button class="btn btn-primary" type="button" @click="goChat">提问 →</button>
      </div>
      <p class="hint">Enter 提问，支持多轮追问，引用可点击回到原文</p>
    </section>

    <section class="grid-3 stats">
      <div class="card stat">
        <strong>{{ kbCount }}</strong>
        <span>知识库</span>
      </div>
      <div class="card stat">
        <strong>{{ docCount }}</strong>
        <span>文档</span>
      </div>
      <div class="card stat">
        <strong>{{ tagCount }}</strong>
        <span>标签</span>
      </div>
    </section>

    <section class="grid-2 lists">
      <div class="card list-card">
        <header>
          <h2>最近文档</h2>
          <RouterLink to="/documents">查看全部 →</RouterLink>
        </header>
        <RouterLink v-for="d in recentDocs" :key="d.id" class="row" :to="`/documents/${d.id}`">
          <span class="name">{{ d.filename }}</span>
          <span v-if="d.tag_ids?.[0]" class="mini">{{ tagName(d.tag_ids[0]) }}</span>
          <span class="kind">{{ d.kind }}</span>
        </RouterLink>
        <p v-if="!recentDocs.length" class="empty">暂无文档</p>
      </div>
      <div class="card list-card">
        <header>
          <h2>最近对话</h2>
          <RouterLink to="/chat">查看全部 →</RouterLink>
        </header>
        <RouterLink
          v-for="c in recentChats"
          :key="c.id"
          class="row"
          :to="{ path: '/chat', query: { c: c.id } }"
        >
          <span class="name">{{ c.title }}</span>
        </RouterLink>
        <p v-if="!recentChats.length" class="empty">暂无对话</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.hero {
  padding: 1.6rem 1.5rem 1.2rem;
}
.badge {
  display: inline-block;
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.8rem;
}
.hero h1 {
  margin: 0.7rem 0 0.4rem;
  font-size: clamp(1.35rem, 3vw, 1.75rem);
}
.ask {
  display: flex;
  gap: 0.6rem;
  margin-top: 1rem;
  flex-wrap: wrap;
}
.ask input {
  flex: 1;
  min-width: 12rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.7rem 0.85rem;
}
.hint,
.empty {
  color: var(--muted);
  font-size: 0.85rem;
}
.stats {
  margin: 1rem 0;
}
.stat {
  padding: 1.1rem 1.2rem;
}
.stat strong {
  display: block;
  font-size: 1.8rem;
}
.stat span {
  color: var(--muted);
}
.list-card {
  padding: 1rem 1.1rem 0.5rem;
}
.list-card header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.list-card h2 {
  margin: 0;
  font-size: 1.05rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
}
.row:first-of-type {
  margin-top: 0.5rem;
}
.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini,
.kind {
  font-size: 0.75rem;
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.4rem;
  color: #556;
}
</style>
