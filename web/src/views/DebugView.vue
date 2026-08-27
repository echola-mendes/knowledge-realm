<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  createKnowledgeBase,
  createNote,
  deleteKnowledgeBase,
  getDocument,
  getMe,
  putRetrievalLabel,
  runRetrievalDebug,
  type KnowledgeBase,
  type RetrievalDebugRow,
} from "../api";
import { knowledgeBases, loadKnowledgeBases } from "../kb";

const STORAGE_BASE = "zhiyu-debug-ui";
const userTag = ref("echola");
const STORAGE = computed(() => `${STORAGE_BASE}:${userTag.value}`);
const EVAL_OPTIONS = [5, 10, 20, 50, 100];
const GT_LABELS = ["Not Relevant", "Partial", "Relevant", "Highly Relevant"] as const;

type Cand = {
  chunkId: string;
  documentId: string;
  title: string;
  source: string;
  path: string;
  vectorRank: number | null;
  vectorScore: number | null;
  bm25Rank: number | null;
  bm25Score: number | null;
  rrfRank: number | null;
  rrfScore: number | null;
  rerankRank: number | null;
  rerankScore: number | null;
  final: boolean;
};

const TEST_PREFIX = "测试库-";
const TEST_MAX = 3;
const TEST_SEEDS = [
  { name: "测试库-退款", filename: "退款.md", content: "退款须原路返回。" },
  { name: "测试库-手册", filename: "手册.md", content: "手册规定工时休假。" },
  { name: "测试库-请假", filename: "请假.md", content: "请假须提前报备。" },
] as const;

const kbs = ref<KnowledgeBase[]>([]);
const seeding = ref(false);
const testKbs = computed(() => kbs.value.filter((kb) => kb.name.startsWith(TEST_PREFIX)));
const canSeed = computed(() => testKbs.value.length < TEST_MAX);

function seedPreview(name: string) {
  const hit = TEST_SEEDS.find((s) => s.name === name);
  const text = hit?.content || "";
  return Array.from(text).slice(0, 30).join("");
}

function nextSeed() {
  const used = new Set(testKbs.value.map((kb) => kb.name));
  return TEST_SEEDS.find((s) => !used.has(s.name));
}

async function refreshKbs() {
  await loadKnowledgeBases();
  kbs.value = knowledgeBases.value;
}

async function waitReady(id: string) {
  for (let i = 0; i < 40; i++) {
    const doc = await getDocument(id);
    if (doc.status === "ready") return;
    if (doc.status === "parse_failed" || doc.status === "index_failed") {
      throw new Error(doc.error_message || "测试文档索引失败");
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("测试文档索引超时");
}

async function createSeed(seed: (typeof TEST_SEEDS)[number]) {
  const text = Array.from(seed.content).slice(0, 30).join("");
  const kb = await createKnowledgeBase(seed.name);
  const doc = await createNote(kb.id, text, seed.filename);
  await waitReady(doc.id);
  return kb;
}

async function seedTestKb() {
  if (!canSeed.value) {
    hint.value = `测试库最多 ${TEST_MAX} 个。`;
    return;
  }
  const seed = nextSeed();
  if (!seed) {
    hint.value = `测试库最多 ${TEST_MAX} 个。`;
    return;
  }
  seeding.value = true;
  try {
    const kb = await createSeed(seed);
    await refreshKbs();
    dataset.value = kb.id;
    hint.value = `已创建 ${seed.name}（正文 ${Array.from(seed.content).length} 字）。`;
  } catch (e) {
    hint.value = String(e);
  } finally {
    seeding.value = false;
  }
}

async function ensureTestKbs() {
  await refreshKbs();
  if (testKbs.value.length >= TEST_MAX) return;
  seeding.value = true;
  try {
    while (testKbs.value.length < TEST_MAX) {
      const seed = nextSeed();
      if (!seed) break;
      hint.value = `正在准备测试库 ${testKbs.value.length + 1}/${TEST_MAX}…`;
      await createSeed(seed);
      await refreshKbs();
    }
    hint.value = `测试库已就绪（${testKbs.value.length}/${TEST_MAX}），正文均不超过 30 字。`;
  } catch (e) {
    hint.value = String(e);
  } finally {
    seeding.value = false;
  }
}

async function removeTestKb(kb: KnowledgeBase) {
  if (seeding.value) return;
  if (!confirm(`删除 ${kb.name}？`)) return;
  try {
    await deleteKnowledgeBase(kb.id);
    await refreshKbs();
    if (dataset.value === kb.id) dataset.value = "current_kb";
    hint.value = `已删除 ${kb.name}。当前 ${testKbs.value.length}/${TEST_MAX}。`;
  } catch (e) {
    hint.value = String(e);
  }
}
const dataset = ref("current_kb");
const k = ref(5);
const bm25K = ref(5);
const n = ref(5);
const m = ref(5);
const rrfKConst = ref(60);
const vectorThreshold = ref(0.3);
const rerankThreshold = ref(0);
const rerankModel = ref("");
const maxRerankCands = ref(20);
const evalKs = ref<number[]>([5, 10, 20]);
const resultTab = ref<"rerank" | "rrf" | "vector" | "bm25">("rerank");
const showDetails = ref(true);
const ran = ref(false);
const running = ref(false);
const cands = ref<Cand[]>([]);
const gtMap = ref<Record<string, number>>({});
const formulaId = ref<string | null>(null);
const hint = ref("点运行后检索当前账号已开启的知识库（pgvector + Elasticsearch），不是演示文档。");
const lat = ref({ vector: 0, bm25: 0, rrf: 0, rerank: 0, total: 0 });

function gtOf(id: string) {
  return gtMap.value[id] ?? 0;
}

function setGt(id: string, v: number) {
  gtMap.value = { ...gtMap.value, [id]: v };
  if (!query.value.trim()) return;
  putRetrievalLabel({
    query: query.value,
    knowledge_base_id: dataset.value === "current_kb" ? undefined : dataset.value,
    document_id: id,
    relevance: v,
  }).catch((e) => {
    hint.value = String(e);
  });
}

function toggleEval(v: number) {
  if (evalKs.value.includes(v)) {
    if (evalKs.value.length === 1) return;
    evalKs.value = evalKs.value.filter((x) => x !== v);
  } else evalKs.value = [...evalKs.value, v].sort((a, b) => a - b);
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, Math.round(n) || lo));
}

