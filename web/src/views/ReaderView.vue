<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import {
  autoTagDocument,
  createTag,
  documentStatusClass,
  documentStatusLabel,
  extractDocumentGraph,
  getDocument,
  getKnowledgeGraph,
  getParsedMarkdown,
  listRelatedDocuments,
  listTags,
  setDocumentTags,
  summarizeDocument,
  type DocumentItem,
  type KnowledgeGraph,
  type RelatedDocument,
  type TagItem,
} from "../api";
import Icon from "../components/Icon.vue";

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
const rawMd = ref("");
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

const systemInfo = computed(() => {
  const parts: string[] = [];
  if (graphError.value) parts.push(graphError.value);
  if (relatedError.value) parts.push(relatedError.value);
  return parts.join(" · ");
});

const showBody = computed(() => {
  const body = rawMd.value.replace(/\s+/g, " ").trim();
  if (!body) return false;
  const summary = (doc.value?.summary || "").replace(/\s+/g, " ").trim();
  if (!summary) return true;
  return body !== summary;
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
    rawMd.value = text;
    html.value = md.render(text);
    await loadSide();
    await nextTick();
    if (route.hash) {
      document.querySelector(decodeURIComponent(route.hash))?.scrollIntoView();
    }
  } catch (e) {
    html.value = "";
    rawMd.value = "";
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
    graphError.value = String(e);
  } finally {
    busy.value = "";
  }
}
</script>

<template>
  <main class="page reader-page">
    <header class="page-top">
      <nav class="crumb" aria-label="面包屑">
        <Icon name="folder" />
        <RouterLink to="/documents">文档</RouterLink>
        <span class="sep">/</span>
        <span class="current">{{ doc?.filename || "阅读" }}</span>
      </nav>
      <RouterLink class="back-link" to="/documents">← 返回文档列表</RouterLink>
    </header>

    <p v-if="pageHint()" class="loc-banner">已从搜索定位到 第 {{ pageHint() }} 页</p>
    <p v-if="error" class="hint err">{{ error }}</p>

    <section v-if="doc" class="hero card">
      <div class="hero-art" aria-hidden="true">
        <Icon name="doc" />
      </div>
      <div class="hero-top">
        <span class="kind-badge">
          <Icon name="doc" />
          {{ doc.kind }}
        </span>
        <span class="status-badge" :class="documentStatusClass(doc.status)">
          <Icon v-if="doc.status === 'ready'" name="check" />
          {{ documentStatusLabel(doc.status) }}
        </span>
      </div>
      <h1 class="hero-title">
        <span class="title-ico" aria-hidden="true"><Icon name="doc" /></span>
        {{ doc.filename }}
      </h1>
      <div class="tag-row" @click.stop>
        <span v-for="id in doc.tag_ids" :key="id" class="tag-chip">
          {{ tagName(id) }}
          <button class="tag-x" type="button" aria-label="移除标签" @click="removeTag(id)">×</button>
        </span>
        <div class="tag-more">
          <button
            class="tag-add"
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
      <div class="hero-actions">
        <button class="action-btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runSummarize">
          <Icon name="spark" />
          {{ busy === "summary" ? "摘要生成中…" : "生成摘要" }}
        </button>
        <button class="action-btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runAutoTags">
          <Icon name="tag" />
          {{ busy === "tags" ? "打标中…" : "自动标签" }}
        </button>
        <button class="action-btn" type="button" :disabled="doc.status !== 'ready' || !!busy" @click="runExtract">
          <Icon name="nodes" />
          {{ busy === "graph" ? "抽取中…" : "抽取图谱" }}
        </button>
        <RouterLink
          v-if="graph.entities.length"
          class="action-btn"
          :to="`/knowledge-graph?knowledgeBaseId=${doc.knowledge_base_id}&documentId=${doc.id}`"
        >
          <Icon name="nodes" />
          查看图谱
        </RouterLink>
      </div>
      <p v-if="doc.summary" class="hero-note">
        <Icon name="info" />
        <span>{{ doc.summary }}</span>
      </p>
    </section>

    <section v-if="doc" class="card pad info-card">
      <h2 class="info-head">
        <span class="info-head-ico"><Icon name="list" /></span>
        详情信息
      </h2>
      <div class="info-grid">
        <div class="info-cell">
          <div class="cell-head">
            <span class="row-ico blue"><Icon name="box" /></span>
            <span class="row-label">实体</span>
          </div>
          <div class="cell-value">
            <p v-if="!graph.entities.length" class="muted">暂无实体，可先抽取图谱</p>
            <ul v-else class="inline-list">
              <li v-for="item in graph.entities" :key="item.id">
                {{ item.name }} <em>{{ item.type }}</em>
              </li>
            </ul>
          </div>
        </div>
        <div class="info-cell">
          <div class="cell-head">
            <span class="row-ico purple"><Icon name="doc" /></span>
            <span class="row-label">相近文档</span>
          </div>
          <div class="cell-value">
            <ul v-if="related.length" class="related-list">
              <li v-for="item in related" :key="item.document_id">
                <RouterLink :to="`/documents/${item.document_id}`">{{ item.document_name }}</RouterLink>
                <span class="score">{{ item.score.toFixed(2) }}</span>
              </li>
            </ul>
            <span v-else class="muted">—</span>
          </div>
        </div>
        <div class="info-cell">
          <div class="cell-head">
            <span class="row-ico green"><Icon name="link" /></span>
            <span class="row-label">关系</span>
          </div>
          <div class="cell-value">
            <p v-if="!graph.links.length" class="muted">暂无关系</p>
            <ul v-else class="inline-list">
              <li v-for="(item, idx) in graph.links" :key="`${item.from_id}-${item.to_id}-${item.rel}-${idx}`">
                {{ entityName(item.from_id) }} · {{ item.rel }} · {{ entityName(item.to_id) }}
              </li>
            </ul>
          </div>
        </div>
        <div class="info-cell">
          <div class="cell-head">
            <span class="row-ico red"><Icon name="alert" /></span>
            <span class="row-label">系统信息</span>
          </div>
          <div class="cell-value" :class="{ 'err-text': systemInfo }">{{ systemInfo || "—" }}</div>
        </div>
      </div>
    </section>

    <section v-if="doc?.summary" class="tip-card">
      <span class="tip-ico"><Icon name="bell" /></span>
      <div>
        <strong>提示</strong>
        <p>{{ doc.summary }}</p>
      </div>
    </section>

    <section v-if="showBody" class="card pad body-card">
      <h2 class="body-title">正文</h2>
      <article class="body" v-html="html"></article>
    </section>
  </main>
