<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import Icon from "../components/Icon.vue";
import {
  favoriteDocument,
  getNewsHot,
  listConversations,
  listDocuments,
  listKnowledgeBases,
  listRecommendations,
  unfavoriteDocument,
  type Conversation,
  type DocumentItem,
  type KnowledgeBase,
  type NewsHotItem,
  type RecommendationItem,
} from "../api";

const router = useRouter();
const q = ref("");
const loading = ref(true);

const kbs = ref<KnowledgeBase[]>([]);
const docs = ref<DocumentItem[]>([]);
const recommendations = ref<RecommendationItem[]>([]);
const conversations = ref<Conversation[]>([]);

const enabledKbCount = computed(() => kbs.value.filter((k) => k.is_enabled).length);
const docCount = computed(() => docs.value.length);
const todayNewCount = computed(() => {
  const today = new Date();
  return docs.value.filter((d) => {
    if (!d.created_at) return false;
    const t = new Date(d.created_at);
    return (
      t.getFullYear() === today.getFullYear() &&
      t.getMonth() === today.getMonth() &&
      t.getDate() === today.getDate()
    );
  }).length;
});

const kbName = computed(() => {
  const map = new Map<string, string>();
  kbs.value.forEach((k) => map.set(k.id, k.name));
  return map;
});

const recentDocs = computed(() =>
  [...docs.value]
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .slice(0, 5),
);

const recentConversations = computed(() =>
  [...conversations.value]
    .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
    .slice(0, 5),
);

// ---- 每日资讯 ----
const NEWS_TABS = [
  { key: "all", label: "全部" },
  { key: "technology", label: "科技" },
  { key: "ai", label: "AI" },
  { key: "finance", label: "金融" },
] as const;
const NEWS_HOME_LIMIT = 8;

const newsTab = ref<(typeof NEWS_TABS)[number]["key"]>("all");
const newsLoading = ref(false);
const newsError = ref("");
const newsItems = ref<NewsHotItem[]>([]);

async function loadNews() {
  newsLoading.value = true;
  newsError.value = "";
  try {
    const category = newsTab.value === "all" ? undefined : newsTab.value;
    const hot = await getNewsHot(category ? { category } : undefined);
    newsItems.value = hot.items.slice(0, NEWS_HOME_LIMIT);
  } catch (e) {
    newsError.value = e instanceof Error ? e.message : "资讯加载失败";
    newsItems.value = [];
  } finally {
    newsLoading.value = false;
  }
}

function switchNewsTab(key: (typeof NEWS_TABS)[number]["key"]) {
  if (newsTab.value === key) return;
  newsTab.value = key;
  loadNews();
}

function newsRelativeTime(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const mins = Math.floor((Date.now() - t) / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  if (mins < 60 * 24) return `${Math.floor(mins / 60)}小时前`;
  return `${Math.floor(mins / (60 * 24))}天前`;
}

// ---- 时间展示 ----
function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  const hm = `${pad(t.getHours())}:${pad(t.getMinutes())}`;
  const now = new Date();
  const dayMs = 24 * 60 * 60 * 1000;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOf(now) - startOf(t)) / dayMs);
  if (diffDays === 0) return `今天 ${hm}`;
  if (diffDays === 1) return `昨天 ${hm}`;
  return `${pad(t.getMonth() + 1)}-${pad(t.getDate())} ${hm}`;
}

// ---- 快捷操作 ----
type QuickAction = { icon: string; label: string; go?: string; run?: () => void };
const quickActions: QuickAction[] = [
  { icon: "doc", label: "总结最近新增知识", run: () => goChat("总结最近新增知识的核心要点") },
  { icon: "compare", label: "比较两篇文档", go: "/documents" },
  { icon: "search", label: "查找相关资料", go: "/search" },
];

function goChat(preset?: string) {
  const query: Record<string, string> = {};
  const text = preset ?? q.value;
  if (text) query.q = text;
  router.push({ path: "/chat", query });
}

function onQuickAction(action: (typeof quickActions)[number]) {
  if (action.go) router.push(action.go);
  else action.run?.();
}

// ---- 收藏 ----
async function toggleFavorite(doc: DocumentItem) {
  const next = !doc.is_favorite;
  doc.is_favorite = next;
  try {
    if (next) await favoriteDocument(doc.id);
    else await unfavoriteDocument(doc.id);
  } catch {
    doc.is_favorite = !next;
  }
}

