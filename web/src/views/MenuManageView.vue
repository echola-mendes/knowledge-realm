<script setup lang="ts">
import { computed, ref, type Directive } from "vue";
import Icon from "../components/Icon.vue";
import { NAV_ITEMS, navConfig, resetNavConfig, saveNavConfig, type NavConfig } from "../navConfig";

const vFocus: Directive<HTMLElement> = {
  mounted(el) {
    el.focus();
    (el as HTMLInputElement).select();
  },
};

interface Row {
  match: string;
  label: string;
  icon: string;
  debug: boolean;
}

const rows = computed<Row[]>(() => {
  const { order, labels } = navConfig.value;
  const byMatch = new Map(NAV_ITEMS.map((item) => [item.match, item]));
  return order
    .map((match) => byMatch.get(match))
    .filter((item): item is (typeof NAV_ITEMS)[number] => Boolean(item))
    .map((item) => ({
      match: item.match,
      label: labels[item.match] ?? item.label,
      icon: item.icon,
      debug: item.match === "debug",
    }));
});

const editingMatch = ref<string | null>(null);
const draft = ref("");

function startEdit(row: Row) {
  editingMatch.value = row.match;
  draft.value = row.label;
}

function commitEdit() {
  const match = editingMatch.value;
  if (!match) return;
  const next: NavConfig = { order: [...navConfig.value.order], labels: { ...navConfig.value.labels } };
  const fallback = NAV_ITEMS.find((i) => i.match === match)?.label ?? match;
  next.labels[match] = draft.value.trim() || fallback;
  saveNavConfig(next);
  editingMatch.value = null;
}

function move(from: number, to: number) {
  if (to < 0 || to >= rows.value.length || to === from) return;
  const order = [...navConfig.value.order];
  const [item] = order.splice(from, 1);
  order.splice(to, 0, item);
  saveNavConfig({ order, labels: { ...navConfig.value.labels } });
}

const dragFrom = ref<number | null>(null);
const dragOver = ref<number | null>(null);

function onDragStart(index: number, ev: DragEvent) {
  dragFrom.value = index;
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", String(index));
  }
}

function onDragOver(index: number, ev: DragEvent) {
  if (dragFrom.value === null) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  dragOver.value = index;
}

function onDrop(index: number, ev: DragEvent) {
  ev.preventDefault();
  if (dragFrom.value !== null) move(dragFrom.value, index);
  dragFrom.value = null;
  dragOver.value = null;
}

function onDragEnd() {
  dragFrom.value = null;
  dragOver.value = null;
}
</script>

<template>
  <div class="menu-page">
    <div class="page-head">
      <div>
        <h1>菜单管理</h1>
        <p class="sub">拖拽或使用上下按钮调整侧边栏菜单顺序，点击名称可修改显示名。配置保存在本机浏览器。</p>
      </div>
      <button class="btn" type="button" @click="resetNavConfig()">恢复默认</button>
    </div>
    <div class="card pad">
      <ul class="menu-list">
        <li
          v-for="(row, index) in rows"
          :key="row.match"
          class="menu-row"
          :class="{ dragging: dragFrom === index, 'drop-target': dragOver === index && dragFrom !== index }"
          draggable="true"
          @dragstart="onDragStart(index, $event)"
          @dragover="onDragOver(index, $event)"
          @drop="onDrop(index, $event)"
          @dragend="onDragEnd"
        >
          <span class="grip" title="拖拽排序" aria-hidden="true"><Icon name="more" /></span>
          <span class="m-ico" aria-hidden="true"><Icon :name="row.icon" /></span>
          <input
            v-if="editingMatch === row.match"
            v-model="draft"
            v-focus
            class="m-input"
            type="text"
            maxlength="10"
            :aria-label="`菜单名称（${NAV_ITEMS.find((i) => i.match === row.match)?.label ?? row.match}）`"
            @keydown.enter.prevent="commitEdit"
            @keydown.esc="editingMatch = null"
            @blur="commitEdit"
          />
          <button v-else class="m-name" type="button" title="点击修改名称" @click="startEdit(row)">
            {{ row.label }}
          </button>
          <span v-if="row.debug" class="pill soft debug-pill">随调试开关显示</span>
          <span class="ops">
            <button
              class="op-btn"
              type="button"
              :disabled="index === 0"
              aria-label="上移"
              @click="move(index, index - 1)"
            >
              ↑
            </button>
            <button
              class="op-btn"
              type="button"
              :disabled="index === rows.length - 1"
              aria-label="下移"
              @click="move(index, index + 1)"
            >
              ↓
            </button>
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.menu-page {
  width: 100%;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
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
.menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.menu-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
  cursor: grab;
}
.menu-row.dragging {
  opacity: 0.5;
}
.menu-row.drop-target {
  border-color: var(--teal);
  box-shadow: inset 0 2px 0 var(--teal);
}
.grip {
  color: var(--muted);
  display: inline-flex;
}
.grip :deep(.ico) {
  width: 0.9rem;
  height: 0.9rem;
}
.m-ico {
  color: var(--muted);
  display: inline-flex;
}
.m-ico :deep(.ico) {
  width: 0.95rem;
  height: 0.95rem;
}
.m-name {
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text);
  cursor: text;
  padding: 0.15rem 0.3rem;
  border-radius: 6px;
}
.m-name:hover {
  background: #f8fafc;
}
.m-input {
  font: inherit;
  font-size: 0.78rem;
  padding: 0.15rem 0.3rem;
  border: 1px solid var(--teal);
  border-radius: 6px;
  width: 8rem;
}
.debug-pill {
  font-size: 0.62rem;
}
.ops {
  margin-left: auto;
  display: inline-flex;
  gap: 0.25rem;
}
.op-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--card);
  color: var(--muted);
  cursor: pointer;
  font-size: 0.75rem;
  line-height: 1;
}
.op-btn:hover:not(:disabled) {
  color: var(--teal);
  border-color: var(--teal);
}
.op-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
