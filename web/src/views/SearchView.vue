<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { listTags, searchChunks, type SearchHit, type TagItem } from "../api";
import { selectedKbId } from "../kb";

const query = ref("");
const tagId = ref("");
const kind = ref("");
const hits = ref<SearchHit[]>([]);
const tags = ref<TagItem[]>([]);
const error = ref("");

listTags().then((rows) => (tags.value = rows)).catch(() => undefined);

async function run() {
  error.value = "";
  try {
    hits.value = await searchChunks({
      query: query.value,
      knowledge_base_id: selectedKbId.value || undefined,
      tag_id: tagId.value || undefined,
      kind: kind.value || undefined,
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
</script>

<template>
  <h1>搜索</h1>
  <p>仅返回相似片段，不生成长答案。</p>
  <p v-if="error" class="err">{{ error }}</p>
  <p>
    <input v-model="query" size="40" @keyup.enter="run" />
    <select v-model="tagId">
      <option value="">标签不限</option>
      <option v-for="t in tags" :key="t.id" :value="t.id">{{ t.name }}</option>
    </select>
    <select v-model="kind">
      <option value="">类型不限</option>
      <option value="pdf">pdf</option>
      <option value="docx">docx</option>
      <option value="md">md</option>
      <option value="txt">txt</option>
      <option value="url">url</option>
      <option value="note">note</option>
    </select>
    <button type="button" @click="run">搜索</button>
  </p>
  <ol>
    <li v-for="hit in hits" :key="hit.chunk_id">
      <RouterLink :to="{ path: `/documents/${hit.document_id}`, hash: hashFor(hit) }">
        {{ hit.document_name }}
      </RouterLink>
      <span> · {{ hit.score.toFixed(3) }}</span>
      <p>{{ hit.content.slice(0, 240) }}</p>
    </li>
  </ol>
</template>

<style scoped>
.err {
  color: #a30;
}
</style>
