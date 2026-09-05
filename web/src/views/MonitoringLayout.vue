<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import Icon from "../components/Icon.vue";

const route = useRoute();
const onDecisions = computed(() => route.path.startsWith("/monitoring/decisions"));
const onOperations = computed(() => route.path.startsWith("/monitoring/operations"));
</script>

<template>
  <main class="page tools-page">
    <aside class="tools-nav" aria-label="监控二级菜单">
      <div class="nav-head">
        <h1 class="nav-title">监控</h1>
        <p class="nav-sub">决策链路与系统操作的可追溯审计。</p>
      </div>
      <div class="nav-card">
        <RouterLink
          to="/monitoring/decisions"
          class="nav-parent nav-parent-link"
          :class="{ on: onDecisions }"
        >
          <Icon name="spark" />
          <span>决策审计</span>
        </RouterLink>
        <RouterLink
          to="/monitoring/operations"
          class="nav-parent nav-parent-link"
          :class="{ on: onOperations }"
        >
          <Icon name="list" />
          <span>操作审计</span>
        </RouterLink>
      </div>
    </aside>
    <section class="tools-main">
      <RouterView />
    </section>
  </main>
</template>

<style scoped>
.tools-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  background: transparent;
  display: flex;
  gap: 1rem;
  align-items: stretch;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.tools-nav {
  width: min(12.5rem, 28vw);
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.nav-head {
  margin: 0 0.25rem 1rem;
  flex-shrink: 0;
}
.nav-title {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.nav-sub {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.nav-card {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 0.75rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.nav-parent {
  width: 100%;
  display: grid;
  grid-template-columns: 1rem 1fr;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.4rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #4b5563;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  text-decoration: none;
  box-sizing: border-box;
}
.nav-parent:hover {
  background: #f8fafc;
  text-decoration: none;
}
.nav-parent.on {
  background: var(--teal-soft);
  color: var(--teal);
}
.nav-parent :deep(.ico) {
  width: 0.95rem;
  height: 0.95rem;
}
.tools-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
