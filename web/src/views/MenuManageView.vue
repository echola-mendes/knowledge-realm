<script setup lang="ts">
import { computed, ref, type Directive } from "vue";
import Icon from "../components/Icon.vue";
import {
  MAX_MENU_DEPTH,
  NAV_ITEMS,
  PAGE_SECTION_IDS,
  navTree,
  newNavNode,
  resetNavConfig,
  saveNavTree,
  type NavNode,
} from "../navConfig";

const vFocus: Directive<HTMLInputElement> = {
  mounted(el) {
    el.focus();
    el.select();
  },
};

interface Row {
  node: NavNode;
  parentId: string | null;
  index: number;
  depth: number;
  siblingCount: number;
}

const rows = computed<Row[]>(() => {
  const list: Row[] = [];
  const walk = (nodes: NavNode[], parentId: string | null, depth: number) => {
    nodes.forEach((node, index) => {
      list.push({ node, parentId, index, depth, siblingCount: nodes.length });
      if (node.children?.length) walk(node.children, node.id, depth + 1);
    });
  };
  walk(navTree.value, null, 0);
  return list;
});

const editingId = ref<string | null>(null);
const draft = ref("");
// 待命名的节点：新增后立刻进入输入状态
const pendingId = ref<string | null>(null);

function startEdit(row: Row) {
  editingId.value = row.node.id;
  draft.value = row.node.label;
}

function commitEdit() {
  const id = editingId.value;
  if (!id) return;
  const label = draft.value.trim();
  editingId.value = null;
  if (!label) {
    if (pendingId.value === id) {
      // 新增节点未命名：移除
      removeById(id, true);
      pendingId.value = null;
    }
    return;
  }
  const tree = cloneTree(navTree.value);
  const node = findNode(tree, id);
  if (node) node.label = label.slice(0, 10);
  saveNavTree(tree);
  pendingId.value = null;
}

function cloneTree(nodes: NavNode[]): NavNode[] {
  return nodes.map((n) => ({ ...n, children: n.children ? cloneTree(n.children) : undefined }));
}

function findNode(nodes: NavNode[], id: string): NavNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      const hit = findNode(n.children, id);
      if (hit) return hit;
    }
  }
  return null;
}

function findSiblings(tree: NavNode[], parentId: string | null): NavNode[] | null {
  if (parentId === null) return tree;
  const parent = findNode(tree, parentId);
  if (!parent) return null;
  if (!parent.children) parent.children = [];
  return parent.children;
}

function canAddChild(row: Row): boolean {
  return row.depth < MAX_MENU_DEPTH - 1 && !PAGE_SECTION_IDS.has(row.node.id);
}

function addMenu(parentId: string | null) {
  if (parentId && PAGE_SECTION_IDS.has(parentId)) return;
  const tree = cloneTree(navTree.value);
  const siblings = findSiblings(tree, parentId);
  if (!siblings) return;
  const node = newNavNode("新菜单");
  siblings.push(node);
  saveNavTree(tree);
  pendingId.value = node.id;
  editingId.value = node.id;
  draft.value = node.label;
}

function removeById(id: string, silent = false) {  const tree = cloneTree(navTree.value);
  const row = rows.value.find((r) => r.node.id === id);
  const siblings = row ? findSiblings(tree, row.parentId) : null;
  if (!siblings) return;
  const idx = siblings.findIndex((n) => n.id === id);
  if (idx < 0) return;
  if (!silent) {
    const target = siblings[idx];
    const extra = target.children?.length ? "其下级菜单将一并删除，" : "";
    if (!window.confirm(`确定删除菜单「${target.label}」？${extra}该操作可用「恢复默认」撤销。`)) return;
  }
  siblings.splice(idx, 1);
  saveNavTree(tree);
}

function cancelEdit(id: string) {
  const wasPending = pendingId.value === id;
  editingId.value = null;
  if (wasPending) {
    removeById(id, true);
    pendingId.value = null;
  }
}

function toggleEnabled(row: Row, value: boolean) {
  const tree = cloneTree(navTree.value);
  const node = findNode(tree, row.node.id);
  if (!node) return;
  node.enabled = value;
  saveNavTree(tree);
}

function moveSibling(row: Row, dir: -1 | 1) {
  const to = row.index + dir;
  if (to < 0 || to >= row.siblingCount) return;
  const tree = cloneTree(navTree.value);
  const siblings = findSiblings(tree, row.parentId);
  if (!siblings) return;
  const [item] = siblings.splice(row.index, 1);
  siblings.splice(to, 0, item);
  saveNavTree(tree);
}

const dragFrom = ref<{ parentId: string | null; index: number } | null>(null);
const dragOver = ref<string | null>(null);

function onDragStart(row: Row, ev: DragEvent) {
  dragFrom.value = { parentId: row.parentId, index: row.index };
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", row.node.id);
  }
}
function onDragOver(row: Row, ev: DragEvent) {
  if (!dragFrom.value || dragFrom.value.parentId !== row.parentId) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  dragOver.value = row.node.id;
}
function onDrop(row: Row, ev: DragEvent) {
  ev.preventDefault();
  if (dragFrom.value && dragFrom.value.parentId === row.parentId) {
    moveSibling({ ...row, index: dragFrom.value.index }, row.index - dragFrom.value.index > 0 ? 1 : -1);
  }
  dragFrom.value = null;
  dragOver.value = null;
}
function onDragEnd() {
  dragFrom.value = null;
  dragOver.value = null;
}

