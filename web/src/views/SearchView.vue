<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { RouterLink } from "vue-router";
import Icon from "../components/Icon.vue";
import { listKnowledgeBases, listTags, searchChunks, type KnowledgeBase, type SearchHit, type TagItem } from "../api";

const query = ref("");
const tagId = ref("");
const kind = ref("");
const kbId = ref("");
const createdAfter = ref("");
const createdBefore = ref("");
const topK = ref(5);

const hits = ref<SearchHit[]>([]);
const tags = ref<TagItem[]>([]);
const kbs = ref<KnowledgeBase[]>([]);
const error = ref("");
const ran = ref(false);
const searching = ref(false);
const elapsedMs = ref(0);
const activeTab = ref("result");
const tagsOpen = ref(false);
const tagLimit = 10;
const visibleTags = computed(() => (tagsOpen.value ? tags.value : tags.value.slice(0, tagLimit)));
const overflowTags = computed(() => tags.value.slice(tagLimit));
const kinds = ["pdf", "docx", "md", "txt", "url", "note"];
const tabs = [
  { key: "result", label: "搜索结果" },
  { key: "visual", label: "可视化分布" },
  { key: "concept", label: "关联概念" },
  { key: "trend", label: "时间趋势" },
];

listTags()
  .then((rows) => (tags.value = rows))
  .catch(() => undefined);
listKnowledgeBases()
  .then((rows) => (kbs.value = rows))
  .catch(() => undefined);

const HISTORY_KEY = "search-history-v1";
type HistoryItem = { query: string; count: number; at: number };
const history = ref<HistoryItem[]>(loadHistory());

function loadHistory(): HistoryItem[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}
function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value.slice(0, 20)));
}
function pushHistory(count: number) {
  const q = query.value.trim();
  if (!q) return;
  history.value = [
    { query: q, count, at: Date.now() },
    ...history.value.filter((h) => h.query !== q),
  ];
  saveHistory();
}
function clearHistory() {
  history.value = [];
  saveHistory();
}
const hotSearches = computed(() => {
  const freq = new Map<string, number>();
  for (const h of history.value) freq.set(h.query, (freq.get(h.query) || 0) + 1);
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([q, n], i) => ({ rank: i + 1, query: q, count: n }));
});

