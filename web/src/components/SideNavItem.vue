<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import Icon from "./Icon.vue";
import { PAGE_SECTION_IDS, type NavNode } from "../navConfig";
import { debugEnabled } from "../debugFlag";

const props = defineProps<{ node: NavNode; depth: number }>();

const route = useRoute();
const open = ref(false);

const children = computed<NavNode[]>(() => {
  // 工具/基础/监控：页内二级菜单，侧栏不展开
  if (PAGE_SECTION_IDS.has(props.node.id)) return [];
  if (props.depth >= 2) return [];
  return (props.node.children ?? []).filter((c) => c.enabled && !(c.id === "debug" && !debugEnabled.value));
});
const hasChildren = computed(() => children.value.length > 0);

function descendantActive(nodes: NavNode[]): boolean {
  for (const n of nodes) {
    if (isActive(n) || (n.children && descendantActive(n.children))) return true;
  }
  return false;
}

function isActive(node: NavNode): boolean {
  if (node.custom) {
    return route.name === "custom-menu" && route.params.menuId === node.id;
  }
  const p = route.path;
  const qMode = typeof route.query.mode === "string" ? route.query.mode : "";
  switch (node.id) {
    case "home":
      return p === "/";
    case "chat":
      return p === "/chat" && qMode !== "report";
    case "kbs":
      return p === "/knowledge-bases";
    case "docs":
      return p === "/documents" || p.startsWith("/documents/");
    case "search":
      return p === "/search";
    case "debug":
      return p === "/debug";
    case "settings":
      return p === "/settings";
    case "knowledge-graph":
      return p === "/knowledge-graph";
    case "insights":
      return p === "/insights";
    case "tools":
      return p === "/tools" || p.startsWith("/tools/");
    case "monitoring":
      return p === "/monitoring" || p.startsWith("/monitoring/");
    case "basics":
      return p === "/basics" || p.startsWith("/basics/");
    default:
      return false;
  }
}

watch(
  () => route.fullPath,
  () => {
    if (hasChildren.value && descendantActive(children.value)) open.value = true;
  },
  { immediate: true },
);

function toggle() {
  open.value = !open.value;
}
</script>

<template>
  <div class="side-item" :class="`depth-${depth}`">
    <component
      :is="hasChildren ? 'button' : 'RouterLink'"
      v-if="node.to || hasChildren"
      :to="hasChildren ? undefined : node.to"
      :class="{ on: isActive(node) || (hasChildren && open && descendantActive(children)) }"
      class="side-link"
      type="button"
      @click="hasChildren ? toggle() : undefined"
    >
      <Icon :name="node.icon" />
      <span class="nav-label">{{ node.label }}</span>
      <span v-if="hasChildren" class="sub-chev" :class="{ open }" aria-hidden="true"></span>
    </component>
    <div v-if="hasChildren && open" class="sub-list" :class="`sub-depth-${depth}`">
      <SideNavItem v-for="c in children" :key="c.id" :node="c" :depth="depth + 1" />
    </div>
  </div>
</template>

<style scoped>
.side-item {
  display: flex;
  flex-direction: column;
}
.side-link {
  position: relative;
  display: grid;
  grid-template-columns: var(--rail) minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-content: start;
  min-height: 3.6rem;
  margin: 0;
  padding: 0.35rem 0 0.35rem;
  border: none;
  background: none;
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  font: inherit;
  width: 100%;
  box-sizing: border-box;
}
.side-link:hover {
  background: #eff6ff;
  color: #2563eb;
}
.side-link.on {
  background: #eff6ff;
  color: #2563eb;
}
.sub-list {
  display: flex;
  flex-direction: column;
  padding-bottom: 0.3rem;
}
.sub-depth-0 {
  border-top: 1px dashed #e5e7eb;
}
.sub-list :deep(.side-link) {
  min-height: 2.7rem;
  padding-top: 0.25rem;
  padding-bottom: 0.25rem;
  grid-template-columns: 1.6rem calc(var(--rail) - 1.6rem);
  font-size: 0.68rem;
}
.sub-list :deep(.side-link .ico) {
  width: 13px;
  height: 13px;
  margin: 0 auto;
}
.sub-depth-1 :deep(.side-link) {
  grid-template-columns: 2.6rem calc(var(--rail) - 2.6rem);
}
.sub-chev {
  position: absolute;
  right: 0.3rem;
  top: 0.55rem;
  width: 0.32rem;
  height: 0.32rem;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(45deg);
  transition: transform 0.15s;
}
.sub-chev.open {
  transform: rotate(-135deg);
  top: 0.65rem;
}
</style>