function rowToCand(r: RetrievalDebugRow): Cand {
  return {
    chunkId: r.chunk_id,
    documentId: r.document_id,
    title: r.document_name,
    source: "",
    path: r.chunk_id,
    vectorRank: r.vector_rank,
    vectorScore: r.vector_score,
    bm25Rank: r.bm25_rank,
    bm25Score: r.bm25_score,
    rrfRank: r.rrf_rank,
    rrfScore: r.rrf_score,
    rerankRank: r.rerank_rank,
    rerankScore: r.rerank_score,
    final: r.final,
  };
}

async function run() {
  const q = query.value.trim();
  if (!q) {
    hint.value = "先填写测试查询。";
    return;
  }
  k.value = clamp(k.value, 1, 100);
  bm25K.value = clamp(bm25K.value, 1, 100);
  n.value = clamp(n.value, 1, 100);
  m.value = clamp(m.value, 1, 100);
  maxRerankCands.value = clamp(maxRerankCands.value, 1, 200);
  running.value = true;
  hint.value = "正在检索…";
  const t0 = performance.now();
  try {
    const evalK = Math.max(...evalKs.value, 5);
    const body = await runRetrievalDebug({
      query: q,
      knowledge_base_id: dataset.value === "current_kb" ? undefined : dataset.value,
      vector_k: k.value,
      bm25_k: bm25K.value,
      rrf_k: n.value,
      rerank_k: m.value,
      vector_threshold: vectorThreshold.value,
      rrf_k_const: rrfKConst.value,
      eval_k: evalK,
    });
    const ms = Math.round(performance.now() - t0);
    cands.value = body.candidates.map(rowToCand);
    gtMap.value = { ...body.labels };
    rerankModel.value = body.rerank.model || rerankModel.value;
    lat.value = { vector: 0, bm25: 0, rrf: 0, rerank: 0, total: ms };
    ran.value = true;
    formulaId.value = null;
    hint.value = `检索完成（整次 ${ms} ms）。向量 ${body.vector.actual_count} / BM25 ${body.bm25.actual_count} / Final ${body.final.length}。`;
  } catch (e) {
    hint.value = String(e);
  } finally {
    running.value = false;
  }
}

function reset() {
  query.value = "";
  dataset.value = "current_kb";
  k.value = 5;
  bm25K.value = 5;
  n.value = 5;
  m.value = 5;
  rrfKConst.value = 60;
  vectorThreshold.value = 0.3;
  rerankThreshold.value = 0;
  evalKs.value = [5, 10, 20];
  ran.value = false;
  cands.value = [];
  gtMap.value = {};
  hint.value = "已重置。再运行会打真实检索。";
}

