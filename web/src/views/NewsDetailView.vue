<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { getNewsDetail, type NewsDetail } from "../api";

const CATEGORY_LABEL: Record<string, string> = {
  technology: "科技",
  ai: "AI",
  finance: "金融",
};

const route = useRoute();
const loading = ref(true);
const error = ref("");
const detail = ref<NewsDetail | null>(null);

const newsId = computed(() => {
  const raw = route.params.id;
  const n = typeof raw === "string" ? Number(raw) : Number(Array.isArray(raw) ? raw[0] : NaN);
  return Number.isFinite(n) ? n : null;
});

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

async function load() {
  if (newsId.value == null) {
    error.value = "无效的资讯 ID";
    detail.value = null;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    detail.value = await getNewsDetail(newsId.value);
  } catch (e) {
    detail.value = null;
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(newsId, () => {
  load().catch(() => undefined);
});

onMounted(() => {
  load().catch(() => undefined);
});
</script>

<template>
  <div class="news-detail-page">
    <nav class="crumb" aria-label="面包屑">
      <RouterLink to="/tools/news">AI资讯</RouterLink>
      <span class="sep">›</span>
      <span class="here">详情</span>
    </nav>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="error" class="hint err">{{ error }}</p>
    <article v-else-if="detail" class="card pad">
      <h1>{{ detail.title }}</h1>
      <div class="meta">
        <span>{{ detail.source }}</span>
        <span>·</span>
        <span>{{ formatTime(detail.published_at) }}</span>
        <span>·</span>
        <span>{{ CATEGORY_LABEL[detail.category] || detail.category }}</span>
        <template v-if="detail.heat_score != null">
          <span>·</span>
          <span>热度 {{ Math.round(detail.heat_score) }}</span>
        </template>
      </div>

      <section class="block">
        <h2>AI摘要</h2>
        <p v-if="detail.summary" class="text">{{ detail.summary }}</p>
        <p v-else class="hint">暂无摘要</p>
      </section>

      <section class="block">
        <h2>正文</h2>
        <p v-if="detail.content" class="text content">{{ detail.content }}</p>
        <p v-else class="hint">暂无正文（仅使用来源 feed 字段，未抓取网页）</p>
      </section>

      <a class="btn btn-primary" :href="detail.url" target="_blank" rel="noopener noreferrer">查看原文</a>
    </article>
  </div>
</template>

<style scoped>
.news-detail-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  font-size: 12.5px;
  background: transparent;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
.crumb {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0 0 0.75rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.crumb a {
  color: var(--teal);
  text-decoration: none;
}
.crumb a:hover {
  text-decoration: underline;
}
.crumb .sep {
  color: #94a3b8;
}
.crumb .here {
  color: var(--text);
  font-weight: 600;
}
.card.pad {
  padding: 0.95rem 1.05rem 1.15rem;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
h1 {
  margin: 0 0 0.45rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1.35;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin: 0 0 0.85rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.block {
  margin: 0 0 0.85rem;
}
.block h2 {
  margin: 0 0 0.35rem;
  font-size: 0.78rem;
  font-weight: 650;
  color: var(--text);
}
.text {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text);
  line-height: 1.55;
  white-space: pre-wrap;
}
.content {
  max-width: 48rem;
}
.hint {
  margin: 0.25rem 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.hint.err {
  color: var(--danger);
}
.btn.btn-primary {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}
</style>
