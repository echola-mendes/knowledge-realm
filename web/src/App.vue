<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { getMe, type AppUser } from "./api";
import Icon from "./components/Icon.vue";
import { knowledgeBases, loadKnowledgeBases, selectKb, selectedKb, selectedKbId } from "./kb";

const me = ref<AppUser | null>(null);
const initial = computed(() => (me.value?.name?.trim().charAt(0) || "?").toUpperCase());
const kbFullName = computed(() => {
  const kb = selectedKb.value;
  if (!kb) return "";
  return kb.is_default ? "默认" : kb.name;
});
const kbShortName = computed(() => {
  const name = kbFullName.value;
  return name.length > 3 ? `${name.slice(0, 3)}…` : name;
});

onMounted(() => {
  loadKnowledgeBases().catch(() => undefined);
  getMe()
    .then((row) => {
      me.value = row;
    })
    .catch(() => undefined);
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
      <div class="top-tools">
        <label class="kb-wrap" :title="kbFullName">
          <Icon name="db" />
          <span class="kb-short">{{ kbShortName }}</span>
          <select class="kb-switch" :value="selectedKbId" @change="selectKb(($event.target as HTMLSelectElement).value)">
            <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
              {{ kb.is_default ? "默认" : kb.name }}
            </option>
          </select>
          <Icon name="chevron" />
        </label>
        <div v-if="me" class="who">
          <span class="avatar" aria-hidden="true">{{ initial }}</span>
          <span class="who-name">{{ me.name }}</span>
        </div>
      </div>
    </header>
    <RouterView />
    <footer class="footer-note">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</footer>
  </div>
</template>
