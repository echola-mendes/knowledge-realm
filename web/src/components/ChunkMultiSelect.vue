<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import type { DebugDatasetChunk } from "../api";

const props = withDefaults(
  defineProps<{
    options: DebugDatasetChunk[];
    modelValue: string[];
    disabled?: boolean;
    placeholder?: string;
    hint?: string;
  }>(),
  {
    disabled: false,
    placeholder: "选择切片编号…",
    hint: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string[]];
  toggle: [chunkId: string];
}>();

const open = ref(false);
const filter = ref("");
const rootRef = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);
const listId = `chunk-list-${Math.random().toString(36).slice(2, 9)}`;

const selectedSet = computed(() => new Set(props.modelValue));

const optionById = computed(() => {
  const map = new Map<string, DebugDatasetChunk>();
  for (const o of props.options) map.set(o.chunk_id, o);
  return map;
});

const filtered = computed(() => {
  const q = filter.value.trim().toLowerCase();
  if (!q) return props.options;
  return props.options.filter((c) => c.chunk_label.toLowerCase().includes(q));
});

const selectedOptions = computed(() =>
  props.modelValue.map((id) => optionById.value.get(id)).filter((c): c is DebugDatasetChunk => !!c),
);

function openPanel() {
  if (props.disabled || !props.options.length) return;
  open.value = true;
  nextTick(() => searchRef.value?.focus());
}

function closePanel() {
  open.value = false;
  filter.value = "";
}

function onTriggerClick() {
  if (open.value) closePanel();
  else openPanel();
}

function onToggle(chunkId: string) {
  emit("toggle", chunkId);
}

function onRemoveChip(chunkId: string, e: Event) {
  e.stopPropagation();
  if (selectedSet.value.has(chunkId)) emit("toggle", chunkId);
}

function onDocClick(e: MouseEvent) {
  if (!open.value) return;
  const el = (e.target as HTMLElement).closest(".chunk-ms");
  if (!el) closePanel();
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value) return;
  if (e.key === "Escape") {
    e.preventDefault();
    closePanel();
    rootRef.value?.querySelector<HTMLButtonElement>(".chunk-ms-trigger")?.focus();
  }
}

watch(open, (v) => {
  if (v) {
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeydown);
  } else {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKeydown);
  }
});

onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div ref="rootRef" class="chunk-ms" :class="{ open, disabled }">
    <button
      type="button"
      class="chunk-ms-trigger"
      :disabled="disabled || !options.length"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :aria-controls="listId"
      @click.stop="onTriggerClick"
    >
      <span v-if="!selectedOptions.length" class="chunk-ms-placeholder">{{ placeholder }}</span>
      <span v-else class="chunk-ms-chips" role="list" aria-label="已选切片编号">
        <span v-for="c in selectedOptions" :key="c.chunk_id" class="chunk-ms-chip" role="listitem">
          <span class="chunk-ms-label">{{ c.chunk_label }}</span>
          <button
            type="button"
            class="chunk-ms-chip-x"
            :aria-label="`移除 ${c.chunk_label}`"
            @click="onRemoveChip(c.chunk_id, $event)"
          >
            ×
          </button>
        </span>
      </span>
      <span class="chunk-ms-end">
        <span v-if="modelValue.length" class="chunk-ms-count">{{ modelValue.length }}</span>
        <span class="chunk-ms-caret" aria-hidden="true">▾</span>
      </span>
    </button>

    <div v-if="open" class="chunk-ms-panel" @click.stop>
      <div class="chunk-ms-search-wrap">
        <label class="sr-only" for="chunk-ms-filter">搜索切片编号</label>
        <input
          id="chunk-ms-filter"
          ref="searchRef"
          v-model="filter"
          class="chunk-ms-search"
          type="search"
          placeholder="搜索 Chunk_1、Chunk_2…"
          autocomplete="off"
        />
      </div>
      <ul :id="listId" class="chunk-ms-list" role="listbox" aria-multiselectable="true" aria-label="切片编号列表">
        <li v-if="!filtered.length" class="chunk-ms-empty" role="option" aria-disabled="true">无匹配编号</li>
        <li
          v-for="c in filtered"
          :key="c.chunk_id"
          class="chunk-ms-item"
          :class="{ selected: selectedSet.has(c.chunk_id) }"
          role="option"
          :aria-selected="selectedSet.has(c.chunk_id)"
          @click="onToggle(c.chunk_id)"
        >
          <span class="chunk-ms-check" aria-hidden="true">
            <svg v-if="selectedSet.has(c.chunk_id)" viewBox="0 0 16 16" width="14" height="14">
              <path
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M3 8l3 3 7-7"
              />
            </svg>
          </span>
          <span class="chunk-ms-item-main">
            <span class="chunk-ms-label">{{ c.chunk_label }}</span>
            <span v-if="c.content" class="chunk-ms-preview">{{ c.content }}</span>
          </span>
        </li>
      </ul>
      <div class="chunk-ms-foot">
        <span>已选 {{ modelValue.length }} / 共 {{ options.length }}</span>
        <span v-if="hint" class="chunk-ms-foot-hint">{{ hint }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.chunk-ms {
  position: relative;
}

.chunk-ms-trigger {
  width: 100%;
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.45rem;
  padding: 0.35rem 0.45rem 0.35rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.chunk-ms.open .chunk-ms-trigger,
.chunk-ms-trigger:focus-visible {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
  outline: none;
}

.chunk-ms-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.chunk-ms-placeholder {
  flex: 1;
  color: var(--muted);
  font-size: 0.72rem;
}

.chunk-ms-chips {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  min-width: 0;
}

.chunk-ms-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  max-width: 100%;
  padding: 0.12rem 0.2rem 0.12rem 0.35rem;
  border-radius: 6px;
  background: var(--teal-soft);
  border: 1px solid var(--teal-mid);
  font-size: 0.68rem;
}

.chunk-ms-item .chunk-ms-label {
  font-family: ui-monospace, monospace;
  font-weight: 400;
  color: var(--text);
}

.chunk-ms-chip .chunk-ms-label {
  font-weight: 600;
  color: #1d4ed8;
}

.chunk-ms-chip-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
}

