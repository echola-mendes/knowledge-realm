<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import Icon from "../components/Icon.vue";
import { listTags, searchChunks, type SearchHit, type TagItem } from "../api";

const query = ref("");
const tagId = ref("");
const kind = ref("");
const createdAfter = ref("");
const createdBefore = ref("");

function toIso(local: string, endOfMinute = false) {
  if (!local.trim()) return undefined;
  const raw = local.length === 16 ? `${local}:00` : local;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return undefined;
  if (endOfMinute) d.setSeconds(59, 999);
  return d.toISOString();
}
const hits = ref<SearchHit[]>([]);
const tags = ref<TagItem[]>([]);
const error = ref("");
const ran = ref(false);
const kinds = ["pdf", "docx", "md", "txt", "url", "note"];

listTags()
  .then((rows) => (tags.value = rows))
  .catch(() => undefined);

async function run() {
  error.value = "";
  ran.value = true;
  try {
    hits.value = await searchChunks({
      query: query.value,
      tag_id: tagId.value || undefined,
      kind: kind.value || undefined,
      created_after: toIso(createdAfter.value),
      created_before: toIso(createdBefore.value, true),
    });
  } catch (e) {
    error.value = String(e);
  }
}

function hashFor(hit: SearchHit) {
  if (hit.page != null) return `#page-${hit.page}`;
  if (hit.heading) return `#${hit.heading}`;
  return "";
}

function pct(score: number) {
  return `${Math.round(score * 100)}%`;
}
</script>

<template>
  <main class="page">
    <section class="card search-card">
      <h1>搜索知识库</h1>
        <p class="sub">只返回已开启知识库中的相似片段，不生成长答案。点击文档名进入阅读页，可携带页锚点。</p>
      <p v-if="error" class="err">{{ error }}</p>
      <div class="bar">
        <div class="bar-field">
          <Icon name="search" />
          <input v-model="query" placeholder="输入关键词，例如：工作记忆模型" @keyup.enter="run" />
        </div>
        <button class="btn btn-primary" type="button" @click="run">
          <Icon name="search" />
          搜索
        </button>
      </div>
      <div class="row">
        <span>标签</span>
        <button class="pill" :class="{ on: !tagId }" type="button" @click="tagId = ''">全部</button>
        <button
          v-for="t in tags"
          :key="t.id"
          class="pill"
          :class="{ on: tagId === t.id }"
          type="button"
          @click="tagId = t.id"
        >
          {{ t.name }}
        </button>
      </div>
      <div class="row">
        <span>类型</span>
        <button class="pill" :class="{ on: !kind, soft: !kind }" type="button" @click="kind = ''">全部类型</button>
        <button
          v-for="k in kinds"
          :key="k"
          class="pill"
          :class="{ on: kind === k }"
          type="button"
          @click="kind = k"
        >
          {{ k }}
        </button>
      </div>
      <div class="row">
        <span>时间</span>
        <input v-model="createdAfter" type="datetime-local" aria-label="起始时间" />
        <input v-model="createdBefore" type="datetime-local" aria-label="结束时间" />
        <button class="pill" type="button" @click="createdAfter = ''; createdBefore = ''">不限时间</button>
      </div>
    </section>

    <p v-if="ran" class="meta">共 {{ hits.length }} 条结果 · 按相似度排序</p>

    <article v-for="hit in hits" :key="hit.chunk_id" class="card hit">
      <div class="score">
        <strong>{{ pct(hit.score) }}</strong>
        <span>相似度</span>
      </div>
      <div class="body">
        <header>
          <RouterLink :to="{ path: `/documents/${hit.document_id}`, hash: hashFor(hit) }">
            {{ hit.document_name }}
          </RouterLink>
          <span class="meta-pills">
            <em v-if="hit.kind">{{ hit.kind }}</em>
            <em v-if="hit.page != null">第 {{ hit.page }} 页</em>
          </span>
        </header>
        <p>{{ hit.content.slice(0, 220) }}</p>
        <RouterLink class="read" :to="{ path: `/documents/${hit.document_id}`, hash: hashFor(hit) }">
          阅读原文
        </RouterLink>
      </div>
    </article>
  </main>
</template>

<style scoped>
.search-card {
  padding: 1.3rem 1.3rem 1rem;
}
.search-card h1 {
  margin: 0 0 0.4rem;
}
.bar {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin: 1rem 0;
}
.bar-field {
  flex: 1;
  min-width: 12rem;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.15rem 0.9rem;
  color: var(--muted);
}
.bar-field input {
  flex: 1;
  border: none;
  outline: none;
  padding: 0.55rem 0;
  background: transparent;
}
.bar .btn-primary .ico {
  width: 15px;
  height: 15px;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.6rem;
}
.row > span {
  width: 2.4rem;
  color: var(--muted);
  font-size: 0.85rem;
}
.row input[type="datetime-local"] {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.25rem 0.7rem;
  background: #fff;
  color: var(--text);
  font-size: 0.8rem;
}
.meta {
  color: var(--muted);
  font-size: 0.88rem;
  margin: 1rem 0 0.7rem;
}
.hit {
  display: flex;
  gap: 1rem;
  padding: 1rem 1.1rem;
  margin-bottom: 0.75rem;
}
.score {
  min-width: 4.2rem;
  text-align: center;
  border-left: 3px solid var(--teal);
  padding-left: 0.7rem;
}
.score strong {
  display: block;
  color: var(--teal);
  font-size: 1.05rem;
}
.score span {
  color: var(--muted);
  font-size: 0.75rem;
}
.body {
  flex: 1;
  min-width: 0;
}
.body header {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.body header a {
  font-weight: 700;
}
.body p {
  color: var(--muted);
  margin: 0.45rem 0 0.6rem;
  line-height: 1.55;
}
.meta-pills em {
  font-style: normal;
  background: #eef1f4;
  color: #667;
  border-radius: 6px;
  padding: 0.1rem 0.4rem;
  font-size: 0.75rem;
  margin-left: 0.3rem;
}
.read {
  float: right;
  font-size: 0.88rem;
}
@media (max-width: 640px) {
  .hit {
    flex-direction: column;
  }
}
</style>