function fallbackLabel(id: string) {
  return NAV_ITEMS.find((i) => i.match === id)?.label ?? id;
}
</script>

<template>
  <div class="menu-page">
    <div class="page-head">
      <div>
        <h1>菜单管理</h1>
        <p class="sub">
          支持最多 {{ MAX_MENU_DEPTH }} 级菜单：点击名称修改显示名，用开关控制是否在侧边栏显示，可新增、编辑、删除与拖拽排序。工具 / 基础 / 监控为页内二级入口，侧栏不展开子菜单。配置保存在本机浏览器。
        </p>
      </div>
      <div class="head-actions">
        <button class="btn" type="button" @click="addMenu(null)">+ 添加菜单</button>
        <button class="btn" type="button" @click="resetNavConfig()">恢复默认</button>
      </div>
    </div>
    <div class="card pad list-card">
      <ul class="menu-list">
        <li
          v-for="row in rows"
          :key="row.node.id"
          class="menu-row"
          :class="[
            `depth-${row.depth}`,
            {
              dragging: dragFrom?.parentId === row.parentId && dragFrom.index === row.index,
              'drop-target': dragOver === row.node.id && dragFrom?.parentId === row.parentId,
            },
          ]"
          draggable="true"
          @dragstart="onDragStart(row, $event)"
          @dragover="onDragOver(row, $event)"
          @drop="onDrop(row, $event)"
          @dragend="onDragEnd"
        >
          <span class="grip" title="拖拽排序" aria-hidden="true"><Icon name="more" /></span>
          <span class="m-ico" aria-hidden="true"><Icon :name="row.node.icon" /></span>
          <input
            v-if="editingId === row.node.id"
            v-model="draft"
            v-focus
            class="m-input"
            type="text"
            maxlength="10"
            :aria-label="`菜单名称（${fallbackLabel(row.node.id)}）`"
            @keydown.enter.prevent="commitEdit"
            @keydown.esc="cancelEdit(row.node.id)"
            @blur="commitEdit"
          />
          <button v-else class="m-name" type="button" title="点击修改名称" @click="startEdit(row)">
            {{ row.node.label }}
          </button>
          <span v-if="row.node.id === 'debug'" class="pill soft debug-pill">随调试开关显示</span>
          <span v-if="PAGE_SECTION_IDS.has(row.node.id)" class="pill soft debug-pill">页内二级</span>
          <span v-if="canAddChild(row)" class="add-child">
            <button class="op-btn" type="button" aria-label="添加子菜单" title="添加子菜单" @click="addMenu(row.node.id)">
              +
            </button>
          </span>
          <label class="switch" :title="row.node.enabled ? '已开启，点击关闭' : '已关闭，点击开启'">
            <input
              type="checkbox"
              :checked="row.node.enabled"
              :aria-label="`是否开启菜单 ${row.node.label}`"
              @change="toggleEnabled(row, ($event.target as HTMLInputElement).checked)"
            />
            <span class="track" aria-hidden="true"></span>
          </label>
          <span class="ops">
            <button
              class="op-btn"
              type="button"
              :disabled="row.index === 0"
              aria-label="上移"
              @click="moveSibling(row, -1)"
            >
              ↑
            </button>
            <button
              class="op-btn"
              type="button"
              :disabled="row.index === row.siblingCount - 1"
              aria-label="下移"
              @click="moveSibling(row, 1)"
            >
              ↓
            </button>
            <button
              class="op-btn danger"
              type="button"
              aria-label="删除菜单"
              title="删除菜单"
              @click="removeById(row.node.id)"
            >
              ×
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
  min-width: 0;
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
.head-actions {
  display: flex;
  gap: 0.4rem;
  flex-shrink: 0;
}
.list-card {
  margin: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
  min-height: 0;
  overflow: auto;
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
.menu-row.depth-1 {
  margin-left: 1.4rem;
}
.menu-row.depth-2 {
  margin-left: 2.8rem;
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
.add-child {
  display: inline-flex;
}
.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  margin-left: auto;
  flex-shrink: 0;
}
.switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.switch .track {
  width: 2.1rem;
  height: 1.15rem;
  border-radius: 999px;
  background: #cbd5e1;
  position: relative;
  transition: background 0.15s;
  flex-shrink: 0;
}
.switch .track::after {
  content: "";
  position: absolute;
  top: 0.14rem;
  left: 0.14rem;
  width: 0.87rem;
  height: 0.87rem;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.2);
  transition: transform 0.15s;
}
.switch input:checked + .track {
  background: var(--teal);
}
.switch input:checked + .track::after {
  transform: translateX(0.95rem);
}
.switch input:focus-visible + .track {
  outline: 2px solid var(--teal-soft);
  outline-offset: 1px;
}
.ops {
  display: inline-flex;
  gap: 0.25rem;
  flex-shrink: 0;
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
.op-btn.danger:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}
.op-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
