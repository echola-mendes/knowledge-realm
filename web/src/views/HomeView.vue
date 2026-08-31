<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  listDocuments,
  listKnowledgeBases,
  listRecommendations,
  listTags,
  type DocumentItem,
  type RecommendationItem,
  type TagItem,
} from "../api";

const router = useRouter();
const q = ref("");
const kbCount = ref(0);
const docCount = ref(0);
const tagCount = ref(0);
const recentDocs = ref<DocumentItem[]>([]);
const tags = ref<TagItem[]>([]);
const recommendations = ref<RecommendationItem[]>([]);

const newsItems = [
  "央行公开市场净投放超千亿，短端资金面边际转松",
  "美联储官员释放鸽派信号，美元指数盘中回落",
  "A股三大指数集体收涨，成交额重回万亿上方",
  "十年期国债收益率下行，债市情绪继续回暖",
  "人民币中间价上调，离岸汇率波动收窄",
  "新能源车板块分化，电池材料午后走强",
  "银行理财规模回升，固收+产品申购回暖",
  "黄金站上关键整数关口，避险需求阶段性升温",
  "原油库存超预期下降，油价短线冲高回落",
  "港股科技股反弹，南向资金净流入扩大",
  "房地产政策再优化，一线城市成交环比改善",
  "险资加大红利股配置，高股息策略持续受关注",
  "公募发行回暖，债券基金仍占新发主力",
  "北向资金连续净买入，外资偏好金融与消费",
  "创业板注册制项目审核提速，投行承销节奏加快",
  "地方债发行窗口开启，供给压力需观察配置力量",
  "美债收益率曲线走平，全球风险资产情绪谨慎乐观",
  "铜铝价格震荡偏强，工业金属交易量上升",
  "消费贷利率继续下行，银行零售信贷竞争加剧",
  "保险预定利率下调预期升温，储蓄型产品销售分化",
  "科创债扩容，高新企业融资渠道进一步打开",
  "跨境理财通业务量增长，南向配置需求旺盛",
  "私募备案数量回升，量化策略业绩分化明显",
  "ETF份额持续增加，宽基与红利主题同步扩容",
  "央行召开金融机构座谈会，强调保持流动性合理充裕",
  "上市公司回购增持计划增多，市场信心边际修复",
  "碳市场成交活跃，绿色金融相关债券发行加快",
  "数字人民币试点场景扩围，对公结算应用增多",
  "美股三大指数收盘互有涨跌，科技巨头业绩指引成焦点",
  "市场预计本周将有重要宏观数据公布，波动或有所加大",
];

function tagName(id: string) {
  return tags.value.find((t) => t.id === id)?.name;
}

onMounted(async () => {
  const [kbs, tagRows, recos] = await Promise.all([listKnowledgeBases(), listTags(), listRecommendations()]);
  kbCount.value = kbs.filter((k) => k.is_enabled).length;
  tags.value = tagRows;
  tagCount.value = tagRows.length;
  recommendations.value = recos;
  const docs = await listDocuments();
  docCount.value = docs.length;
  recentDocs.value = docs.slice(0, 4);
});

function goChat() {
  router.push({ path: "/chat", query: q.value ? { q: q.value } : {} });
}
</script>

<template>
  <main class="page">
    <section class="hero-row">
      <div class="card hero">
        <span class="badge">已开启知识库</span>
        <h1>今天，想从知识库里发现什么？</h1>
        <p class="sub">向已开启的知识库提问，回答会带来源引用；也可先去搜索只看相似片段。</p>
        <div class="ask">
          <input
            v-model="q"
            placeholder="例如：梳理文档的核心结论…"
            @keyup.enter="goChat"
          />
          <button class="btn btn-primary" type="button" @click="goChat">提问 →</button>
        </div>
        <p class="hint">Enter 提问，支持多轮追问，引用可点击回到原文</p>
      </div>
      <div class="card news">
        <p class="news-title">每日资讯</p>
        <ol class="news-rank">
          <li v-for="(title, i) in newsItems" :key="i">
            <span class="news-n">{{ i + 1 }}</span>
            <span class="news-name">{{ title }}</span>
          </li>
        </ol>
      </div>
    </section>

    <section class="grid-3 stats">
      <div class="card stat">
        <strong>{{ kbCount }}</strong>
        <span>知识库</span>
      </div>
      <div class="card stat">
        <strong>{{ docCount }}</strong>
        <span>文档</span>
      </div>
      <div class="card stat">
        <strong>{{ tagCount }}</strong>
        <span>标签</span>
      </div>
    </section>

    <section v-if="recommendations.length" class="lists">
      <div class="card list-card">
        <header>
          <h2>推荐阅读</h2>
        </header>
        <RouterLink
          v-for="r in recommendations"
          :key="r.document_id"
          class="row"
          :to="`/documents/${r.document_id}`"
        >
          <span class="name">{{ r.document_name }}</span>
          <span class="kind">{{ r.kind }}</span>
        </RouterLink>
      </div>
    </section>

    <section class="lists">
      <div class="card list-card">
        <header>
          <h2>最近文档</h2>
          <RouterLink to="/documents">查看全部 →</RouterLink>
        </header>
        <RouterLink v-for="d in recentDocs" :key="d.id" class="row" :to="`/documents/${d.id}`">
          <span class="name">{{ d.filename }}</span>
          <span v-if="d.tag_ids?.[0]" class="mini">{{ tagName(d.tag_ids[0]) }}</span>
          <span class="kind">{{ d.kind }}</span>
        </RouterLink>
        <p v-if="!recentDocs.length" class="empty">暂无文档</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.hero-row {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(14rem, 0.55fr);
  gap: 1rem;
  align-items: stretch;
}
.hero {
  padding: 1.6rem 1.5rem 1.2rem;
  min-width: 0;
}
.news {
  min-width: 0;
  padding: 1rem 0.9rem 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 16.5rem;
}
.news-title {
  margin: 0 0.15rem;
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--teal);
  line-height: 1.4;
}
.news-rank {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: auto;
  min-height: 0;
  flex: 1;
}
.news-rank li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
  padding: 0.22rem 0.15rem;
  font-size: 0.8rem;
  line-height: 1.35;
}
.news-n {
  flex: none;
  width: 1.2rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  font-size: 0.72rem;
}
.news-rank li:nth-child(-n + 3) .news-n {
  color: var(--teal);
  font-weight: 700;
}
.news-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 800px) {
  .hero-row {
    grid-template-columns: 1fr;
  }
}
.badge {
  display: inline-block;
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.8rem;
}
.hero h1 {
  margin: 0.7rem 0 0.4rem;
  font-size: 1.15rem;
}
.ask {
  display: flex;
  gap: 0.6rem;
  margin-top: 1rem;
  flex-wrap: wrap;
}
.ask input {
  flex: 1;
  min-width: 12rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.45rem 0.7rem;
}
.hint,
.empty {
  color: var(--muted);
  font-size: 0.75rem;
}
.stats {
  margin: 1rem 0;
}
.stat {
  padding: 1.1rem 1.2rem;
}
.stat strong {
  display: block;
  font-size: 1.35rem;
}
.stat span {
  color: var(--muted);
}
.list-card {
  padding: 1rem 1.1rem 0.5rem;
}
.list-card header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.list-card h2 {
  margin: 0;
  font-size: 0.88rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
}
.row:first-of-type {
  margin-top: 0.5rem;
}
.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini,
.kind {
  font-size: 0.75rem;
  background: #eef1f4;
  border-radius: 6px;
  padding: 0.1rem 0.4rem;
  color: var(--muted);
}
</style>
