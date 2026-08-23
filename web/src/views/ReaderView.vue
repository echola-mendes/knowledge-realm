<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getParsedMarkdown } from "../api";

const route = useRoute();
const md = new MarkdownIt();
const html = ref("");
const error = ref("");

async function load() {
  error.value = "";
  try {
    const text = await getParsedMarkdown(String(route.params.id));
    html.value = md.render(text);
  } catch (e) {
    html.value = "";
    error.value = String(e);
  }
}

onMounted(load);
watch(() => route.params.id, load);
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