onMounted(async () => {
  loadNews();
  try {
    const [kbRows, docRows, recos, convs] = await Promise.all([
      listKnowledgeBases(),
      listDocuments(),
      listRecommendations(),
      listConversations(),
    ]);
    kbs.value = kbRows;
    docs.value = docRows;
    recommendations.value = recos;
    conversations.value = convs;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="page home-page">
    <!-- AI 知识问答 + 每日资讯 -->
    <section class="hero-row">
      <div class="card hero">
        <h1>今天，想从知识库里发现什么？</h1>
        <p class="sub">基于已开启的知识库进行检索与问答，回答带来源引用；也可先去搜索只看相似片段。</p>
        <div class="ask">
          <input
            v-model="q"
            placeholder="例如：梳理文档的核心结论…"
            @keyup.enter="goChat()"
          />
          <button class="btn btn-primary" type="button" @click="goChat()">提问 →</button>
        </div>
        <div class="quick-actions">
          <button
            v-for="action in quickActions"
            :key="action.label"
            class="quick-btn"
            type="button"
            @click="onQuickAction(action)"
          >
            <Icon :name="action.icon" class="q-ico" />
            <span>{{ action.label }}</span>
          </button>
        </div>
        <RouterLink to="/knowledge-bases" class="kb-status">
          <span class="dot" />已开启 {{ enabledKbCount }} 个知识库
          <Icon name="chevron" class="chev" />
        </RouterLink>
      </div>

      <div class="card news">
        <header class="news-head">
          <h2>每日资讯</h2>
          <div class="news-tabs" role="tablist">
            <button
              v-for="tab in NEWS_TABS"
              :key="tab.key"
              type="button"
              class="news-tab"
              :class="{ on: newsTab === tab.key }"
              role="tab"
              :aria-selected="newsTab === tab.key"
              @click="switchNewsTab(tab.key)"
            >
              {{ tab.label }}
            </button>
          </div>
        </header>
        <p v-if="newsError" class="hint">{{ newsError }}，可稍后重试。</p>
        <p v-else-if="newsLoading && !newsItems.length" class="hint">资讯加载中…</p>
        <p v-else-if="!newsItems.length" class="hint">今日暂无资讯，去资讯中心看看吧。</p>
        <ol v-else class="news-rank">
          <li v-for="item in newsItems" :key="item.id">
            <RouterLink class="news-row" :to="`/tools/news/${item.id}`">
              <span class="news-n">{{ item.rank }}</span>
              <span class="news-name">{{ item.title }}</span>
              <span class="news-time">{{ newsRelativeTime(item.published_at) }}</span>
            </RouterLink>
          </li>
        </ol>
        <RouterLink to="/tools/news" class="news-more">查看全部 →</RouterLink>
      </div>
    </section>

    <!-- 知识概览 -->
    <section class="grid-3 stats">
      <RouterLink to="/knowledge-bases" class="card stat">
        <span class="stat-ico ico-blue"><Icon name="db" /></span>
        <span class="stat-body">
          <strong>{{ enabledKbCount }}<em v-if="kbs.length !== enabledKbCount"> / {{ kbs.length }}</em></strong>
          <span class="stat-label">知识库</span>
          <span class="stat-desc">已启用 {{ enabledKbCount }} 个知识库</span>
        </span>
        <Icon name="chevron" class="chev" />
      </RouterLink>
      <RouterLink to="/documents" class="card stat">
        <span class="stat-ico ico-blue"><Icon name="doc" /></span>
        <span class="stat-body">
          <strong>{{ docCount }}</strong>
          <span class="stat-label">文档</span>
          <span class="stat-desc">知识库中共 {{ docCount }} 篇文档</span>
        </span>
        <Icon name="chevron" class="chev" />
      </RouterLink>
      <RouterLink to="/documents" class="card stat">
        <span class="stat-ico ico-green"><Icon name="report" /></span>
        <span class="stat-body">
          <strong>{{ todayNewCount }}</strong>
          <span class="stat-label">今日新增</span>
          <span class="stat-desc">新增文档 {{ todayNewCount }} 篇，知识持续更新</span>
        </span>
        <Icon name="chevron" class="chev" />
      </RouterLink>
    </section>

    <!-- 最近文档 + 继续探索 -->
    <section class="mid-row">
      <div class="card list-card">
        <header>
          <h2>最近文档</h2>
          <RouterLink to="/documents">查看全部 →</RouterLink>
        </header>
        <RouterLink v-for="d in recentDocs" :key="d.id" class="doc-row" :to="`/documents/${d.id}`">
          <span class="name">{{ d.filename }}</span>
          <span class="kind">{{ d.kind }}</span>
          <span class="src">{{ kbName.get(d.knowledge_base_id) || "—" }}</span>
          <span class="time">{{ formatTime(d.created_at) }}</span>
          <button
            class="star"
            :class="{ on: d.is_favorite }"
            type="button"
            :title="d.is_favorite ? '取消收藏' : '收藏'"
            @click.prevent="toggleFavorite(d)"
          >
            <Icon name="star" />
          </button>
        </RouterLink>
        <p v-if="!recentDocs.length && !loading" class="empty">还没有文档，去知识库上传或导入一篇吧。</p>
      </div>

      <div class="card list-card">
        <header>
          <h2>继续探索</h2>
        </header>
        <RouterLink
          v-for="r in recommendations.slice(0, 4)"
          :key="r.document_id"
          class="explore-row"
          :to="`/documents/${r.document_id}`"
        >
          <span class="explore-ico"><Icon name="doc" /></span>
          <span class="explore-body">
            <span class="name">{{ r.document_name }}</span>
            <span class="mini">基于知识库内容为你推荐</span>
          </span>
          <span class="reco-badge">建议阅读</span>
        </RouterLink>
        <p v-if="!recommendations.length && !loading" class="empty">暂无推荐，先去提问或浏览文档吧。</p>
        <RouterLink v-if="recommendations.length" to="/documents" class="news-more">查看全部推荐 →</RouterLink>
      </div>
    </section>

    <!-- 最近对话 -->
    <section class="card list-card conv-card">
      <header>
        <h2>最近对话</h2>
        <RouterLink to="/chat">查看全部 →</RouterLink>
      </header>
      <RouterLink
        v-for="c in recentConversations"
        :key="c.id"
        class="conv-row"
        :to="{ path: '/chat', query: { c: c.id } }"
      >
        <span class="conv-ico"><Icon name="session" /></span>
        <span class="name">{{ c.title }}</span>
        <span class="time">{{ formatTime(c.updated_at) }}</span>
        <Icon name="chevron" class="chev" />
      </RouterLink>
      <p v-if="!recentConversations.length && !loading" class="empty">暂无对话记录，去发起第一次提问吧。</p>
    </section>

    <p class="hint foot-hint">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</p>
  </main>
</template>

<style scoped>
.home-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem;
  background: transparent;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ---- 第一行：问答 + 资讯 ---- */
.hero-row {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(16rem, 1fr);
  gap: 1rem;
  align-items: stretch;
}
.hero {
  padding: 1.4rem 1.5rem 1.2rem;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.hero h1 {
  margin: 0 0 0.3rem;
  font-size: 1.2rem;
}
.hero .sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
}
.ask {
  display: flex;
  gap: 0.6rem;
  margin-top: 1rem;
  flex-wrap: wrap;
  width: 100%;
}
.ask input {
  flex: 1;
  min-width: 12rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.45rem 0.7rem;
  background: #fff;
  color: var(--text);
  font: inherit;
}
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.9rem;
}
.quick-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text);
  border-radius: 8px;
  padding: 0.35rem 0.7rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.15s;
}
.quick-btn:hover {
  background: var(--teal-soft);
}
.q-ico {
  width: 0.85rem;
  height: 0.85rem;
  color: var(--teal);
}
.kb-status {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1rem;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.75rem;
  text-decoration: none;
}
.kb-status .dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--ok);
}
.kb-status .chev {
  width: 0.7rem;
  height: 0.7rem;
}