function timeAgo(at: number) {
  const m = Math.floor((Date.now() - at) / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m}分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}小时前`;
  return `${Math.floor(h / 24)}天前`;
}

const SAVED_KEY = "search-saved-v1";
type SavedItem = {
  query: string;
  tagId: string;
  kind: string;
  kbId: string;
  createdAfter: string;
  createdBefore: string;
  at: number;
};
const savedSearches = ref<SavedItem[]>(loadSaved());

function loadSaved(): SavedItem[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]");
  } catch {
    return [];
  }
}
function saveSaved() {
  localStorage.setItem(SAVED_KEY, JSON.stringify(savedSearches.value.slice(0, 10)));
}
function saveSearch() {
  const q = query.value.trim();
  if (!q) return;
  const item: SavedItem = {
    query: q,
    tagId: tagId.value,
    kind: kind.value,
    kbId: kbId.value,
    createdAfter: createdAfter.value,
    createdBefore: createdBefore.value,
    at: Date.now(),
  };
  savedSearches.value = [item, ...savedSearches.value.filter((s) => s.query !== q)];
  saveSaved();
}
function applySaved(s: SavedItem) {
  query.value = s.query;
  tagId.value = s.tagId;
  kind.value = s.kind;
  kbId.value = s.kbId;
  createdAfter.value = s.createdAfter;
  createdBefore.value = s.createdBefore;
  run();
}
function removeSaved(s: SavedItem) {
  savedSearches.value = savedSearches.value.filter((x) => x.query !== s.query);
  saveSaved();
}

function toIso(local: string, endOfDay = false) {
  if (!local.trim()) return undefined;
  const date = local.slice(0, 10);
  const d = new Date(`${date}T00:00`);
  if (Number.isNaN(d.getTime())) return undefined;
  if (endOfDay) d.setDate(d.getDate() + 1);
  return d.toISOString();
}
const p2 = (n: number) => String(n).padStart(2, "0");
function fmtLocal(d: Date) {
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
}
const quickPick = ref("");
const dateOpen = ref(false);
const dateWrap = ref<HTMLElement | null>(null);
const calCursor = ref(new Date());
const rangeAnchor = ref("");
const weekLabels = ["日", "一", "二", "三", "四", "五", "六"];
const calTitle = computed(() => `${calCursor.value.getFullYear()}年${calCursor.value.getMonth() + 1}月`);
const calCells = computed(() => {
  const y = calCursor.value.getFullYear();
  const m = calCursor.value.getMonth();
  const firstDow = new Date(y, m, 1).getDay();
  const last = new Date(y, m + 1, 0).getDate();
  const cells: (string | null)[] = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= last; d++) cells.push(fmtLocal(new Date(y, m, d)));
  return cells;
});
function inRange(iso: string) {
  if (!createdAfter.value || !createdBefore.value) return iso === createdAfter.value;
  return iso >= createdAfter.value && iso <= createdBefore.value;
}
function shiftMonth(delta: number) {
  const d = new Date(calCursor.value);
  d.setMonth(d.getMonth() + delta);
  calCursor.value = d;
}
function openDatePop() {
  dateOpen.value = !dateOpen.value;
  rangeAnchor.value = "";
  const seed = createdAfter.value || createdBefore.value;
  calCursor.value = seed ? new Date(`${seed}T00:00`) : new Date();
}
function pickDay(iso: string) {
  markCustom();
  if (!rangeAnchor.value) {
    createdAfter.value = iso;
    createdBefore.value = "";
    rangeAnchor.value = iso;
    return;
  }
  const a = rangeAnchor.value;
  createdAfter.value = a <= iso ? a : iso;
  createdBefore.value = a <= iso ? iso : a;
  rangeAnchor.value = "";
  dateOpen.value = false;
}
function quickRange(days: number) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days);
  createdAfter.value = fmtLocal(start);
  createdBefore.value = fmtLocal(end);
  quickPick.value = days === 0 ? "today" : `d${days}`;
  dateOpen.value = false;
  rangeAnchor.value = "";
}
function markCustom() {
  quickPick.value = "custom";
}
function openCustom() {
  markCustom();
  if (!dateOpen.value) openDatePop();
  else dateOpen.value = true;
}
function clearTime() {
  createdAfter.value = "";
  createdBefore.value = "";
  quickPick.value = "";
  rangeAnchor.value = "";
  dateOpen.value = false;
}
function fmtDate(iso?: string | null) {
  if (!iso) return "";
  return iso.slice(0, 10);
}

const docCount = computed(() => new Set(hits.value.map((h) => h.document_id)).size);
const maxScore = computed(() => (hits.value.length ? Math.max(...hits.value.map((h) => h.score)) : 0));
const avgScore = computed(() =>
  hits.value.length ? hits.value.reduce((s, h) => s + h.score, 0) / hits.value.length : 0,
);

const sortBy = ref("score-desc");
const viewMode = ref<"list" | "grid">("list");
const sortedHits = computed(() => {
  const rows = [...hits.value];
  if (sortBy.value === "score-asc") rows.sort((a, b) => a.score - b.score);
  else if (sortBy.value === "date-desc")
    rows.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  else rows.sort((a, b) => b.score - a.score);
  return rows;
});

async function run() {
  error.value = "";
  ran.value = true;
  searching.value = true;
  const t0 = performance.now();
  try {
    hits.value = await searchChunks({
      query: query.value,
      knowledge_base_id: kbId.value || undefined,
      tag_id: tagId.value || undefined,
      kind: kind.value || undefined,
      k: topK.value,
      created_after: toIso(createdAfter.value),
      created_before: toIso(createdBefore.value, true),
    });
    pushHistory(hits.value.length);
  } catch (e) {
    error.value = String(e);
  } finally {
    elapsedMs.value = Math.round(performance.now() - t0);
    searching.value = false;
  }
}
function reset() {
  query.value = "";
  tagId.value = "";
  kind.value = "";
  kbId.value = "";
  clearTime();
  hits.value = [];
  error.value = "";
  ran.value = false;
}

function exportResults() {
  if (!hits.value.length) return;
  const blob = new Blob([JSON.stringify(hits.value, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `search-results-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

