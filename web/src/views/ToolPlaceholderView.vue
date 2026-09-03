<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "工具"));
const sub = computed(() => String(route.meta.sub ?? "功能即将推出。"));
</script>

<template>
  <div class="placeholder-page">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p class="sub">{{ sub }}</p>
      </div>
    </div>
    <div class="card pad empty-card">
      <p class="empty-title">即将推出</p>
      <p class="empty-desc">当前为菜单占位，具体能力后续接入。</p>
    </div>
  </div>
</template>

<style scoped>
.placeholder-page {
  width: 100%;
  padding: 0;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-shrink: 0;
}
.page-head h1 {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
  line-height: 1.5;
}
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.pad {
  padding: 1.25rem 1.1rem;
}
.empty-card {
  text-align: left;
  flex: 1;
  min-height: 0;
}
.empty-title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.empty-desc {
  margin: 0.45rem 0 0;
  max-width: 32rem;
  color: var(--muted);
  font-size: 0.75rem;
  line-height: 1.55;
}
</style>
