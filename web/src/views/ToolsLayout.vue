<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import Icon from "../components/Icon.vue";
import { navTree, type NavNode } from "../navConfig";

const route = useRoute();

const toolsNode = computed(() => navTree.value.find((n) => n.id === "tools"));

/** 分组（有可见子项）与平铺项（无子项的自定义节点）统一从导航树取 */
const groups = computed<NavNode[]>(() =>
  (toolsNode.value?.children ?? []).filter((g) => g.enabled),
);

function visibleChildren(group: NavNode): NavNode[] {
  return (group.children ?? []).filter((c) => c.enabled);
}

function isActive(to: string | undefined): boolean {
  if (!to) return false;
  const p = route.path;
  return p === to || p.startsWith(`${to}/`);
}

/** 当前命中的子项 to：取最长匹配，避免「我的行程单」同时命中「创建新行程」的前缀 */
const activeTo = computed<string>(() => {
  const p = route.path;
  let best = "";
  for (const g of groups.value) {
    for (const c of g.children ?? []) {
      if (!c.enabled || !c.to) continue;
      if (isActive(c.to) && c.to.length > best.length) best = c.to;
    }
  }
  return best;
});

function groupActive(group: NavNode): boolean {
  return visibleChildren(group).some((c) => c.to === activeTo.value);
}

const openMap = ref<Record<string, boolean>>({});
function isOpen(group: NavNode): boolean {
  return openMap.value[group.id] ?? true;
}
function toggleGroup(id: string) {
  openMap.value[id] = !(openMap.value[id] ?? true);
}
watch(
  () => route.path,
  () => {
    for (const g of groups.value) {
      if (groupActive(g)) openMap.value[g.id] = true;
    }
  },
  { immediate: true },
);
</script>

<template>
  <main class="page tools-page">
    <aside class="tools-nav" aria-label="工具二级菜单">
      <div class="nav-head">
        <h1 class="nav-title">工具</h1>
        <p class="nav-sub">发现更多 AI 工具，提升效率</p>
      </div>
      <div class="nav-card">
        <template v-for="g in groups" :key="g.id">
          <div v-if="visibleChildren(g).length" class="nav-group">
            <button
              type="button"
              class="nav-parent"
              :class="{ on: groupActive(g) }"
              :aria-expanded="isOpen(g)"
              @click="toggleGroup(g.id)"
            >
              <Icon :name="g.icon" />
              <span>{{ g.label }}</span>
              <Icon class="chev" name="chevron" />
            </button>
            <div v-show="isOpen(g)" class="nav-children">
              <RouterLink
                v-for="c in visibleChildren(g)"
                :key="c.id"
                :to="c.to || '#'"
                class="nav-child"
                active-class=""
                exact-active-class=""
                :class="{ on: activeTo === c.to }"
              >
                {{ c.label }}
              </RouterLink>
            </div>
          </div>
          <RouterLink
            v-else
            :to="g.to || '#'"
            class="nav-parent nav-parent-link"
            :class="{ on: isActive(g.to) }"
          >
            <Icon :name="g.icon" />
            <span>{{ g.label }}</span>
          </RouterLink>
        </template>
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
  width: 13.75rem;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.nav-head {
  margin: 0 0.15rem 0.85rem;
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
  padding: 0.45rem 0.4rem;
}
.nav-group + .nav-group {
  margin-top: 0.2rem;
}
.nav-parent {
  width: 100%;
  display: grid;
  grid-template-columns: 1.05rem 1fr 0.75rem;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.nav-parent:hover {
  background: #f8fafc;
}
.nav-parent.on {
  background: #eff6ff;
  color: var(--teal);
}
.nav-parent :deep(.ico) {
  width: 1rem;
  height: 1rem;
}
.nav-parent .chev {
  opacity: 0.55;
  color: #94a3b8;
  justify-self: end;
}
.nav-parent .chev :deep(svg) {
  transform: rotate(-90deg);
}
.nav-parent[aria-expanded="true"] .chev :deep(svg) {
  transform: rotate(0deg);
}
.nav-children {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.12rem 0 0.28rem 1.5rem;
}
.nav-child {
  display: block;
  padding: 0.42rem 0.5rem;
  border-radius: 8px;
  color: #4b5563;
  text-decoration: none;
  font-size: 0.78rem;
  font-weight: 400;
}
.nav-child:hover {
  background: #f8fafc;
  text-decoration: none;
}
.nav-child.on {
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 600;
}
.tools-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tools-main :deep(.placeholder-page) {
  padding: 0;
}
</style>
