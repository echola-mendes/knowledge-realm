<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, RouterView } from "vue-router";
import Icon from "./components/Icon.vue";
import { knowledgeBases, loadKnowledgeBases, selectKb, selectedKbId } from "./kb";

onMounted(() => {
  loadKnowledgeBases().catch(() => undefined);
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <Icon name="book" />
        知域
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/"><Icon name="home" />首页</RouterLink>
        <RouterLink to="/documents"><Icon name="doc" />文档</RouterLink>
        <RouterLink to="/search"><Icon name="search" />搜索</RouterLink>
        <RouterLink to="/chat"><Icon name="chat" />对话</RouterLink>
        <RouterLink to="/settings"><Icon name="gear" />设置</RouterLink>
      </nav>
      <label class="kb-wrap">
        <Icon name="db" />
        <select class="kb-switch" :value="selectedKbId" @change="selectKb(($event.target as HTMLSelectElement).value)">
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
            {{ kb.is_default ? "默认" : kb.name }}
          </option>
        </select>
        <Icon name="chevron" />
      </label>
    </header>
    <RouterView />
    <footer class="footer-note">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</footer>
  </div>
</template>