function save() {
  localStorage.setItem(
    STORAGE.value,
    JSON.stringify({
      query: query.value,
      dataset: dataset.value,
      k: k.value,
      bm25K: bm25K.value,
      n: n.value,
      m: m.value,
      rrfKConst: rrfKConst.value,
      vectorThreshold: vectorThreshold.value,
      rerankThreshold: rerankThreshold.value,
      rerankModel: rerankModel.value,
      maxRerankCands: maxRerankCands.value,
      evalKs: evalKs.value,
    }),
  );
  hint.value = "配置已写入本机 localStorage。";
}

function load() {
  const raw = localStorage.getItem(STORAGE.value);
  if (!raw) {
    hint.value = "没有已保存的配置。";
    return;
  }
  const c = JSON.parse(raw) as Record<string, unknown>;
  if (typeof c.query === "string") query.value = c.query;
  if (typeof c.dataset === "string") dataset.value = c.dataset;
  if (typeof c.k === "number") k.value = c.k;
  if (typeof c.bm25K === "number") bm25K.value = c.bm25K;
  if (typeof c.n === "number") n.value = c.n;
  if (typeof c.m === "number") m.value = c.m;
  if (typeof c.rrfKConst === "number") rrfKConst.value = c.rrfKConst;
  if (typeof c.vectorThreshold === "number") vectorThreshold.value = c.vectorThreshold;
  if (typeof c.rerankThreshold === "number") rerankThreshold.value = c.rerankThreshold;
  if (typeof c.rerankModel === "string") rerankModel.value = c.rerankModel;
  if (typeof c.maxRerankCands === "number") maxRerankCands.value = c.maxRerankCands;
  if (Array.isArray(c.evalKs)) evalKs.value = c.evalKs.filter((x): x is number => typeof x === "number");
  hint.value = "已加载本机配置。";
}