const cfgOpen = ref(false);
const cfgWrap = ref<HTMLElement | null>(null);
function onDocClick(e: MouseEvent) {
  if (cfgWrap.value && !cfgWrap.value.contains(e.target as Node)) cfgOpen.value = false;
  if (dateWrap.value && !dateWrap.value.contains(e.target as Node)) {
    dateOpen.value = false;
    rangeAnchor.value = "";
  }
}
onMounted(() => document.addEventListener("click", onDocClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));
const kOptions = [5, 10, 20];

function kindLabel(k: string) {
  return k === "url" ? "网页" : k === "note" ? "笔记" : k.toUpperCase();
}
const kindColors: Record<string, string> = {
  pdf: "#e11d48",
  docx: "#2563eb",
  md: "#0d9488",
  txt: "#64748b",
  url: "#7c3aed",
  note: "#d97706",
};

function hashFor(hit: SearchHit) {
  if (hit.page != null) return `#page-${hit.page}`;
  if (hit.heading) return `#${hit.heading}`;
  return "";
}
function pct(score: number) {
  return score.toFixed(2);
}
</script>

<template>
  <main class="page search-page">
    <div class="search-main">
      <div class="page-head">
        <div>
          <h1>搜索知识库</h1>
          <p class="sub">在知识库中快速检索相关内容，支持多维度精准过滤与结果分析</p>
        </div>
        <div class="head-actions">
          <button class="btn" type="button" @click="saveSearch" :disabled="!query.trim()">
            <Icon name="doc" /> 保存搜索
          </button>
          <button class="btn" type="button" @click="exportResults" :disabled="!hits.length">
            <Icon name="doc" /> 导出结果
          </button>
          <div ref="cfgWrap" class="cfg-wrap">
            <button class="btn" type="button" @click="cfgOpen = !cfgOpen">
              <Icon name="gear" /> 搜索配置
            </button>
            <div v-if="cfgOpen" class="cfg-menu card">
              <span class="cfg-label">返回条数（Top K）</span>
              <div class="cfg-opts">
                <button
                  v-for="k in kOptions"
                  :key="k"
                  type="button"
                  class="pill"
                  :class="{ on: topK === k }"
                  @click="topK = k"
                >
                  {{ k }}
                </button>
              </div>
              <span class="cfg-note">每次搜索返回的相似片段数量上限</span>
            </div>
          </div>
        </div>
      </div>
      <section class="card search-card">
        <p v-if="error" class="err">{{ error }}</p>

        <div class="bar">
          <div class="bar-field">
            <Icon name="search" />
            <input v-model="query" placeholder="输入关键词，例如：工作记忆模型" @keyup.enter="run" />
          </div>
          <button class="btn btn-primary" type="button" :disabled="searching" @click="run">
            {{ searching ? "搜索中…" : "搜索" }}
          </button>
          <button class="btn" type="button" @click="reset">重置</button>
        </div>

        <div class="row">
          <span>标签</span>
          <button class="pill" :class="{ on: !tagId }" type="button" @click="tagId = ''">全部</button>
          <button
            v-for="t in visibleTags"
            :key="t.id"
            class="pill"
            :class="{ on: tagId === t.id }"
            type="button"
            @click="tagId = t.id"
          >
            {{ t.name }}
          </button>
          <template v-if="tags.length > tagLimit">
            <em class="row-divider"></em>
            <button
              v-for="t in overflowTags"
              :key="t.id"
              v-show="tagsOpen"
              class="pill"
              :class="{ on: tagId === t.id }"
              type="button"
              @click="tagId = t.id"
            >
              {{ t.name }}
            </button>
            <button class="pill more-pill" type="button" @click="tagsOpen = !tagsOpen">
              {{ tagsOpen ? "收起" : "更多" }}
              <i class="chev" :class="{ open: tagsOpen }"></i>
            </button>
          </template>
        </div>

        <div class="row">
          <span>类型</span>
          <button class="pill" :class="{ on: !kind }" type="button" @click="kind = ''">全部</button>
          <button
            v-for="k in kinds"
            :key="k"
            class="pill kind-pill"
            :class="{ on: kind === k }"
            type="button"
            @click="kind = k"
          >
            <i class="kind-dot" :style="{ background: kindColors[k] }"></i>
            {{ kindLabel(k) }}
          </button>
        </div>

        <div class="row">
          <span>时间</span>
          <div ref="dateWrap" class="date-range">
            <div class="date-range-btn" role="button" tabindex="0" aria-label="选择日期范围" @click="openDatePop" @keydown.enter.prevent="openDatePop">
              <span class="seg" :class="{ ph: !createdAfter }">{{ createdAfter || "开始日期" }}</span>
              <em>-</em>
              <span class="seg" :class="{ ph: !createdBefore }">{{ createdBefore || "结束日期" }}</span>
              <button
                v-if="createdAfter || createdBefore"
                class="date-clear"
                type="button"
                aria-label="清除日期"
                @click.stop="clearTime"
              >
                ×
              </button>
              <svg class="cal-ico" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
                <path d="M8 3.5v3M16 3.5v3M3.5 9.5h17" />
              </svg>
            </div>
            <div v-if="dateOpen" class="date-pop" role="dialog" aria-label="日期范围">
              <div class="cal-nav">
                <button type="button" @click="shiftMonth(-1)">‹</button>
                <strong>{{ calTitle }}</strong>
                <button type="button" @click="shiftMonth(1)">›</button>
              </div>
              <div class="cal-grid">
                <span v-for="w in weekLabels" :key="w" class="cal-w">{{ w }}</span>
                <button
                  v-for="(cell, i) in calCells"
                  :key="i"
                  type="button"
                  class="cal-d"
                  :class="{
                    empty: !cell,
                    on: cell && inRange(cell),
                    start: cell && cell === createdAfter,
                    end: cell && cell === createdBefore,
                  }"
                  :disabled="!cell"
                  @click="cell && pickDay(cell)"
                >
                  {{ cell ? Number(cell.slice(8)) : "" }}
                </button>
              </div>
              <p class="cal-hint">{{ rangeAnchor ? "再点结束日期" : "先选开始日期" }}</p>
            </div>
          </div>
          <button class="pill" :class="{ on: quickPick === 'today' }" type="button" @click="quickRange(0)">今天</button>
          <button class="pill" :class="{ on: quickPick === 'd7' }" type="button" @click="quickRange(7)">近7天</button>
          <button class="pill" :class="{ on: quickPick === 'd30' }" type="button" @click="quickRange(30)">近30天</button>
          <button class="pill" :class="{ on: quickPick === 'custom' }" type="button" @click="openCustom">自定义</button>
        </div>

        <div class="row adv">
          <span>高级筛选</span>
          <label class="adv-field">
            知识库：
            <select v-model="kbId">
              <option value="">全部</option>
              <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </label>
          <label class="adv-field">
            类型范围：
            <select v-model="kind">
              <option value="">全部</option>
              <option v-for="k in kinds" :key="k" :value="k">{{ kindLabel(k) }}</option>
            </select>
          </label>
        </div>
      </section>

      <div class="search-body">
      <div class="search-lower">
      <div class="stats">
        <div class="card stat">
          <div class="stat-info">
            <span class="stat-label">命中文档数</span>
            <strong>{{ ran ? docCount : "—" }}</strong>
            <span class="stat-delta">文档去重</span>
          </div>
          <span class="stat-ico blue"><Icon name="doc" /></span>
        </div>
        <div class="card stat">
          <div class="stat-info">
            <span class="stat-label">命中片段数</span>
            <strong>{{ ran ? hits.length : "—" }}</strong>
            <span class="stat-delta">相似片段</span>
          </div>
          <span class="stat-ico green"><Icon name="search" /></span>
        </div>
        <div class="card stat">
          <div class="stat-info">
            <span class="stat-label">相关度最高</span>
            <strong>{{ ran ? pct(maxScore) : "—" }}</strong>
            <span class="stat-delta">余弦相似度</span>
          </div>
          <span class="stat-ico orange"><Icon name="spark" /></span>
        </div>
        <div class="card stat">
          <div class="stat-info">
            <span class="stat-label">平均相关度</span>
            <strong>{{ ran ? pct(avgScore) : "—" }}</strong>
            <span class="stat-delta">余弦相似度</span>
          </div>
          <span class="stat-ico purple"><Icon name="nodes" /></span>
        </div>
      </div>

      <section class="card results-card">
        <div class="tabs">
          <button
            v-for="t in tabs"
            :key="t.key"
            type="button"
            class="tab"
            :class="{ on: activeTab === t.key }"
            @click="activeTab = t.key"
          >
            {{ t.label }}
          </button>
        </div>

        <template v-if="activeTab === 'result'">
          <div class="result-bar">
            <p v-if="ran" class="meta">
              共找到 {{ hits.length }} 个相关片段（用时 {{ elapsedMs }}ms）
            </p>
            <p v-else class="meta">输入关键词开始搜索，结果只来自已开启的知识库</p>
            <div class="result-tools">
              <select v-model="sortBy" class="sort-select" aria-label="结果排序">
                <option value="score-desc">相关度 高→低</option>
                <option value="score-asc">相关度 低→高</option>
                <option value="date-desc">时间 最新优先</option>
              </select>
              <div class="view-toggle">
                <button
                  type="button"
                  class="view-btn"
                  :class="{ on: viewMode === 'list' }"
                  aria-label="列表视图"
                  @click="viewMode = 'list'"
                >
                  <Icon name="list" />
                </button>
                <button
                  type="button"
                  class="view-btn"
                  :class="{ on: viewMode === 'grid' }"
                  aria-label="网格视图"
                  @click="viewMode = 'grid'"
                >
                  <Icon name="nodes" />
                </button>
              </div>
            </div>
          </div>

          <div class="hit-wrap" :class="{ grid: viewMode === 'grid' }">
            <article v-for="hit in sortedHits" :key="hit.chunk_id" class="hit">
              <div class="hit-head">
                <span class="kind-badge" :style="{ background: kindColors[hit.kind || ''] || '#64748b' }">
                  {{ kindLabel(hit.kind || "txt") }}
                </span>
                <RouterLink class="hit-title" :to="{ path: `/documents/${hit.document_id}`, hash: hashFor(hit) }">
                  {{ hit.document_name }}
                </RouterLink>
                <span v-for="t in hit.tags || []" :key="t" class="hit-tag">{{ t }}</span>
                <span v-if="hit.knowledge_base_name" class="hit-kb">知识库：{{ hit.knowledge_base_name }}</span>
              </div>
              <p class="hit-body">{{ hit.content.slice(0, 220) }}{{ hit.content.length > 220 ? "…" : "" }}</p>
              <div class="hit-foot">
                <span>
                  <template v-if="hit.page != null">第 {{ hit.page }} 页 · </template>片段 #{{ hit.chunk_id.slice(0, 6) }}
                  · 相关度 {{ pct(hit.score) }}
                </span>
                <span class="hit-date">{{ fmtDate(hit.created_at) }}</span>
              </div>
              <RouterLink class="read" :to="{ path: `/documents/${hit.document_id}`, hash: hashFor(hit) }">
                阅读原文 →
              </RouterLink>
            </article>
          </div>
          <p v-if="ran && !hits.length && !error" class="meta empty">没有匹配的片段，试试更换关键词或放宽筛选条件</p>
        </template>

        <div v-else class="placeholder">
          <Icon name="info" />
          <p>{{ tabs.find((t) => t.key === activeTab)?.label }}为原型占位，暂未开放</p>
        </div>
      </section>
      </div>

    <aside class="search-side">
      <section v-if="savedSearches.length" class="card side-card saved-card">
        <header class="side-head">
          <h2><span class="side-ico flame flame-blue"></span> 已保存搜索</h2>
        </header>
        <ul class="history">
          <li v-for="s in savedSearches" :key="s.query + s.at">
            <button type="button" class="history-item" @click="applySaved(s)">
              <span class="history-q">{{ s.query }}</span>
              <span class="history-meta">已保存条件 · {{ timeAgo(s.at) }}</span>
            </button>
            <button type="button" class="saved-del" aria-label="删除" @click="removeSaved(s)">×</button>
          </li>
        </ul>
      </section>

      <section class="card side-card">
        <header class="side-head">
          <h2><span class="side-ico flame flame-blue"></span> 搜索历史</h2>
          <button class="side-btn" type="button" @click="clearHistory">清空</button>
        </header>
        <ul v-if="history.length" class="history">
          <li v-for="h in history" :key="h.query + h.at">
            <button type="button" class="history-item" @click="query = h.query; run()">
              <span class="history-q">{{ h.query }}</span>
              <span class="history-meta">{{ h.count }} 个结果 · {{ timeAgo(h.at) }}</span>
            </button>
          </li>
        </ul>
        <p v-else class="side-empty">暂无搜索历史</p>
      </section>

      <section class="card side-card">
        <header class="side-head">
          <h2><span class="side-ico flame flame-hot"></span> 热门搜索</h2>
        </header>
        <ol v-if="hotSearches.length" class="hot">
          <li v-for="h in hotSearches" :key="h.query">
            <button type="button" class="hot-item" @click="query = h.query; run()">
              <em :class="{ top: h.rank <= 3 }">{{ h.rank }}</em>
              <span class="hot-q">{{ h.query }}</span>
              <span class="hot-count">{{ h.count }} 次</span>
            </button>
          </li>
        </ol>
        <p v-else class="side-empty">搜索后生成热门榜</p>
      </section>
    </aside>
      </div>
    </div>
  </main>
