<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { nextTick, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { getDocument, getParsedMarkdown, statusLabel, type DocumentItem } from "../api";
import { listTags, type TagItem } from "../api";

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
const doc = ref<DocumentItem | null>(null);
const tags = ref<TagItem[]>([]);

const pageHint = () => {
  const m = /^#page-(\d+)/.exec(route.hash);
  return m ? m[1] : "";
};

function tagName(id: string) {
  return tags.value.find((t) => t.id === id)?.name;
}

async function load() {
  error.value = "";
  try {
    const id = String(route.params.id);
    doc.value = await getDocument(id);
    tags.value = await listTags();
    const text = await getParsedMarkdown(id);
    html.value = md.render(text);
    await nextTick();
    if (route.hash) {
      document.querySelector(decodeURIComponent(route.hash))?.scrollIntoView();
    }
  } catch (e) {
    html.value = "";
    error.value = String(e);
  }
}

onMounted(load);
watch(() => [route.params.id, route.hash], load);
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
        <span v-for="id in doc.tag_ids" :key="id">{{ tagName(id) }}</span>
        <span class="right">{{ statusLabel(doc.status) }}</span>
      </div>
      <h1>{{ doc.filename }}</h1>
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
