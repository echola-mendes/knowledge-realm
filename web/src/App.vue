<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { knowledgeBases, loadKnowledgeBases, selectKb, selectedKbId } from "./kb";

onMounted(() => {
  loadKnowledgeBases().catch(() => undefined);
});
</script>

<template>
  <div class="shell">
    <header>
      <strong>知域</strong>
      <nav>
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/documents">文档</RouterLink>
        <RouterLink to="/search">搜索</RouterLink>
        <RouterLink to="/chat">对话</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>
      <label>
        知识库
        <select :value="selectedKbId" @change="selectKb(($event.target as HTMLSelectElement).value)">
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
            {{ kb.name }}{{ kb.is_default ? "（默认）" : "" }}
          </option>
        </select>
      </label>
    </header>
    <p class="privacy">隐私说明：检索与问答时，文本片段会发往所配置的第三方 AI。</p>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: sans-serif;
  color: #222;
}
.shell header {
  display: flex;
  gap: 1.5rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #ddd;
}
nav {
  display: flex;
  gap: 1rem;
}
a {
  color: #245;
}
main {
  padding: 1rem;
}
.privacy {
  margin: 0;
  padding: 0.5rem 1rem;
  background: #f6f3e8;
  font-size: 0.9rem;
}
</style>
