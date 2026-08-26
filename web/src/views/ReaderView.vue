<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import {
  autoTagDocument,
  createTag,
  extractDocumentGraph,
  getDocument,
  getKnowledgeGraph,
  getParsedMarkdown,
  listRelatedDocuments,
  listTags,
  setDocumentTags,
  statusLabel,
  summarizeDocument,
  type DocumentItem,
  type KnowledgeGraph,
  type RelatedDocument,
  type TagItem,
} from "../api";

const route = useRoute();
const md = new MarkdownIt();
const defaultOpen =
  md.renderer.rules.heading_open || ((tokens, idx, options, env, slf) => slf.renderToken(tokens, idx, options));
md.renderer.rules.heading_open = (tokens, idx, options, env, slf) => {
  const text = tokens[idx + 1]?.content || "";
  const page = /Page\s+(\d+)/i.exec(text);
  tokens[idx].attrSet("id", page ? `page-${page[1]}` : text.slice(0, 40));
  return defaultOpen(tokens, idx, options, env, slf);
};
const html = ref("");
const error = ref("");
const busy = ref("");
const doc = ref<DocumentItem | null>(null);
const tags = ref<TagItem[]>([]);
const graph = ref<KnowledgeGraph>({ entities: [], links: [] });
const related = ref<RelatedDocument[]>([]);
const graphError = ref("");
const relatedError = ref("");
const tagPickOpen = ref(false);
const newTag = ref("");
const MAX_DOC_TAGS = 5;
const unusedTags = computed(() => {
  if (!doc.value) return [];
  const used = new Set(doc.value.tag_ids);
  return tags.value.filter((t) => !used.has(t.id));
});

const pageHint = () => {
  const m = /^#page-(\d+)/.exec(route.hash);
  return m ? m[1] : "";
};

function entityName(id: string) {
  return graph.value.entities.find((item) => item.id === id)?.name || id.slice(0, 8);
}

function tagName(id: string) {
  return tags.value.find((t) => t.id === id)?.name;
}

async function loadSide() {
  graphError.value = "";
  relatedError.value = "";
  graph.value = { entities: [], links: [] };
  related.value = [];
  if (!doc.value) return;
  try {
    graph.value = await getKnowledgeGraph({
      knowledgeBaseId: doc.value.knowledge_base_id,
      documentId: doc.value.id,
    });
  } catch (e) {
    graphError.value = String(e);
  }
  try {
    related.value = await listRelatedDocuments(doc.value.id);
  } catch (e) {
    relatedError.value = String(e);
  }
}

async function load() {
  error.value = "";
  try {
    const id = String(route.params.id);
    doc.value = await getDocument(id);
    tags.value = await listTags();
    const text = await getParsedMarkdown(id);
    html.value = md.render(text);
    await loadSide();
    await nextTick();
    if (route.hash) {
      document.querySelector(decodeURIComponent(route.hash))?.scrollIntoView();
    }
  } catch (e) {
    html.value = "";
    error.value = String(e);
  }
}

onMounted(() => {
  load();
  document.addEventListener("click", closeTagPick);
});
onUnmounted(() => {
  document.removeEventListener("click", closeTagPick);
});
watch(() => [route.params.id, route.hash], load);

function closeTagPick() {
  tagPickOpen.value = false;
}

async function saveTags(ids: string[]) {
  if (!doc.value) return;
  error.value = "";
  try {
    doc.value = await setDocumentTags(doc.value.id, ids);
  } catch (e) {
    error.value = String(e);
  }
}

async function addTag(id: string) {
  if (!doc.value || doc.value.tag_ids.includes(id)) return;
  if (doc.value.tag_ids.length >= MAX_DOC_TAGS) {
    error.value = "一篇文档最多5个标签";
    return;
  }
  await saveTags([...doc.value.tag_ids, id]);
  tagPickOpen.value = false;
}

