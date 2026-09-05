<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  getNewsHot,
  getNewsSettings,
  putNewsSettings,
  type NewsHotItem,
} from "../api";

const CHANNELS = [
  { key: "all", label: "全部" },
  { key: "technology", label: "科技" },
  { key: "ai", label: "AI" },
  { key: "finance", label: "金融" },
] as const;

const SETTING_OPTIONS = [
  { key: "technology", label: "科技" },
  { key: "ai", label: "AI" },
  { key: "finance", label: "金融" },
] as const;

const CATEGORY_LABEL: Record<string, string> = {
  technology: "科技",
  ai: "AI",
  finance: "金融",
};

const channel = ref<(typeof CHANNELS)[number]["key"]>("all");
const enabled = ref<string[]>(["technology", "ai", "finance"]);
const items = ref<NewsHotItem[]>([]);
const boardDate = ref("");
const loading = ref(true);
const savingSettings = ref(false);
const error = ref("");
const settingsError = ref("");

function formatBoardDate(isoDate: string): string {
  if (!isoDate) return "";
  const [y, m, d] = isoDate.split("-");
  if (!y || !m || !d) return isoDate;
  return `${y}年${m}月${d}日`;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diffMs = Date.now() - t;
  if (diffMs < 0) return "刚刚";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}天前`;
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function heatText(score: number | null): string {
  if (score == null || Number.isNaN(score)) return "—";
  return String(Math.round(score));
}

function isEnabled(key: string): boolean {
  return enabled.value.includes(key);
}

async function loadHot() {
  loading.value = true;
  error.value = "";
  try {
    const hot = await getNewsHot({ category: channel.value });
    boardDate.value = hot.date;
    items.value = hot.items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadSettings() {
  settingsError.value = "";
  try {
    const s = await getNewsSettings();
    enabled.value = [...s.enabled_categories];
  } catch (e) {
    settingsError.value = e instanceof Error ? e.message : "设置加载失败";
  }
}

async function toggleCategory(key: string) {
  if (savingSettings.value) return;
  const next = isEnabled(key)
    ? enabled.value.filter((c) => c !== key)
    : [...enabled.value, key];
  if (!next.length) {
    settingsError.value = "至少启用一个分类";
    return;
  }
  savingSettings.value = true;
  settingsError.value = "";
  const prev = [...enabled.value];
  enabled.value = next;
  try {
    const s = await putNewsSettings(next);
    enabled.value = [...s.enabled_categories];
  } catch (e) {
    enabled.value = prev;
    settingsError.value = e instanceof Error ? e.message : "保存失败";
  } finally {
    savingSettings.value = false;
  }
}

watch(channel, () => {
  loadHot().catch(() => undefined);
});

onMounted(() => {
  Promise.all([loadSettings(), loadHot()]).catch(() => undefined);
});
</script>

<template>
  <div class="news-page">
    <div class="page-head">
      <h1>AI资讯</h1>
      <p class="sub">按启用板块采集的今日热榜；切换频道仅影响浏览，不改变采集范围。</p>
    </div>

    <section class="card pad">
      <div class="settings-row">
        <span class="settings-label">启用板块</span>
        <div class="checks" role="group" aria-label="启用板块">
          <label v-for="opt in SETTING_OPTIONS" :key="opt.key" class="check">
            <input
              type="checkbox"
              :checked="isEnabled(opt.key)"
              :disabled="savingSettings"
              @change="toggleCategory(opt.key)"
            />
            <span>{{ opt.label }}</span>
          </label>
        </div>
      </div>
      <p v-if="settingsError" class="hint err">{{ settingsError }}</p>

      <div class="tabs" role="tablist" aria-label="浏览频道">
        <button
          v-for="item in CHANNELS"
          :key="item.key"
          type="button"
          role="tab"
          :class="{ on: channel === item.key }"
          :aria-selected="channel === item.key"
          @click="channel = item.key"
        >
          {{ item.label }}
        </button>
      </div>

      <div class="board-head">
        <h2 class="block-title">今日热榜</h2>
        <span v-if="boardDate" class="board-date">{{ formatBoardDate(boardDate) }}</span>
      </div>

      <p v-if="error" class="hint err">{{ error }}</p>
      <p v-else-if="loading" class="hint">加载中…</p>
      <p v-else-if="!items.length" class="hint">暂无资讯</p>
      <ol v-else class="news-list">
        <li v-for="row in items" :key="row.id" class="news-item">
          <span class="rank">{{ String(row.rank).padStart(2, "0") }}</span>
          <div class="body">
            <RouterLink class="title" :to="`/tools/news/${row.id}`">{{ row.title }}</RouterLink>
            <p v-if="row.summary" class="summary">{{ row.summary }}</p>
            <div class="meta">
              <span>{{ CATEGORY_LABEL[row.category] || row.category }}</span>
              <span>·</span>
              <span>{{ row.source }}</span>
              <span>·</span>
              <span>{{ formatRelative(row.published_at) }}</span>
            </div>
          </div>
          <span class="heat" :title="`热度 ${heatText(row.heat_score)}`">{{ heatText(row.heat_score) }}</span>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.news-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  font-size: 12.5px;
  background: transparent;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
.page-head h1 {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.page-head .sub {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.card.pad {
  padding: 0.85rem 1rem 1rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.settings-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 0.85rem;
  margin-bottom: 0.55rem;
}
.settings-label {
  font-size: 0.68rem;
  color: var(--muted);
}
.checks {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 0.85rem;
}
.check {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
  color: var(--text);
  cursor: pointer;
}
.check input {
  accent-color: var(--teal);
}
.tabs {
  display: flex;
  flex-wrap: nowrap;
  gap: 0;
  margin: 0 0 0.7rem;
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
}
.tabs button {
  border: none;
  background: none;
  border-radius: 0;
  padding: 0.35rem 0.7rem 0.45rem;
  cursor: pointer;
  color: var(--muted);
  font: inherit;
  font-size: 0.72rem;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tabs button.on {
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.board-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.45rem;
}
.block-title {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 650;
  color: var(--text);
}
.board-date {
  font-size: 0.72rem;
  color: var(--muted);
}
.hint {
  margin: 0.35rem 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.hint.err {
  color: var(--danger);
}
.news-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.news-item {
  display: grid;
  grid-template-columns: 2rem 1fr auto;
  gap: 0.55rem;
  align-items: start;
  padding: 0.65rem 0;
  border-top: 1px solid var(--line);
}
.news-item:first-child {
  border-top: none;
}
.rank {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--muted);
  line-height: 1.35;
}
.body {
  min-width: 0;
}
.title {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
  line-height: 1.35;
}
.title:hover {
  color: var(--teal);
  text-decoration: underline;
}
.summary {
  margin: 0.28rem 0 0;
  font-size: 0.72rem;
  color: var(--muted);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.meta {
  margin-top: 0.28rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  font-size: 0.68rem;
  color: var(--muted);
}
.heat {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--teal);
  line-height: 1.35;
  min-width: 1.5rem;
  text-align: right;
}
</style>