</template>

<style scoped>
.reader-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem;
  font-size: 12.5px;
}
.page-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.85rem;
}
.crumb {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0;
  color: var(--muted);
  font-size: 0.72rem;
}
.crumb a {
  color: var(--teal);
  text-decoration: none;
}
.crumb a:hover {
  text-decoration: underline;
}
.crumb .sep,
.crumb .current {
  color: var(--muted);
}
.crumb :deep(.ico) {
  width: 0.95rem;
  height: 0.95rem;
}
.back-link {
  flex-shrink: 0;
  color: var(--teal);
  text-decoration: none;
  font-size: 0.72rem;
  transition: color 0.2s ease;
}
.back-link:hover {
  text-decoration: underline;
}
.back-link:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
  border-radius: 4px;
}
.loc-banner {
  margin: 0 0 0.75rem;
  padding: 0.55rem 0.75rem;
  border-radius: 10px;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.72rem;
}
.hero {
  position: relative;
  overflow: hidden;
  padding: 1rem 1.15rem 1.1rem;
  margin-bottom: 0.75rem;
  border: 1px solid #dbeafe;
  background: linear-gradient(118deg, #f8fbff 0%, #edf5ff 45%, #f3f8ff 100%);
  box-shadow: var(--shadow);
}
.hero-art {
  position: absolute;
  right: 0.35rem;
  top: 0.15rem;
  opacity: 0.1;
  pointer-events: none;
}
.hero-art :deep(.ico) {
  width: 7rem;
  height: 7rem;
  stroke: var(--teal);
}
.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.6rem;
}
.kind-badge,
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 999px;
  padding: 0.14rem 0.58rem;
  font-size: 0.62rem;
  font-weight: 600;
  line-height: 1.2;
}
.kind-badge {
  background: var(--teal-soft);
  color: var(--teal);
}
.kind-badge :deep(.ico),
.status-badge :deep(.ico) {
  width: 0.72rem;
  height: 0.72rem;
}
.status-badge.ok {
  background: #ecfdf5;
  color: var(--ok);
}
.status-badge.busy {
  background: #fff7ed;
  color: var(--warn);
}
.status-badge.idle {
  background: var(--chrome);
  color: var(--muted);
}
.status-badge.bad {
  background: #fef2f2;
  color: var(--danger);
}
.hero-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.7rem;
  font-size: 1.08rem;
  font-weight: 700;
  color: #1e40af;
  line-height: 1.3;
}
.title-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 9px;
  background: var(--teal-soft);
}
.title-ico :deep(.ico) {
  width: 1.05rem;
  height: 1.05rem;
  stroke: var(--teal);
}
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  margin-bottom: 0.8rem;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  border-radius: 999px;
  padding: 0.1rem 0.48rem 0.1rem 0.55rem;
  background: var(--chrome);
  color: var(--text);
  font-size: 0.68rem;
}
.tag-x {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--muted);
  padding: 0;
  min-width: 1rem;
  min-height: 1rem;
  line-height: 1;
}
.tag-x:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
  border-radius: 4px;
}
.tag-add {
  border: 1px dashed #93c5fd;
  border-radius: 999px;
  background: transparent;
  color: var(--teal);
  padding: 0.1rem 0.58rem;
  font-size: 0.68rem;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.tag-add:hover:not(:disabled) {
  background: var(--teal-soft);
}
.tag-add:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  transition: background 0.2s ease;
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
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.32rem;
  min-height: 2rem;
  border: 1px solid #93c5fd;
  border-radius: 999px;
  background: var(--card);
  color: var(--teal);
  padding: 0.32rem 0.72rem;
  font-size: 0.68rem;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.action-btn:hover:not(:disabled) {
  background: var(--teal-soft);
}
.action-btn:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
}
.action-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.action-btn :deep(.ico) {
  width: 0.85rem;
  height: 0.85rem;
}
.hero-note {
  display: flex;
  align-items: flex-start;
  gap: 0.38rem;
  margin: 0.82rem 0 0;
  padding-top: 0.75rem;
  border-top: 1px dashed #bfdbfe;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.55;
}
.hero-note :deep(.ico) {
  width: 0.92rem;
  height: 0.92rem;
  flex-shrink: 0;
  margin-top: 0.08rem;
  stroke: var(--muted);
}
.info-card {
  margin-bottom: 0.75rem;
  padding: 0.85rem 1rem 1rem;
}
.info-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0 0 0.75rem;
  font-size: 0.82rem;
  font-weight: 650;
  color: var(--text);
}
.info-head-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 8px;
  background: var(--teal-soft);
  color: var(--teal);
}
.info-head-ico :deep(.ico) {
  width: 0.78rem;
  height: 0.78rem;
}
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}
.info-cell {
  padding: 0.65rem 0.75rem 0.75rem 0;
  min-width: 0;
}
.info-cell:nth-child(odd) {
  padding-right: 1rem;
  border-right: 1px dashed var(--line);
}
.info-cell:nth-child(even) {
  padding-left: 1rem;
}
.info-cell:nth-child(-n + 2) {
  border-bottom: 1px dashed var(--line);
  padding-bottom: 0.85rem;
  margin-bottom: 0.1rem;
}
.info-cell:nth-child(n + 3) {
  padding-top: 0.75rem;
}
.cell-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.35rem;
}
.cell-value {
  min-width: 0;
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--text);
  padding-left: 1.75rem;
}
.row-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 999px;
  flex-shrink: 0;
}
.row-ico :deep(.ico) {
  width: 0.75rem;
  height: 0.75rem;
}
.row-ico.blue {
  background: var(--teal-soft);
  color: var(--teal);
}
.row-ico.green {
  background: #dcfce7;
  color: var(--ok);
}
.row-ico.purple {
  background: #ede9fe;
  color: #7c3aed;
}
.row-ico.red {
  background: #fee2e2;
  color: var(--danger);
}
.row-label {
  color: var(--text);
  font-size: 0.72rem;
  font-weight: 600;
}
.muted {
  margin: 0;
  color: var(--muted);
}
.err-text {
  color: var(--danger);
  word-break: break-word;
}
.inline-list,
.related-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.inline-list li + li,
.related-list li + li {
  margin-top: 0.28rem;
}
.inline-list em {
  color: var(--muted);
  font-style: normal;
  margin-left: 0.25rem;
}
.related-list a {
  color: var(--teal);
  text-decoration: none;
}
.related-list a:hover {
  text-decoration: underline;
}
.related-list .score {
  margin-left: 0.35rem;
  color: var(--muted);
  font-size: 0.65rem;
}