</template>

<style scoped>
.search-page {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 1.1rem 1.25rem;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.search-main {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  flex: 1;
  min-height: 0;
}
.search-card {
  width: 100%;
  padding: 1rem 1.3rem;
  box-sizing: border-box;
  flex-shrink: 0;
}
.search-body {
  display: flex;
  gap: 1rem;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}
.search-lower {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.search-page .page-head {
  margin-bottom: 0;
  flex-shrink: 0;
}
.head-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
  align-items: flex-start;
}
.cfg-wrap {
  position: relative;
}
.cfg-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 0.4rem);
  z-index: 30;
  width: 13rem;
  padding: 0.8rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.cfg-label {
  font-size: 0.78rem;
  color: var(--text);
  font-weight: 600;
}
.cfg-opts {
  display: flex;
  gap: 0.35rem;
}
.cfg-note {
  font-size: 0.68rem;
  color: var(--muted);
}
.bar {
  display: flex;
  gap: 0.35rem;
  flex-wrap: nowrap;
  align-items: center;
  margin: 1.1rem 0 1rem;
}
.bar-field {
  flex: 1;
  min-width: 0;
  height: 1.85rem;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0 0.55rem;
  border: 1px solid #2563eb;
  border-radius: 8px;
  background: #f8fafc;
  color: var(--muted);
}
.bar-field .ico {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.bar-field input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  padding: 0;
  background: none;
  width: 100%;
  font: inherit;
  font-size: 0.72rem;
  color: inherit;
}
.bar-field input::placeholder {
  color: #94a3b8;
}
.bar .btn {
  flex-shrink: 0;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.65rem;
}
.row > span {
  width: 3.6rem;
  color: var(--muted);
  font-size: 0.82rem;
  flex-shrink: 0;
}
.date-range {
  position: relative;
  flex: 0 0 30%;
  width: 30%;
  max-width: 30%;
}
.date-range-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.28rem 0.55rem 0.28rem 0.85rem;
  background: #fff;
  color: var(--text);
  font-size: 0.78rem;
  cursor: pointer;
}
.date-range-btn .seg {
  flex: 1;
  min-width: 0;
  text-align: left;
}
.date-range-btn .ph {
  color: var(--muted);
}
.date-range-btn em {
  flex: none;
  color: var(--muted);
  font-style: normal;
}
.date-clear {
  flex: none;
  width: 1.1rem;
  height: 1.1rem;
  border: none;
  border-radius: 50%;
  background: #e2e8f0;
  color: #64748b;
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.date-clear:hover {
  background: #cbd5e1;
  color: var(--text);
}
.date-range-btn .cal-ico {
  flex: none;
  width: 14px;
  height: 14px;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.6;
  color: var(--text);
}
.date-pop {
  position: absolute;
  z-index: 20;
  top: calc(100% + 0.35rem);
  left: 0;
  width: 16.5rem;
  padding: 0.7rem 0.75rem 0.55rem;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.cal-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.45rem;
}
.cal-nav strong {
  font-size: 0.82rem;
}
.cal-nav button {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text);
  font-size: 1rem;
  padding: 0 0.25rem;
}
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.12rem;
}
.cal-w,
.cal-d {
  text-align: center;
  font-size: 0.72rem;
  line-height: 1.7rem;
}
.cal-w {
  color: var(--muted);
}
.cal-d {
  border: none;
  background: none;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text);
}
.cal-d.empty {
  cursor: default;
}
.cal-d.on {
  background: var(--teal-soft);
  color: var(--teal);
}
.cal-d.start,
.cal-d.end {
  background: var(--teal);
  color: #fff;
}
.cal-hint {
  margin: 0.4rem 0 0;
  color: var(--muted);
  font-size: 0.68rem;
}
.kind-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 3px;
  display: inline-block;
  margin-right: 0.3rem;
}
.adv {
  border-top: 1px dashed var(--line);
  padding-top: 0.65rem;
  margin-bottom: 0;
}
.row-divider {
  width: 1px;
  height: 1.1rem;
  background: var(--line);
  margin: 0 0.35rem;
}
.more-pill .chev {
  width: 0.4rem;
  height: 0.4rem;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(45deg);
  display: inline-block;
  margin-left: 0.25rem;
  transition: transform 0.15s;
  vertical-align: 2px;
}
.more-pill .chev.open {
  transform: rotate(-135deg);
  vertical-align: -1px;
}
.adv-field {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.25rem 0.6rem;
  font-size: 0.8rem;
  color: var(--muted);
  background: #fff;
}
.adv-field select {
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 0.8rem;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.9rem;
  flex-shrink: 0;
}
.stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.9rem 1rem;
}
.stat-label {
  display: block;
  color: var(--muted);
  font-size: 0.78rem;
  margin-bottom: 0.2rem;
}
.stat strong {
  font-size: 1.45rem;
  color: var(--text);
}
.stat-delta {
  display: block;
  color: #16a34a;
  font-size: 0.7rem;
  margin-top: 0.15rem;
}
.stat-ico {
  width: 2.3rem;
  height: 2.3rem;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-ico .ico {
  width: 18px;
  height: 18px;
}
.stat-ico.blue {
  background: #eff6ff;
  color: #2563eb;
}
.stat-ico.green {
  background: #ecfdf5;
  color: #059669;
}
.stat-ico.orange {
  background: #fff7ed;
  color: #ea580c;
}
.stat-ico.purple {
  background: #f5f3ff;
  color: #7c3aed;
}

.results-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0.6rem 1.3rem 1.1rem;
}
.tabs {
  display: flex;
  gap: 1.4rem;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.tab {
  border: none;
  background: none;
  padding: 0.65rem 0.1rem;
  font-size: 0.88rem;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab.on {
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.result-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.meta {
  color: var(--muted);
  font-size: 0.82rem;
  margin: 0.3rem 0 0.8rem;
}
.result-tools {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.sort-select {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.28rem 0.5rem;
  font-size: 0.78rem;
  color: var(--text);
  background: #fff;
}
.view-toggle {
  display: flex;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.view-btn {
  border: none;
  background: #fff;
  color: var(--muted);
  padding: 0.3rem 0.5rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.view-btn + .view-btn {
  border-left: 1px solid var(--line);
}
.view-btn.on {
  background: var(--teal-soft);
  color: var(--teal);
}
.view-btn .ico {
  width: 14px;
  height: 14px;
}
.empty {
  text-align: center;
  padding: 1.5rem 0;
}
.hit-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.hit-wrap.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.7rem;
  align-content: start;
}
.hit-wrap.grid .hit {
  margin-bottom: 0;
}
.hit {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  margin-bottom: 0.7rem;
  background: #fff;
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.kind-badge {
  color: #fff;
  font-size: 0.62rem;
  font-weight: 700;
  border-radius: 5px;
  padding: 0.12rem 0.4rem;
  letter-spacing: 0.02em;
}
.hit-title {
  font-weight: 700;
  font-size: 0.92rem;
}
.hit-tag {
  font-size: 0.68rem;
  color: var(--muted);
  background: #f1f5f9;
  border-radius: 5px;
  padding: 0.1rem 0.4rem;
}
.hit-kb {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.75rem;
}
.hit-body {
  color: var(--muted);
  margin: 0.45rem 0 0.55rem;
  line-height: 1.6;
  font-size: 0.84rem;
}
.hit-foot {
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 0.75rem;
}
.hit-date {
  color: var(--muted);
}
.read {
  display: inline-block;
  margin-top: 0.35rem;
  font-size: 0.8rem;
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: var(--muted);
  padding: 2.5rem 0;
  flex: 1;
  min-height: 0;
}
.placeholder .ico {
  width: 22px;
  height: 22px;
}

.search-side {
  width: min(17rem, 26vw);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  min-height: 0;
}
.side-card {
  padding: 0.9rem 1rem;
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.saved-card {
  flex: 0 0 auto;
  max-height: 30%;
}
.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
}
.side-head h2 {
  margin: 0;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.side-ico.flame {
  width: 0.85rem;
  height: 0.85rem;
  border-radius: 50% 50% 50% 0;
  transform: rotate(-45deg);
  display: inline-block;
}
.flame-blue {
  background: #3b82f6;
}
.flame-hot {
  background: #f97316;
}
.side-btn {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 0.75rem;
  cursor: pointer;
}
.side-btn:hover {
  color: var(--teal);
}
.history,
.hot {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.history li {
  display: flex;
  align-items: center;
}
.history-item {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  text-align: left;
  padding: 0.45rem 0.45rem;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}
.history-item:hover,
.hot-item:hover {
  background: #f1f5f9;
}
.saved-del {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.2rem 0.45rem;
  flex-shrink: 0;
}
.saved-del:hover {
  color: var(--danger);
}
.history-q {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-meta {
  color: var(--muted);
  font-size: 0.7rem;
}
.hot-item em {
  font-style: normal;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 4px;
  background: #f1f5f9;
  color: var(--muted);
  font-size: 0.68rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.hot-item em.top {
  background: #fff1f2;
  color: #e11d48;
  font-weight: 700;
}
.hot-count {
  color: var(--muted);
  font-size: 0.68rem;
  flex-shrink: 0;
}
.side-empty {
  color: var(--muted);
  font-size: 0.78rem;
  margin: 0.3rem 0 0;
}
.hot-item {
  width: 100%;
  border: none;
  background: none;
  text-align: left;
  padding: 0.35rem 0.4rem;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.hot-q {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--text);
}

@media (max-width: 1100px) {
  .search-side {
    display: none;
  }
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 640px) {
  .stats {
    grid-template-columns: 1fr;
  }
  .hit-wrap.grid {
    grid-template-columns: 1fr;
  }
}
</style>
