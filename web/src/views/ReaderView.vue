<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getParsedMarkdown } from "../api";

const route = useRoute();
const md = new MarkdownIt();
const defaultOpen = md.renderer.rules.heading_open || ((tokens, idx, options, env, slf) => slf.renderToken(tokens, idx, options));
md.renderer.rules.heading_open = (tokens, idx, options, env, slf) => {
  const text = tokens[idx + 1]?.content || "";
  const page = /Page\s+(\d+)/i.exec(text);
  tokens[idx].attrSet("id", page ? `page-${page[1]}` : text.slice(0, 40));
  return defaultOpen(tokens, idx, options, env, slf);
};
const html = ref("");
const error = ref("");

async function load() {
  error.value = "";
  try {
    const text = await getParsedMarkdown(String(route.params.id));
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
  <h1>阅读</h1>
  <p v-if="error" class="err">{{ error }}</p>
  <article v-else v-html="html"></article>
</template>

<style scoped>
.err {
  color: #a30;
}
article {
  max-width: 48rem;
  line-height: 1.5;
}
</style>