.chunk-ms-chip-x:hover {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.chunk-ms-chip-x:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
}

.chunk-ms-end {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
}

.chunk-ms-count {
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.3rem;
  border-radius: 999px;
  background: var(--teal);
  color: #fff;
  font-size: 0.62rem;
  font-weight: 600;
  line-height: 1.25rem;
  text-align: center;
}

.chunk-ms-caret {
  color: var(--muted);
  font-size: 0.75rem;
  transition: transform 0.15s;
}

.chunk-ms.open .chunk-ms-caret {
  transform: rotate(180deg);
}

.chunk-ms-panel {
  position: absolute;
  z-index: 30;
  top: calc(100% + 0.3rem);
  left: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  max-height: min(18rem, 50vh);
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  box-shadow: var(--shadow), 0 12px 32px rgba(15, 23, 42, 0.1);
  overflow: hidden;
}

.chunk-ms-search-wrap {
  padding: 0.45rem;
  border-bottom: 1px solid var(--line);
  background: #f8fafc;
}

.chunk-ms-search {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.45rem 0.55rem;
  font-size: 0.72rem;
  background: #fff;
}

.chunk-ms-search:focus-visible {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
  outline: none;
}

.chunk-ms-list {
  margin: 0;
  padding: 0.25rem 0;
  list-style: none;
  overflow: auto;
  flex: 1;
}

.chunk-ms-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.45rem 0.55rem;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.12s;
}

.chunk-ms-item:hover {
  background: #f8fafc;
}

.chunk-ms-item.selected {
  background: var(--teal-soft);
  border-left-color: var(--teal);
}

.chunk-ms-check {
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
  border: 1.5px solid #cbd5e1;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--teal);
  background: #fff;
}

.chunk-ms-item.selected .chunk-ms-check {
  border-color: var(--teal);
}

.chunk-ms-item-main {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  min-width: 0;
  flex: 1;
}

.chunk-ms-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.7rem;
  color: var(--muted);
}

.chunk-ms-empty {
  padding: 0.75rem 0.55rem;
  color: var(--muted);
  font-size: 0.72rem;
  text-align: center;
}

.chunk-ms-foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 0.5rem;
  padding: 0.4rem 0.55rem;
  border-top: 1px solid var(--line);
  background: #f8fafc;
  font-size: 0.64rem;
  color: var(--muted);
}

.chunk-ms-foot-hint {
  color: var(--warn);
}
</style>
