<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { knowledgeBases, loadKnowledgeBases, selectKb, selectedKbId } from "./kb";

onMounted(() => {
  loadKnowledgeBases().catch(() => undefined);
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span aria-hidden="true">☰</span>
        知域
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/documents">文档</RouterLink>
        <RouterLink to="/search">搜索</RouterLink>
        <RouterLink to="/chat">对话</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>
      <select class="kb-switch" :value="selectedKbId" @change="selectKb(($event.target as HTMLSelectElement).value)">
        <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
          {{ kb.is_default ? "默认" : kb.name }}
        </option>
      </select>
    </header>
    <RouterView />
    <footer class="footer-note">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</footer>
  </div>
</template>