@media (max-width: 640px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  .info-cell:nth-child(odd) {
    border-right: none;
    padding-right: 0;
  }
  .info-cell:nth-child(even) {
    padding-left: 0;
  }
  .info-cell:nth-child(-n + 3) {
    border-bottom: 1px dashed var(--line);
    padding-bottom: 0.85rem;
    margin-bottom: 0.1rem;
  }
  .info-cell:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }
}
.tip-card {
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  margin-bottom: 0.75rem;
  padding: 0.78rem 0.9rem;
  border-radius: var(--radius);
  background: #fff7ed;
  border: 1px solid #fed7aa;
}
.tip-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.55rem;
  height: 1.55rem;
  border-radius: 999px;
  background: #ffedd5;
  flex-shrink: 0;
}
.tip-ico :deep(.ico) {
  width: 0.88rem;
  height: 0.88rem;
  stroke: var(--warn);
}
.tip-card strong {
  display: block;
  margin-bottom: 0.18rem;
  font-size: 0.72rem;
  color: #9a3412;
}
.tip-card p {
  margin: 0;
  font-size: 0.72rem;
  color: #7c2d12;
  line-height: 1.55;
}
.body-card {
  margin-bottom: 0.75rem;
}
.body-title {
  margin: 0 0 0.55rem;
  font-size: 0.78rem;
  color: var(--muted);
  font-weight: 600;
}
.body {
  line-height: 1.7;
  font-size: 0.82rem;
}
.body :deep(h2[id^="page-"]) {
  background: var(--teal-soft);
  border-radius: 8px;
  padding: 0.35rem 0.5rem;
}
.empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.68rem;
}

@media (prefers-reduced-motion: reduce) {
  .back-link,
  .action-btn,
  .tag-add,
  .tag-pop-item {
    transition: none;
  }
}
</style>