function exportJson() {
  const blob = new Blob([JSON.stringify({ query: query.value, cands: cands.value, gt: gtMap.value }, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "retrieval-debug.json";
  a.click();
  URL.revokeObjectURL(a.href);
}

const vectorRows = computed(() =>
  cands.value.filter((c) => c.vectorRank != null).sort((a, b) => (a.vectorRank || 0) - (b.vectorRank || 0)),
);
const bm25Rows = computed(() =>
  cands.value.filter((c) => c.bm25Rank != null).sort((a, b) => (a.bm25Rank || 0) - (b.bm25Rank || 0)),
);
const rrfRows = computed(() =>
  cands.value.filter((c) => c.rrfRank != null).sort((a, b) => (a.rrfRank || 0) - (b.rrfRank || 0)),
);
const rerankRows = computed(() =>
  cands.value.filter((c) => c.rerankRank != null).sort((a, b) => (a.rerankRank || 0) - (b.rerankRank || 0)),
);
const finalRows = computed(() => cands.value.filter((c) => c.final).sort((a, b) => (a.rerankRank || 0) - (b.rerankRank || 0)));

const tabRows = computed(() => {
  if (resultTab.value === "vector") return vectorRows.value;
  if (resultTab.value === "bm25") return bm25Rows.value;
  if (resultTab.value === "rrf") return rrfRows.value;
  return rerankRows.value;
});

const uniqueDocs = computed(() => {
  const seen = new Set<string>();
  const list: Cand[] = [];
  for (const c of [...finalRows.value, ...cands.value]) {
    if (seen.has(c.documentId)) continue;
    seen.add(c.documentId);
    list.push(c);
  }
  return list;
});

const relevantIds = computed(() => uniqueDocs.value.filter((c) => gtOf(c.documentId) >= 2).map((c) => c.documentId));

function finalDocOrder() {
  const seen = new Set<string>();
  const order: string[] = [];
  for (const c of finalRows.value) {
    if (seen.has(c.documentId)) continue;
    seen.add(c.documentId);
    order.push(c.documentId);
  }
  return order;
}

function precisionAt(at: number) {
  if (!ran.value) return "—";
  const order = finalDocOrder().slice(0, at);
  if (!order.length) return "0.00";
  const hits = order.filter((id) => relevantIds.value.includes(id)).length;
  return (hits / order.length).toFixed(2);
}

function recallAt(at: number) {
  if (!ran.value) return "—";
  const rel = relevantIds.value;
  if (!rel.length) return "—";
  const order = finalDocOrder().slice(0, at);
  const hits = order.filter((id) => rel.includes(id)).length;
  return (hits / rel.length).toFixed(2);
}

function hitAt(at: number) {
  if (!ran.value) return "—";
  const rel = relevantIds.value;
  if (!rel.length) return "—";
  const order = finalDocOrder().slice(0, at);
  return order.some((id) => rel.includes(id)) ? "1.00" : "0.00";
}

function mrrAt(at: number) {
  if (!ran.value) return "—";
  const rel = new Set(relevantIds.value);
  if (!rel.size) return "—";
  const order = finalDocOrder().slice(0, at);
  const idx = order.findIndex((id) => rel.has(id));
  if (idx < 0) return "0.00";
  return (1 / (idx + 1)).toFixed(2);
}

function ndcgAt(at: number) {
  if (!ran.value) return "—";
  const order = finalDocOrder().slice(0, at);
  let dcg = 0;
  order.forEach((id, i) => {
    const g = gtOf(id);
    if (g <= 0) return;
    dcg += (2 ** g - 1) / Math.log2(i + 2);
  });
  const ideal = [...uniqueDocs.value]
    .map((c) => gtOf(c.documentId))
    .sort((a, b) => b - a)
    .slice(0, at);
  let idcg = 0;
  ideal.forEach((g, i) => {
    if (g <= 0) return;
    idcg += (2 ** g - 1) / Math.log2(i + 2);
  });
  if (!idcg) return "—";
  return (dcg / idcg).toFixed(2);
}

function rrfParts(c: Cand) {
  const kc = rrfKConst.value;
  const v = c.vectorRank ? `1/(${kc}+${c.vectorRank})` : "0";
  const b = c.bm25Rank ? `1/(${kc}+${c.bm25Rank})` : "0";
  return `${v} + ${b} = ${(c.rrfScore ?? 0).toFixed(6)}`;
}

const formulaRow = computed(() => rrfRows.value.find((x) => x.chunkId === formulaId.value) || null);
const gtHits = computed(() => uniqueDocs.value.filter((c) => gtOf(c.documentId) >= 2).slice(0, 3));

onMounted(() => {
  ensureTestKbs().catch((e) => {
    hint.value = String(e);
  });
  getMe()
    .then((row) => {
      userTag.value = row.username;
    })
    .catch(() => undefined);
});
</script>

<template>
  <main class="page debug-page">
    <div class="page-head">
      <div>
        <h1>调试模式</h1>
        <p class="sub">检索已开启的知识库。分数体系不同，勿横向比较大小。</p>
      </div>
      <div class="head-actions">
        <button class="btn" type="button" @click="save">保存配置</button>
        <button class="btn" type="button" @click="load">加载配置</button>
        <button class="btn" type="button" @click="reset">重置</button>
        <button class="btn btn-primary" type="button" :disabled="running" @click="run">
          {{ running ? "检索中…" : "运行 Evaluation" }}
        </button>
      </div>
    </div>
    <p class="hint">{{ hint }}</p>

    <section class="top-grid">
      <div class="card pad">
        <label>测试查询</label>
        <textarea v-model="query" rows="3" />
      </div>
      <div class="card pad">
        <label>数据集 / Ground Truth</label>
        <ul v-if="testKbs.length" class="test-list">
          <li v-for="kb in testKbs" :key="kb.id">
            <strong>{{ kb.name }}</strong>
            <span>{{ seedPreview(kb.name) || "短测试文" }}</span>
            <button class="btn-link" type="button" @click="removeTestKb(kb)">删除</button>
          </li>
        </ul>
        <p v-else class="tiny">还没有测试库。点下方按钮创建（最多 3 个）。</p>
        <select v-model="dataset">
          <option value="current_kb">当前用户已开启知识库</option>
          <option v-for="kb in testKbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
        <button class="btn" type="button" :disabled="!canSeed || seeding" @click="seedTestKb">
          {{ seeding ? "创建中…" : `创建测试库（${testKbs.length}/${TEST_MAX}）` }}
        </button>
        <p class="tiny">测试库正文不超过 30 字，同时最多 3 个。Ground Truth 写入 retrieval_label。</p>
      </div>
      <div class="card pad">
        <label>Evaluation K</label>
        <p class="tiny">只用于 Recall@K / Precision@K 等，与检索 K/N/M 独立</p>
        <div class="chips">
          <button
            v-for="opt in EVAL_OPTIONS"
            :key="opt"
            type="button"
            class="pill"
            :class="{ on: evalKs.includes(opt) }"
            @click="toggleEval(opt)"
          >
            {{ opt }}
          </button>
        </div>
      </div>
    </section>

    <h2 class="block-title">Retrieval Configuration</h2>
    <section class="stage-grid">
      <div class="card stage vector">
        <h2>1. Vector Search</h2>
        <div class="stage-body">
        <label>Vector TopK</label>
        <input v-model.number="k" type="number" min="1" max="100" />
        <label>Similarity Threshold</label>
        <input v-model.number="vectorThreshold" type="number" min="0" max="1" step="0.01" />
        </div>
      </div>
      <div class="card stage bm25">
        <h2>2. BM25 Search</h2>
        <div class="stage-body">
        <label>BM25 TopK</label>
        <input v-model.number="bm25K" type="number" min="1" max="100" />
        </div>
      </div>
      <div class="card stage rrf">
        <h2>3. RRF Fusion</h2>
        <div class="stage-body">
        <label>TopK（N）</label>
        <input v-model.number="n" type="number" min="1" max="100" />
        <label>RRF rank constant</label>
        <input v-model.number="rrfKConst" type="number" min="1" max="200" />
        <label>算法</label>
        <select disabled>
          <option>Reciprocal Rank Fusion</option>
        </select>
        </div>
      </div>
      <div class="card stage rerank">
        <h2>4. Rerank</h2>
        <div class="stage-body">
        <label>TopK（M）</label>
        <input v-model.number="m" type="number" min="1" max="100" />
        <label>Score Threshold</label>
        <input v-model.number="rerankThreshold" type="number" min="0" max="1" step="0.01" />
        </div>
      </div>
      <div class="card pad">
        <h2>其他选项</h2>
        <label>Rerank 模型</label>
        <input v-model="rerankModel" />
        <label>最大候选数（送 Rerank）</label>
        <input v-model.number="maxRerankCands" type="number" min="1" max="200" />
      </div>
      <div class="card pad legend">
        <h2>参数说明</h2>
        <p><b>Vector TopK</b>：向量检索返回的候选数量</p>
        <p><b>BM25 TopK</b>：BM25 检索返回的候选数量</p>
        <p><b>RRF TopK</b>：融合后保留的候选数量</p>
        <p><b>Rerank TopK</b>：精排后返回给 LLM 的数量</p>
        <p><b>Evaluation K</b>：评估时检查前 K 个结果</p>
      </div>
    </section>

    <section class="card pad pipe">
      <div class="pipe-head">
        <h2>Pipeline Trace</h2>
        <div class="pipe-actions">
          <label class="toggle">
            <span>显示详情</span>
            <input v-model="showDetails" type="checkbox" role="switch" />
          </label>
          <button class="btn" type="button" :disabled="!ran" @click="exportJson">
            <svg class="export-ico" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"
              />
            </svg>
            导出结果
          </button>
        </div>
      </div>
      <div class="pipe-track">
        <div class="pipe-node query">
          <h3>Query</h3>
          <p class="pipe-q">{{ query || "—" }}</p>
          <p class="pipe-stat">整次 {{ ran ? lat.total : "—" }}ms</p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node vector">
          <h3>Vector Search</h3>
          <p>召回 {{ ran ? vectorRows.length : k }} 条</p>
          <p class="pipe-stat">pgvector</p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node bm25">
          <h3>BM25 Search</h3>
          <p>召回 {{ ran ? bm25Rows.length : bm25K }} 条</p>
          <p class="pipe-stat">Elasticsearch</p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node rrf">
          <h3>RRF Fusion</h3>
          <p>融合后 {{ ran ? rrfRows.length : n }} 条</p>
          <p class="pipe-stat">应用层</p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node rerank">
          <h3>Rerank</h3>
          <p>精排后 {{ ran ? rerankRows.length : m }} 条</p>
          <p class="pipe-stat">{{ rerankModel || "模型见配置" }}</p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node final">
          <h3>Final Context</h3>
          <p>送入 LLM {{ ran ? finalRows.length : m }} 条</p>
          <p class="pipe-stat">相关过滤后</p>
        </div>
      </div>
    </section>

    <section v-if="showDetails && ran" class="detail-grid">
      <div class="card pad">
        <h2>Vector Search</h2>
        <p class="tiny">Requested TopK {{ k }} · Threshold {{ vectorThreshold }} · Actual {{ vectorRows.length }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Vector Rank</th>
                <th>Similarity</th>
                <th>Document ID</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in vectorRows" :key="c.chunkId">
                <td>{{ c.vectorRank }}</td>
                <td>{{ c.vectorScore?.toFixed(3) }}</td>
                <td>{{ c.documentId }}</td>
                <td>{{ c.title }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card pad">
        <h2>BM25 / ES</h2>
        <p class="tiny">Requested TopK {{ bm25K }} · Actual {{ bm25Rows.length }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>BM25 Rank</th>
                <th>BM25 Score</th>
                <th>Document ID</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in bm25Rows" :key="c.chunkId">
                <td>{{ c.bm25Rank }}</td>
                <td>{{ c.bm25Score?.toFixed(2) }}</td>
                <td>{{ c.documentId }}</td>
                <td>{{ c.title }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card pad">
        <h2>RRF</h2>
        <p class="tiny">Candidate {{ vectorRows.length + bm25Rows.length }} · TopN {{ n }} · Actual {{ rrfRows.length }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>RRF Rank</th>
                <th>RRF Score</th>
                <th>Vector Rank</th>
                <th>BM25 Rank</th>
                <th>Document ID</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in rrfRows"
                :key="c.chunkId"
                class="clickable"
                :class="{ on: formulaId === c.chunkId }"
                @click="formulaId = formulaId === c.chunkId ? null : c.chunkId"
              >
                <td>{{ c.rrfRank }}</td>
                <td>{{ c.rrfScore?.toFixed(4) }}</td>
                <td>{{ c.vectorRank ?? "—" }}</td>
                <td>{{ c.bm25Rank ?? "—" }}</td>
                <td>{{ c.documentId }}</td>
                <td>{{ c.title }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="formulaRow" class="formula">{{ rrfParts(formulaRow) }}</p>
      </div>
      <div class="card pad">
        <h2>Rerank</h2>
        <p class="tiny">Model {{ rerankModel }} · TopM {{ m }} · Actual {{ rerankRows.length }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rerank Rank</th>
                <th>Rerank Score</th>
                <th>Document ID</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in rerankRows" :key="c.chunkId">
                <td>{{ c.rerankRank }}</td>
                <td>{{ c.rerankScore?.toFixed(3) }}</td>
                <td>{{ c.documentId }}</td>
                <td>{{ c.title }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="bottom-grid">
      <div class="card pad">
        <div class="tabs">
          <button type="button" :class="{ on: resultTab === 'rerank' }" @click="resultTab = 'rerank'">
            Rerank 结果 (Top {{ m }})
          </button>
          <button type="button" :class="{ on: resultTab === 'rrf' }" @click="resultTab = 'rrf'">RRF 结果 (Top {{ n }})</button>
          <button type="button" :class="{ on: resultTab === 'vector' }" @click="resultTab = 'vector'">
            Vector 结果 (Top {{ k }})
          </button>
          <button type="button" :class="{ on: resultTab === 'bm25' }" @click="resultTab = 'bm25'">BM25 结果 (Top {{ bm25K }})</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>文档标题</th>
                <th>来源</th>
                <th>Vector Score</th>
                <th>BM25 Score</th>
                <th>RRF Score</th>
                <th>Rerank Score</th>
                <th>GT</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!tabRows.length">
                <td colspan="9" class="empty">点击运行后查看</td>
              </tr>
              <tr v-for="c in tabRows" :key="c.chunkId">
                <td>{{ c.rerankRank || c.rrfRank || c.vectorRank || c.bm25Rank }}</td>
                <td>{{ c.title }}</td>
                <td>{{ c.source }}</td>
                <td>{{ c.vectorScore?.toFixed(3) ?? "—" }}</td>
                <td>{{ c.bm25Score?.toFixed(2) ?? "—" }}</td>
                <td>{{ c.rrfScore?.toFixed(4) ?? "—" }}</td>
                <td>{{ c.rerankScore?.toFixed(3) ?? "—" }}</td>
                <td>
                  <select :value="gtOf(c.documentId)" @change="setGt(c.documentId, Number(($event.target as HTMLSelectElement).value))">
                    <option v-for="(lab, gi) in GT_LABELS" :key="gi" :value="gi">{{ gi }}</option>
                  </select>
                </td>
                <td>
                  <button class="btn-link" type="button" @click="formulaId = c.chunkId; showDetails = true">查看</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card pad">
        <h2>Evaluation Metrics</h2>
        <p class="tiny">只根据 Ground Truth（≥2 视为相关），不用检索分推断。</p>
        <select>
          <option>Default Metric Set</option>
        </select>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>指标</th>
                <th v-for="ek in evalKs" :key="ek">@{{ ek }}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Recall@K</td>
                <td v-for="ek in evalKs" :key="'r' + ek">{{ recallAt(ek) }}</td>
              </tr>
              <tr>
                <td>Precision@K</td>
                <td v-for="ek in evalKs" :key="'p' + ek">{{ precisionAt(ek) }}</td>
              </tr>
              <tr>
                <td>MRR@K</td>
                <td v-for="ek in evalKs" :key="'m' + ek">{{ mrrAt(ek) }}</td>
              </tr>
              <tr>
                <td>NDCG@K</td>
                <td v-for="ek in evalKs" :key="'n' + ek">{{ ndcgAt(ek) }}</td>
              </tr>
              <tr>
                <td>Hit@K</td>
                <td v-for="ek in evalKs" :key="'h' + ek">{{ hitAt(ek) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="tiny">Ground Truth 命中位置分布（本次查询）：{{ gtHits.length }}</p>
      </div>
    </section>

    <section class="card pad gt-foot">
      <h2>Ground Truth（本次查询）</h2>
      <p v-if="!gtHits.length" class="tiny">在结果表 GT 列把文档标成 2/3 后会出现在这里。</p>
      <ul>
        <li v-for="c in gtHits" :key="c.documentId">
          <strong>{{ c.title }}</strong>
          <span>{{ c.path }}</span>
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.debug-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem;
  font-size: 12.5px;
  background: transparent;
}
.debug-page .btn {
  padding: 0.5rem 0.85rem;
  border-radius: 10px;
  font-size: inherit;
}
.debug-page .pill {
  padding: 0.28rem 0.7rem;
  font-size: inherit;
}
.debug-page .page-head h1 {
  font-size: 1.05rem;
}
.block-title {
  margin: 0 0 0.45rem;
  font-size: 0.8rem;
  color: var(--text);
}
.top-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
  margin-bottom: 1rem;
}
.top-grid .btn {
  margin-top: 0.4rem;
  width: 100%;
}
.test-list {
  margin: 0.35rem 0 0.45rem;
  padding: 0;
  list-style: none;
  font-size: 0.72rem;
}
.test-list li {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.1rem 0.4rem;
  align-items: start;
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--line);
}
.test-list span {
  grid-column: 1;
  color: var(--muted);
}
.test-list .btn-link {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
}
.stage-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(8.5rem, 1fr));
  gap: 0.65rem;
  margin-bottom: 1rem;
  overflow-x: auto;
  align-items: stretch;
}
.stage-grid > .card {
  min-width: 8.5rem;
  height: 100%;
}
.stage-grid .pad {
  padding: 0.45rem 0.55rem 0.5rem;
}
.stage {
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.stage h2 {
  margin: 0;
  padding: 0.4rem 0.55rem;
  font-size: 0.72rem;
}
.stage-body {
  padding: 0.35rem 0.55rem 0.5rem;
  flex: 1;
}
.stage.vector {
  border-left: 3px solid #3b82f6;
}
.stage.vector h2 {
  background: #f0f7ff;
  color: #1d4ed8;
}
.stage.bm25 {
  border-left: 3px solid #22a06b;
}
.stage.bm25 h2 {
  background: #f3fbf6;
  color: #166534;
}
.stage.rrf {
  border-left: 3px solid #7c5cbf;
}
.stage.rrf h2 {
  background: #f6f3ff;
  color: #5b21b6;
}
.stage.rerank {
  border-left: 3px solid #e67e22;
}
.stage.rerank h2 {
  background: #fff8f1;
  color: #c2410c;
}
.stage-grid .pad label,
.stage-body label {
  margin: 0.2rem 0 0.08rem;
  font-size: 0.62rem;
  display: block;
  color: var(--muted);
}
.stage-grid .pad input,
.stage-grid .pad select,
.stage-body input,
.stage-body select {
  width: 100%;
  height: 1.55rem;
  padding: 0.12rem 0.35rem;
  font-size: 0.72rem;
  line-height: 1.2;
  border-radius: 6px;
  border: 1px solid var(--line);
}
.head-actions,
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}
.pipe-head {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.55rem;
}
.pipe-head h2 {
  margin: 0;
  line-height: 1.2;
}
.pipe-actions {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.65rem;
}
.pipe-actions .toggle {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 0.4rem;
  height: 2rem;
  margin: 0;
  padding: 0;
  font-size: 0.72rem;
  color: var(--muted);
  line-height: 1;
}
.pipe-actions .btn {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  height: 2rem;
  margin: 0;
  padding: 0 0.7rem;
  line-height: 1;
}
.pipe-actions .export-ico {
  width: 0.85rem;
  height: 0.85rem;
  flex-shrink: 0;
}
.pipe-track {
  display: flex;
  flex-wrap: nowrap;
  align-items: stretch;
  gap: 0.2rem;
  overflow-x: auto;
  padding: 0.15rem 0 0.35rem;
}
.pipe-node {
  flex: 1 1 0;
  min-width: 7.2rem;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.45rem 0.5rem 0.5rem;
}
.pipe-node.query {
  background: #fff;
}
.pipe-node.vector {
  background: #f0f7ff;
  border-color: #e0edff;
}
.pipe-node.bm25 {
  background: #f3fbf6;
  border-color: #e3f5ea;
}
.pipe-node.rrf {
  background: #f6f3ff;
  border-color: #ece7ff;
}
.pipe-node.rerank {
  background: #fff8f1;
  border-color: #ffedd5;
}
.pipe-node.final {
  background: #f0f7ff;
  border-color: #e0edff;
}
.pipe-node h3 {
  margin: 0 0 0.25rem;
  font-size: 0.72rem;
  font-weight: 650;
}
.pipe-node p {
  margin: 0;
  font-size: 0.68rem;
  color: var(--text);
}
.pipe-q {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--muted) !important;
  margin-bottom: 0.2rem !important;
}
.pipe-stat {
  margin-top: 0.2rem !important;
  color: var(--muted) !important;
}
.pipe-arrow {
  flex: 0 0 auto;
  align-self: center;
  color: #94a3b8;
  font-size: 0.9rem;
  padding: 0 0.05rem;
}
.pipe-arrow {
  flex: 0 0 auto;
  align-self: center;
  color: #94a3b8;
  font-size: 0.9rem;
  padding: 0 0.05rem;
}
.toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.72rem;
  color: var(--muted);
  width: auto;
  height: 2rem;
  cursor: pointer;
  margin: 0;
  line-height: 1;
}
.toggle input {
  appearance: none;
  -webkit-appearance: none;
  width: 2.1rem !important;
  height: 1.15rem !important;
  padding: 0 !important;
  margin: 0;
  border: none;
  border-radius: 999px;
  background: #cbd5e1;
  position: relative;
  cursor: pointer;
  flex-shrink: 0;
}
.toggle input::after {
  content: "";
  position: absolute;
  top: 0.12rem;
  left: 0.12rem;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 50%;
  background: #fff;
  transition: left 0.15s;
}
.toggle input:checked {
  background: #2563eb;
}
.toggle input:checked::after {
  left: 1.05rem;
}
.hint,
.tiny {
  color: var(--muted);
  font-size: 0.75rem;
}
.tiny {
  margin: 0.2rem 0 0.5rem;
}
.pad {
  padding: 1rem 1.1rem;
}
.pad h2 {
  margin: 0 0 0.4rem;
  font-size: 0.78rem;
}
.pipe-head h2 {
  margin: 0;
}
.pad label:not(.toggle) {
  display: block;
  font-size: 0.68rem;
  color: var(--muted);
  margin: 0.3rem 0 0.15rem;
}
.pad textarea,
.pad input,
.pad select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin-bottom: 1rem;
}
.stage-grid .legend {
  background: #eff6ff;
  border-color: #dbeafe;
}
.stage-grid .legend h2 {
  font-size: 0.7rem;
  color: #2563eb;
}
.legend p {
  margin: 0.12rem 0;
  font-size: 0.58rem;
  color: #64748b;
  line-height: 1.4;
}
.legend b {
  color: #2563eb;
  font-weight: 600;
}
.bottom-grid {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 1rem;
  margin: 1rem 0;
}
.tabs {
  display: flex;
  flex-wrap: nowrap;
  gap: 0;
  margin: 0 0 0.55rem;
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
  font-size: 0.72rem;
  white-space: nowrap;
  box-shadow: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tabs button.on {
  background: none;
  color: var(--teal);
  font-weight: 600;
  border-color: transparent;
  border-bottom-color: var(--teal);
}
.table-wrap {
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
th,
td {
  text-align: left;
  padding: 0.4rem 0.45rem;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.empty {
  color: var(--muted);
}
.clickable {
  cursor: pointer;
}
.clickable.on {
  background: var(--teal-soft);
}
.formula {
  margin: 0.6rem 0 0;
  font-family: ui-monospace, monospace;
  font-size: 0.82rem;
}
.gt-foot ul {
  margin: 0;
  padding-left: 1.1rem;
}
.gt-foot span {
  margin-left: 0.5rem;
  color: var(--muted);
  font-size: 0.82rem;
}
@media (max-width: 720px) {
  .bottom-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 560px) {
  .top-grid {
    grid-template-columns: 1fr;
  }
}
</style>