async function removeTag(id: string) {
  if (!doc.value) return;
  await saveTags(doc.value.tag_ids.filter((item) => item !== id));
}

async function createAndAttach() {
  const name = newTag.value.trim();
  if (!name || !doc.value) return;
  if (doc.value.tag_ids.length >= MAX_DOC_TAGS) {
    error.value = "一篇文档最多5个标签";
    return;
  }
  error.value = "";
  try {
    const created = await createTag(name);
    tags.value = await listTags();
    newTag.value = "";
    if (!doc.value.tag_ids.includes(created.id)) {
      await saveTags([...doc.value.tag_ids, created.id]);
    }
    tagPickOpen.value = false;
  } catch (e) {
    error.value = String(e);
  }
}

async function runSummarize() {
  if (!doc.value || busy.value) return;
  error.value = "";
  busy.value = "summary";
  try {
    doc.value = await summarizeDocument(doc.value.id);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = "";
  }
}

async function runAutoTags() {
  if (!doc.value || busy.value) return;
  error.value = "";
  busy.value = "tags";
  try {
    doc.value = await autoTagDocument(doc.value.id);
    tags.value = await listTags();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = "";
  }
}

async function runExtract() {
  if (!doc.value || busy.value) return;
  error.value = "";
  graphError.value = "";
  busy.value = "graph";
  try {
    graph.value = await extractDocumentGraph(doc.value.id);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <main class="page">
    <div class="crumb">
      <span>文档 / {{ doc?.filename || "阅读" }}</span>
      <RouterLink to="/documents">返回文档列表</RouterLink>
    </div>
    <p v-if="pageHint()" class="banner">已从搜索定位到 第 {{ pageHint() }} 页</p>
    <p v-if="error" class="err">{{ error }}</p>
    <section v-if="doc" class="card meta">
      <div class="chips">
        <span>{{ doc.kind }}</span>
        <span class="right">{{ statusLabel(doc.status) }}</span>
      </div>
      <h1>{{ doc.filename }}</h1>
      <div class="tag-edit" @click.stop>
        <span v-for="id in doc.tag_ids" :key="id" class="tag-chip">
          {{ tagName(id) }}
          <button class="tag-x" type="button" aria-label="移除标签" @click="removeTag(id)">×</button>
        </span>
        <span v-if="!doc.tag_ids.length" class="empty">暂无标签</span>
        <div class="tag-more">
          <button
            class="btn"
            type="button"
            :disabled="doc.tag_ids.length >= MAX_DOC_TAGS || !!busy"
            @click="tagPickOpen = !tagPickOpen"
          >
            + 标签
          </button>
          <div v-if="tagPickOpen" class="tag-pop">
            <p v-if="!unusedTags.length" class="empty">没有更多已有标签</p>
            <button
              v-for="t in unusedTags"
              :key="t.id"
              class="tag-pop-item"
              type="button"
              @click="addTag(t.id)"
            >
              {{ t.name }}
            </button>
            <input
              v-model="newTag"
              class="new-tag"
              placeholder="+ 新建标签"
              :disabled="doc.tag_ids.length >= MAX_DOC_TAGS"
              @keyup.enter="createAndAttach"
            />
          </div>
        </div>
      </div>
      <div class="p1-actions">
        <button class="btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runSummarize">
          {{ busy === "summary" ? "摘要生成中…" : "生成摘要" }}
        </button>
        <button class="btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runAutoTags">
          {{ busy === "tags" ? "打标中…" : "自动标签" }}
        </button>
        <button class="btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runExtract">
          {{ busy === "graph" ? "抽取中…" : "抽取图谱" }}
        </button>
      </div>
      <p v-if="doc.summary" class="summary">{{ doc.summary }}</p>
    </section>
    <section v-if="doc" class="card graph-panel">
      <h2>实体</h2>
      <p v-if="graphError" class="err">{{ graphError }}</p>
      <p v-else-if="!graph.entities.length" class="empty">暂无实体，可先抽取图谱</p>
      <ul v-else class="plain-list">
        <li v-for="item in graph.entities" :key="item.id">
          {{ item.name }}
          <span class="type">{{ item.type }}</span>
        </li>
      </ul>
      <h2>关系</h2>
      <p v-if="!graphError && !graph.links.length" class="empty">暂无关系</p>
      <ul v-else-if="!graphError" class="plain-list">
        <li v-for="(item, idx) in graph.links" :key="`${item.from_id}-${item.to_id}-${item.rel}-${idx}`">
          {{ entityName(item.from_id) }}
          <span class="rel">{{ item.rel }}</span>
          {{ entityName(item.to_id) }}
        </li>
      </ul>
      <h2>相近文档</h2>
      <p v-if="relatedError" class="err">{{ relatedError }}</p>
      <p v-else-if="!related.length" class="empty">暂无相近文档</p>
      <ul v-else class="plain-list related">
        <li v-for="item in related" :key="item.document_id">
          <RouterLink :to="`/documents/${item.document_id}`">{{ item.document_name }}</RouterLink>
          <span class="score">{{ item.score.toFixed(2) }}</span>
          <p class="snippet">{{ item.content }}</p>
        </li>
      </ul>
    </section>
    <article class="card body" v-html="html"></article>
  </main>
</template>

<style scoped>
.crumb {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.8rem;
  color: var(--muted);
}
.banner {
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 10px;
  padding: 0.65rem 0.9rem;
}
.meta {
  padding: 1.1rem 1.2rem;
  margin-bottom: 1rem;
}
.meta h1 {
  margin: 0.5rem 0 0;
  font-size: clamp(1.3rem, 3vw, 1.7rem);
}
.p1-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.85rem;
}
.summary {
  margin: 0.85rem 0 0;
  color: var(--muted);
  line-height: 1.6;
}
.graph-panel {
  padding: 1.1rem 1.2rem;
  margin-bottom: 1rem;
}
.graph-panel h2 {
  margin: 0.85rem 0 0.4rem;
  font-size: 0.95rem;
}
.graph-panel h2:first-child {
  margin-top: 0;
}
.empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}
.plain-list {
  margin: 0;
  padding-left: 1.1rem;
  line-height: 1.7;
}
.plain-list .type,
.plain-list .rel,
.plain-list .score {
  color: var(--muted);
  font-size: 0.82rem;
  margin-left: 0.35rem;
}
.related .snippet {
  margin: 0.15rem 0 0.55rem;
  color: var(--muted);
  font-size: 0.86rem;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.chips span {
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.45rem;
  font-size: 0.78rem;
  color: #556;
}
.chips .right {
  margin-left: auto;
  background: var(--teal-soft);
  color: var(--teal);
}
.tag-edit {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-top: 0.75rem;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.4rem 0.1rem 0.45rem;
  font-size: 0.78rem;
  color: #556;
}
.tag-x {
  border: none;
  background: none;
  cursor: pointer;
  color: #889;
  padding: 0 0.1rem;
  line-height: 1;
}
.tag-more {
  position: relative;
}
.tag-pop {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 20;
  min-width: 11rem;
  max-height: 16rem;
  overflow: auto;
  padding: 0.4rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.tag-pop-item {
  border: none;
  background: transparent;
  text-align: left;
  border-radius: 8px;
  padding: 0.35rem 0.55rem;
  cursor: pointer;
}
.tag-pop-item:hover {
  background: var(--teal-soft);
  color: var(--teal);
}
.new-tag {
  border: 1px dashed var(--line);
  border-radius: 8px;
  padding: 0.35rem 0.5rem;
  background: transparent;
}
.body {
  padding: 1.3rem 1.4rem;
  line-height: 1.7;
}
.body :deep(h2[id^="page-"]) {
  background: var(--teal-soft);
  border-radius: 8px;
  padding: 0.35rem 0.5rem;
}
</style>