/* ---- 每日资讯 ---- */
.news {
  min-width: 0;
  padding: 1rem 1.1rem 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  /* 高度固定为视口百分比，不随榜单条目多少变化；超出部分列表内滚动 */
  height: clamp(16rem, 36vh, 24rem);
  overflow: hidden;
}
.news-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.news-head h2 {
  margin: 0;
  font-size: 0.88rem;
}
.news-tabs {
  display: flex;
  gap: 0.25rem;
}
.news-tab {
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 0.72rem;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  cursor: pointer;
}
.news-tab.on {
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 600;
}
.news-rank {
  margin: 0;
  padding: 0;
  list-style: none;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.news-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.3rem 0.15rem;
  font-size: 0.78rem;
  line-height: 1.4;
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.news-row:hover .news-name {
  color: var(--teal);
}
.news-n {
  flex: none;
  width: 1.1rem;
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-size: 0.72rem;
  color: var(--muted);
}
.news-row:nth-child(-n + 3) .news-n {
  color: var(--teal);
  font-weight: 700;
}
.news-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.news-time {
  flex: none;
  font-size: 0.68rem;
  color: var(--muted);
}
.news-more {
  align-self: flex-end;
  font-size: 0.75rem;
  color: var(--teal);
  text-decoration: none;
  font-weight: 600;
}
.news-more:hover {
  text-decoration: underline;
}

/* ---- 知识概览 ---- */
.stats {
  margin: 0;
}
.stat {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 1rem 1.2rem;
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.stat-ico {
  flex: none;
  width: 2.3rem;
  height: 2.3rem;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.stat-ico :deep(svg) {
  width: 1.1rem;
  height: 1.1rem;
}
.ico-blue {
  background: var(--teal-soft);
  color: var(--teal);
}
.ico-green {
  background: #ecfdf5;
  color: var(--ok);
}
.stat-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.stat-body strong {
  font-size: 1.25rem;
  line-height: 1.2;
}
.stat-body strong em {
  font-style: normal;
  font-size: 0.8rem;
  color: var(--muted);
  font-weight: 400;
}
.stat-label {
  font-size: 0.75rem;
  color: var(--text);
}
.stat-desc {
  font-size: 0.68rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stat .chev {
  flex: none;
  width: 0.8rem;
  height: 0.8rem;
  color: #94a3b8;
}

/* ---- 列表卡片通用 ---- */
.list-card {
  padding: 1rem 1.1rem 0.7rem;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.list-card header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.4rem;
}
.list-card h2 {
  margin: 0;
  font-size: 0.88rem;
}
.list-card header a {
  font-size: 0.75rem;
  color: var(--teal);
  text-decoration: none;
  font-weight: 600;
}
.list-card header a:hover {
  text-decoration: underline;
}

/* ---- 最近文档 ---- */
.mid-row {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(16rem, 1fr);
  gap: 1rem;
  align-items: stretch;
}
.doc-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.15rem;
  border-top: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
  font-size: 0.8rem;
  min-width: 0;
}
.doc-row:first-of-type {
  border-top: none;
}
.doc-row:hover .name {
  color: var(--teal);
}
.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-row .kind {
  flex: none;
  font-size: 0.68rem;
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 6px;
  padding: 0.08rem 0.4rem;
}
.doc-row .src {
  flex: none;
  width: 7rem;
  font-size: 0.72rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-row .time {
  flex: none;
  width: 6rem;
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.star {
  flex: none;
  border: none;
  background: transparent;
  padding: 0.1rem;
  cursor: pointer;
  color: #cbd5e1;
  display: inline-flex;
}
.star.on {
  color: #f59e0b;
}
.star :deep(svg) {
  width: 0.9rem;
  height: 0.9rem;
}

/* ---- 继续探索 ---- */
.explore-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.15rem;
  border-top: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.explore-row:first-of-type {
  border-top: none;
}
.explore-row:hover .name {
  color: var(--teal);
}
.explore-ico {
  flex: none;
  width: 1.7rem;
  height: 1.7rem;
  border-radius: 8px;
  background: var(--teal-soft);
  color: var(--teal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.explore-ico :deep(svg) {
  width: 0.85rem;
  height: 0.85rem;
}
.explore-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.explore-body .name {
  flex: none;
  font-size: 0.78rem;
}
.mini {
  font-size: 0.68rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reco-badge {
  flex: none;
  font-size: 0.65rem;
  color: var(--teal);
  background: var(--teal-soft);
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
}

/* ---- 最近对话 ---- */
.conv-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.65rem 0.15rem;
  border-top: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
  font-size: 0.8rem;
  min-width: 0;
}
.conv-row:first-of-type {
  border-top: none;
}
.conv-row:hover .name {
  color: var(--teal);
}
.conv-ico {
  flex: none;
  width: 1.7rem;
  height: 1.7rem;
  border-radius: 8px;
  background: var(--teal-soft);
  color: var(--teal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.conv-ico :deep(svg) {
  width: 0.85rem;
  height: 0.85rem;
}
.conv-row .time {
  flex: none;
  color: var(--muted);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}
.conv-row .chev {
  flex: none;
  width: 0.8rem;
  height: 0.8rem;
  color: #94a3b8;
}

.empty {
  color: var(--muted);
  font-size: 0.75rem;
  padding: 0.5rem 0.15rem;
}
.hint {
  color: var(--muted);
  font-size: 0.75rem;
}
.foot-hint {
  margin: 0;
}

@media (max-width: 900px) {
  .hero-row,
  .mid-row {
    grid-template-columns: 1fr;
  }
  .doc-row .src,
  .doc-row .time {
    width: auto;
  }
}
</style>
