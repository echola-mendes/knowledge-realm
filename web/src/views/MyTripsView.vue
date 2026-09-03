<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { listPlans, type PlanRecordItem } from "../api";
import Icon from "../components/Icon.vue";

const TRIP_TYPES = [
  { key: "all", label: "全部" },
  { key: "business", label: "商务出行" },
  { key: "leisure", label: "旅游度假" },
  { key: "study", label: "学习交流" },
  { key: "other", label: "其他" },
] as const;

const TYPE_LABEL: Record<string, string> = {
  business: "商务出行",
  leisure: "旅游度假",
  study: "学习交流",
  other: "其他",
};

const PAGE_SIZE = 10;
const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

const loading = ref(true);
const error = ref("");
const rows = ref<PlanRecordItem[]>([]);
const q = ref("");
const typeFilter = ref("all");
const dateFrom = ref("");
const dateTo = ref("");
const page = ref(1);

function typeLabel(key: string | undefined): string {
  return TYPE_LABEL[key || "other"] || "其他";
}

function durationText(nights: number | null | undefined): string {
  if (nights == null) return "";
  if (nights === 0) return "当天往返";
  return `${nights + 1}天${nights}晚`;
}

function formatDepart(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${iso.slice(0, 10)} ${WEEKDAYS[d.getDay()]}`;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function inDateRange(depart: string | null): boolean {
  if (!dateFrom.value && !dateTo.value) return true;
  if (!depart) return false;
  const day = depart.slice(0, 10);
  if (dateFrom.value && day < dateFrom.value) return false;
  if (dateTo.value && day > dateTo.value) return false;
  return true;
}

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase();
  return rows.value.filter((row) => {
    const typ = row.trip_type || "other";
    if (typeFilter.value !== "all" && typ !== typeFilter.value) return false;
    if (!inDateRange(row.depart_date)) return false;
    if (!needle) return true;
    const hay = [row.title, row.origin, row.destination, typeLabel(typ)].join(" ").toLowerCase();
    return hay.includes(needle);
  });
});

const typeCounts = computed(() => {
  const counts: Record<string, number> = { all: rows.value.length, business: 0, leisure: 0, study: 0, other: 0 };
  for (const row of rows.value) {
    const typ = row.trip_type || "other";
    counts[typ] = (counts[typ] || 0) + 1;
  }
  return counts;
});

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / PAGE_SIZE)));
const paged = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filtered.value.slice(start, start + PAGE_SIZE);
});

function resetFilters() {
  q.value = "";
  typeFilter.value = "all";
  dateFrom.value = "";
  dateTo.value = "";
  page.value = 1;
}

async function refresh() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listPlans();
    page.value = 1;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  refresh().catch(() => undefined);
});
</script>

<template>
  <div class="trips-page">
    <div class="top-bar">
      <nav class="crumb" aria-label="面包屑">
        <span>工具</span>
        <span class="sep">›</span>
        <span>旅程</span>
        <span class="sep">›</span>
        <span class="here">我的行程单</span>
      </nav>
      <div class="top-actions">
        <input
          v-model="q"
          type="search"
          class="search"
          placeholder="搜索行程目的地、关键词…"
          aria-label="搜索行程"
          @input="page = 1"
        />
        <RouterLink class="btn btn-primary" to="/tools/trips/new">+ 新建行程</RouterLink>
      </div>
    </div>

    <section class="hero">
      <svg class="hero-art" viewBox="0 0 420 160" aria-hidden="true">
        <path d="M40 160 110 78l40 28 70-62 55 48 50-36 55 58v46H40Z" fill="#dbeafe" />
        <path d="M80 160 150 92l36 24 48-50 62 46 40-28 44 48v26H80Z" fill="#bfdbfe" />
        <path
          d="M248 92c18-6 34-4 46 8"
          fill="none"
          stroke="#93c5fd"
          stroke-width="1.4"
          stroke-dasharray="3 4"
        />
        <g fill="none" stroke="#60a5fa" stroke-width="1.5" stroke-linejoin="round">
          <path d="M318 78 332 84l-4 14-10-4 0-14Z" />
          <path d="M332 84h12" />
        </g>
      </svg>
      <button class="guide-btn" type="button">
        <Icon name="book" />
        使用指南
      </button>
      <div class="hero-head">
        <div class="hero-map" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#mapBg)" />
            <path
              d="M12 16.2 22.6 13.4l.4 20.2L12.2 36Z"
              fill="#fff"
              stroke="#93c5fd"
              stroke-width="1.2"
              stroke-linejoin="round"
            />
            <path
              d="M22.6 13.4 36 16.6v19.2L23 33.6Z"
              fill="#eff6ff"
              stroke="#93c5fd"
              stroke-width="1.2"
              stroke-linejoin="round"
            />
            <path d="M15 21.2h5.2M15 25.6h4.2M26.2 22.4h6.4M26.2 26.6h4.8" stroke="#bfdbfe" stroke-width="1.3" />
            <path d="M29.2 34.6s7.4-4.8 7.4-9.2a7.4 7.4 0 1 0-14.8 0c0 4.4 7.4 9.2 7.4 9.2Z" fill="#2563eb" />
            <circle cx="29.2" cy="24.8" r="2.35" fill="#fff" />
            <defs>
              <linearGradient id="mapBg" x1="8" y1="4" x2="42" y2="46">
                <stop stop-color="#eff6ff" />
                <stop offset="1" stop-color="#dbeafe" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div>
          <h1>我的行程单</h1>
          <p class="sub">在 Multi Agent 对话中完成差旅规划后，方案会出现在这里。</p>
        </div>
      </div>
      <ul class="features">
        <li>
          <span class="feat-ico"><Icon name="robot" /></span>
          <div>
            <strong>AI 智能规划</strong>
            <p>快速生成个性化行程</p>
          </div>
        </li>
        <li>
          <span class="feat-ico"><Icon name="clipboard" /></span>
          <div>
            <strong>多方案对比</strong>
            <p>灵活选择最佳方案</p>
          </div>
        </li>
        <li>
          <span class="feat-ico"><Icon name="export" /></span>
          <div>
            <strong>一键导出分享</strong>
            <p>支持 PDF / 链接分享</p>
          </div>
        </li>
      </ul>
      <p class="hero-quote">“让每一次出发，都更从容”</p>
    </section>

    <p v-if="error" class="hint err">{{ error }}</p>

    <section class="card pad list-card">
      <div class="filters">
        <div class="type-tabs" role="tablist" aria-label="行程类型">
          <button
            v-for="item in TRIP_TYPES"
            :key="item.key"
            type="button"
            class="type-tab"
            :class="{ on: typeFilter === item.key }"
            @click="typeFilter = item.key; page = 1"
          >
            {{ item.label }} ({{ typeCounts[item.key] || 0 }})
          </button>
        </div>
        <div class="filter-extra">
          <input v-model="dateFrom" type="date" aria-label="开始日期" @change="page = 1" />
          <span class="muted">→</span>
          <input v-model="dateTo" type="date" aria-label="结束日期" @change="page = 1" />
          <button class="btn" type="button" @click="resetFilters">重置</button>
        </div>
      </div>

      <div v-if="loading" class="empty-desc">加载中…</div>
      <div v-else-if="!filtered.length" class="empty-card">
        <p class="empty-title">暂无行程单</p>
        <p class="empty-desc">
          打开对话，切换到 Multi Agent，描述出行需求（出发地、目的地、日期），生成方案后可在此回看。
        </p>
        <RouterLink class="btn btn-primary" to="/tools/trips/new">开始规划</RouterLink>
      </div>
      <template v-else>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>行程名称</th>
                <th>出发日期</th>
                <th>创建时间</th>
                <th>方案页</th>
                <th>对话</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in paged" :key="row.id">
                <td>
                  <div class="name-cell">
                    <span class="thumb"><Icon name="plane" /></span>
                    <div>
                      <strong>{{ row.title }}</strong>
                      <span class="meta">
                        {{ typeLabel(row.trip_type) }}
                        <template v-if="durationText(row.nights)"> {{ durationText(row.nights) }}</template>
                      </span>
                    </div>
                  </div>
                </td>
                <td>{{ formatDepart(row.depart_date) }}</td>
                <td>{{ formatTime(row.created_at) }}</td>
                <td>
                  <a v-if="row.url" class="link" :href="row.url" target="_blank" rel="noopener">打开</a>
                  <span v-else class="muted">仅会话内</span>
                </td>
                <td>
                  <RouterLink
                    v-if="row.conversation_id"
                    class="link"
                    :to="{ path: '/chat', query: { mode: 'agent', c: row.conversation_id } }"
                  >
                    查看
                  </RouterLink>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pager">
          <span>共 {{ filtered.length }} 条记录</span>
          <span>{{ PAGE_SIZE }} 条/页</span>
          <button class="btn" type="button" :disabled="page <= 1" @click="page -= 1">上一页</button>
          <span>{{ page }} / {{ pageCount }}</span>
          <button class="btn" type="button" :disabled="page >= pageCount" @click="page += 1">下一页</button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.trips-page {
  min-width: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  overflow: hidden;
}
.top-bar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.crumb {
  font-size: 0.75rem;
  color: var(--muted);
}
.crumb .sep {
  margin: 0 0.25rem;
  color: #94a3b8;
}
.crumb .here {
  color: var(--text);
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.search {
  min-width: 14rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
  background: #fff;
  color: var(--text);
  font: inherit;
}
.hero {
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "head guide"
    "feats quote";
  column-gap: 0.75rem;
  row-gap: 0.65rem;
  background: linear-gradient(105deg, #f8fbff 0%, #eff6ff 48%, #dbeafe 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 1rem 1.1rem 0.9rem;
  min-height: 8.5rem;
}
.hero-art {
  position: absolute;
  right: -0.6rem;
  bottom: -0.5rem;
  width: 11rem;
  height: 6.5rem;
  pointer-events: none;
  opacity: 0.9;
}
.guide-btn {
  grid-area: guide;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text);
  border-radius: 8px;
  padding: 0.28rem 0.55rem;
  font: inherit;
  font-size: 0.72rem;
  cursor: pointer;
  height: fit-content;
  justify-self: end;
}
.guide-btn :deep(.ico) {
  width: 0.85rem;
  height: 0.85rem;
  color: var(--teal);
}
.hero-head {
  grid-area: head;
  position: relative;
  z-index: 1;
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
}
.hero-map {
  width: 2.6rem;
  height: 2.6rem;
  flex-shrink: 0;
}
.hero-map svg {
  width: 100%;
  height: 100%;
  display: block;
}
.hero h1 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 0.25rem;
}
.sub {
  font-size: 0.75rem;
  color: var(--muted);
  margin: 0;
}
.features {
  grid-area: feats;
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.features li {
  display: flex;
  gap: 0.4rem;
  align-items: flex-start;
  min-width: 8.5rem;
  flex: 1 1 7.5rem;
}
.feat-ico {
  width: 1.45rem;
  height: 1.45rem;
  border-radius: 999px;
  background: var(--teal-soft);
  color: var(--teal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 0.05rem;
}
.feat-ico :deep(.ico) {
  width: 0.82rem;
  height: 0.82rem;
}
.features strong {
  display: block;
  font-size: 0.75rem;
  font-weight: 650;
  color: var(--text);
}
.features p {
  margin: 0.12rem 0 0;
  font-size: 0.68rem;
  color: var(--muted);
}
.hero-quote {
  grid-area: quote;
  position: relative;
  z-index: 1;
  margin: 0;
  align-self: end;
  max-width: 7.5rem;
  text-align: right;
  font-size: 0.78rem;
  color: #94a3b8;
  line-height: 1.45;
}
.list-card {
  margin: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.filters {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
  margin-bottom: 0.55rem;
}
.type-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  flex: 1;
}
.type-tab {
  border: none;
  background: #eef1f4;
  color: var(--muted);
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  cursor: pointer;
  font: inherit;
  font-size: 0.72rem;
}
.type-tab.on {
  background: var(--teal);
  color: #fff;
}
.filter-extra {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}
.filter-extra input[type="date"] {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.28rem 0.4rem;
  background: #fff;
  font: inherit;
  color: var(--text);
}
.empty-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.55rem;
  min-height: 8rem;
  justify-content: center;
}
.empty-title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.empty-desc {
  margin: 0;
  max-width: 32rem;
  font-size: 0.75rem;
  color: var(--muted);
  line-height: 1.55;
}
.hint.err {
  color: var(--danger);
  font-size: 0.75rem;
  margin: 0;
}
.muted {
  color: var(--muted);
}
.name-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.thumb {
  width: 2rem;
  height: 2rem;
  border-radius: 8px;
  background: #eff6ff;
  color: var(--teal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.thumb :deep(.ico) {
  width: 0.9rem;
  height: 0.9rem;
}
.meta {
  display: block;
  font-size: 0.72rem;
  font-weight: 400;
  color: var(--muted);
  margin-top: 0.12rem;
}
.link {
  color: var(--teal);
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
.table-wrap {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  padding: 0.55rem 0.4rem;
  border-bottom: 1px solid var(--line);
  font-size: 0.72rem;
  vertical-align: middle;
}
th {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--muted);
}
.pager {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.55rem;
  color: var(--muted);
  flex-wrap: wrap;
  flex-shrink: 0;
}
.pager .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
