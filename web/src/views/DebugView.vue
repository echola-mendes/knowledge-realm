<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import ChunkMultiSelect from "../components/ChunkMultiSelect.vue";
import {
  getMe,
  judgeAnswerQuality,
  listDebugDatasetChunks,
  listKnowledgeBases,
  listRetrievalLabels,
  putRetrievalLabel,
  runRetrievalDebug,
  streamAgentTrace,
  type AgentTraceEvent,
  type AgentTraceStep,
  type AnswerQuality,
  type DebugDatasetChunk,
  type KnowledgeBase,
  type RetrievalDebugRow,
} from "../api";

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

const query = ref("");
const searchQuery = ref("");
const nextAction = ref<"search" | "generate">("search");
const datasetChunks = ref<DebugDatasetChunk[]>([]);
const selectedGtChunks = ref<string[]>([]);
const gtQueryHint = computed(() => (query.value.trim() ? "" : "请先填写测试查询"));

function optionLabel(chunkId: string) {
  return datasetChunks.value.find((c) => c.chunk_id === chunkId)?.chunk_label || chunkId.slice(0, 8);
}

function chunkLabelOf(chunkId: string) {
  return datasetChunks.value.find((c) => c.chunk_id === chunkId)?.chunk_label || chunkId.slice(0, 8);
}

function chunkContentOf(chunkId: string) {
  return datasetChunks.value.find((c) => c.chunk_id === chunkId)?.content || "";
}

async function loadDatasetChunks() {
  try {
    datasetChunks.value = await listDebugDatasetChunks();
  } catch (e) {
    hint.value = String(e);
  }
}

async function loadGtSelection() {
  const q = query.value.trim();
  if (!q) {
    selectedGtChunks.value = [];
    return;
  }
  try {
    const rows = await listRetrievalLabels(q);
    gtMap.value = Object.fromEntries(rows.map((r) => [r.chunk_id, r.relevance]));
    selectedGtChunks.value = rows.filter((r) => r.relevance >= 2).map((r) => r.chunk_id);
  } catch (e) {
    hint.value = String(e);
  }
}

async function toggleGtChunk(chunkId: string) {
  const q = query.value.trim();
  if (!q) {
    hint.value = "先填写测试查询，再选择切片编号。";
    return;
  }
  const set = new Set(selectedGtChunks.value);
  const adding = !set.has(chunkId);
  if (adding) set.add(chunkId);
  else set.delete(chunkId);
  selectedGtChunks.value = [...set];
  const next = adding ? 3 : 0;
  try {
    await putRetrievalLabel({ query: q, chunk_id: chunkId, relevance: next });
    gtMap.value = { ...gtMap.value, [chunkId]: next };
    hint.value = `已保存 ${selectedGtChunks.value.length} 条标准切片（${selectedGtChunks.value.map((id) => optionLabel(id)).join(", ") || "—"}）。`;
  } catch (e) {
    hint.value = String(e);
    if (adding) {
      selectedGtChunks.value = selectedGtChunks.value.filter((id) => id !== chunkId);
    } else {
      selectedGtChunks.value = [...selectedGtChunks.value, chunkId];
    }
  }
}

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
const hint = ref("");
const lat = ref({ plan: 0, vector: 0, bm25: 0, rrf: 0, rerank: 0, final: 0, total: 0 });
const hits = ref({ vector: 0, bm25: 0, final: 0 });
const hybridStatus = computed<"idle" | "running" | "done" | "error">(() => {
  if (running.value) return "running";
  if (ran.value) return "done";
  if (hint.value && /失败|错误|Error|Exception/i.test(hint.value)) return "error";
  return "idle";
});
const hybridStatusText = computed(() => {
  const map = { idle: "未运行", running: "检索中…", done: "检索完成", error: "失败" } as const;
  return map[hybridStatus.value];
});
const primaryEvalK = computed(() => evalKs.value[0] ?? 5);

const activeTab = ref<"trace" | "hybrid">("trace");

// ---- Agent 执行轨迹（AGENT-TRACE）----
const traceQuery = ref("");
const traceKbId = ref("");
const traceAllowWeb = ref(false);
const traceRunning = ref(false);
const traceSteps = ref<AgentTraceStep[]>([]);
const traceTokens = ref<{ prompt_tokens: number; completion_tokens: number; total_tokens: number } | null>(null);
const traceFinal = ref<{
  answer: string;
  citations: { document_name: string; score: number; content?: string }[];
  loop_count: number;
} | null>(null);
const answerQuality = ref<AnswerQuality | null>(null);
const judging = ref(false);
const judgeError = ref("");
const traceError = ref("");
const knowledgeBases = ref<KnowledgeBase[]>([]);
const traceStatus = ref<"idle" | "running" | "done" | "error">("idle");
const traceTab = ref<"result" | "chain" | "tools" | "model" | "json">("result");
const traceEvents = ref<AgentTraceEvent[]>([]);

const TRACE_SCENARIOS: { category: string; note: string; items: { title: string; expect: string; question: string }[] }[] = [
  {
    category: "知识库问答",
    note: "验证知识库检索与引用来源。",
    items: [
      {
        title: "会议室预约需要提前多久申请？",
        expect: "预期：命中知识库并以引用来源标注出处。",
        question: "会议室预约需要提前多久申请？",
      },
      {
        title: "帮我总结员工考勤制度里关于请假和加班的规定",
        expect: "预期：多片段综合，回答覆盖请假与加班两部分。",
        question: "帮我总结员工考勤制度里关于请假和加班的规定",
      },
    ],
  },
  {
    category: "知识边界",
    note: "验证无真实数据源时不编造事实。",
    items: [
      {
        title: "我们公司的年假能累计到明年吗？具体有效期多久？",
        expect: "预期：知识库没有的规定应明确说明查不到，不编造。",
        question: "我们公司的年假能累计到明年吗？具体有效期多久？",
      },
    ],
  },
  {
    category: "上下文理解",
    note: "验证直接生成路径（不调用 Tool）。",
    items: [
      {
        title: "你好",
        expect: "预期：reason 选 DIRECT，0 次工具调用直接回答。",
        question: "你好",
      },
    ],
  },
  {
    category: "复合推理",
    note: "验证子任务拆分与多轮检索。",
    items: [
      {
        title: "对比一下会议室使用规范和请假流程里对提前申请的要求",
        expect: "预期：reason 拆分子任务，多轮 RAG 后汇总对比。",
        question: "对比一下会议室使用规范和请假流程里对提前申请的要求",
      },
    ],
  },
];
const traceScenarioTab = ref(0);
const activeScenario = computed(() => TRACE_SCENARIOS[traceScenarioTab.value]);

const traceToolSteps = computed(() => traceSteps.value.filter((s) => s.node === "run_tool"));
const traceModelCalls = computed(() => traceSteps.value.filter((s) => s.node === "reason" || s.node === "generate").length);
const traceTotalMs = computed(() => traceSteps.value.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0));
const traceStatusText = computed(() => {
  if (traceStatus.value === "running") return "RUNNING";
  if (traceStatus.value === "error") return "ERROR";
  if (traceStatus.value === "done") return "DONE";
  return "IDLE";
});
const traceStopReason = computed(() => {
  if (traceStatus.value === "running") return "—";
  if (traceStatus.value === "error") return traceError.value || "执行异常";
  if (traceFinal.value) return `正常结束 · ${traceFinal.value.loop_count} 轮工具调用`;
  return "—";
});
const traceDelayBars = computed(() => {
  const total = traceTotalMs.value;
  return traceSteps.value.map((s) => ({
    label: traceStepTitle(s),
    ms: s.elapsed_ms || 0,
    pct: total ? Math.round(((s.elapsed_ms || 0) / total) * 100) : 0,
  }));
});
const traceTips = computed(() => {
  const tips: string[] = [];
  if (traceStatus.value === "idle") return ["输入问题并点击「运行测试」查看执行链。"];
  if (traceStatus.value === "running") return ["执行中，每完成一个节点会实时追加。"];
  const bars = traceDelayBars.value.slice().sort((a, b) => b.ms - a.ms);
  if (bars.length && bars[0].ms > 0) {
    tips.push(`主要延迟来自「${bars[0].label}」（${bars[0].pct}%）；如果需要优化，优先检查该阶段。`);
  }
  if (traceFinal.value && !traceFinal.value.citations.length) {
    tips.push("本轮没有引用来源：可能 reason 选择了直接生成，或知识库未命中（可在 Hybrid Search 页检查检索得分）。");
  }
  if (traceFinal.value) {
    tips.push(`Agent 正常结束，共 ${traceModelCalls.value} 次模型调用、${traceToolSteps.value.length} 次工具调用。`);
  }
  return tips;
});
const traceRawJson = computed(() => JSON.stringify(traceEvents.value, null, 2));

function applyScenario(question: string) {
  traceQuery.value = question;
}

function copyRawJson() {
  navigator.clipboard?.writeText(traceRawJson.value).catch(() => undefined);
}

function copyAnswer() {
  if (traceFinal.value) navigator.clipboard?.writeText(traceFinal.value.answer).catch(() => undefined);
}

async function loadKnowledgeBases() {
  try {
    knowledgeBases.value = await listKnowledgeBases();
    if (!traceKbId.value) {
      traceKbId.value = knowledgeBases.value[0]?.id || "";
    }
  } catch (e) {
    traceError.value = String(e);
  }
}

function traceStepTitle(step: AgentTraceStep) {
  if (step.node === "reason") {
    const action = step.action === "search" ? "RAG 检索" : step.action === "web" ? "WEB 联网" : "直接生成";
    return `reason → ${action}`;
  }
  if (step.node === "run_tool") return `工具 ${step.tool || ""} · 命中 ${step.hits ?? 0} 条`;
  if (step.node === "generate") return `生成回答（${step.answer_len ?? 0} 字）`;
  return step.node;
}

async function runTrace() {
  const q = traceQuery.value.trim();
  if (!q) {
    traceError.value = "请输入测试问题";
    return;
  }
  traceRunning.value = true;
  traceStatus.value = "running";
  traceError.value = "";
  traceSteps.value = [];
  traceTokens.value = null;
  traceEvents.value = [];
  traceFinal.value = null;
  answerQuality.value = null;
  judgeError.value = "";
  try {
    await streamAgentTrace(
      {
        query: q,
        knowledge_base_id: traceKbId.value || undefined,
        task: "agent",
        allow_web: traceAllowWeb.value,
      },
      (event: AgentTraceEvent) => {
        traceEvents.value.push(event);
        if (event.type === "step") {
          traceSteps.value.push(event);
          if (event.tokens) {
            traceTokens.value = {
              prompt_tokens: (traceTokens.value?.prompt_tokens || 0) + event.tokens.prompt_tokens,
              completion_tokens: (traceTokens.value?.completion_tokens || 0) + event.tokens.completion_tokens,
              total_tokens: (traceTokens.value?.total_tokens || 0) + event.tokens.total_tokens,
            };
          }
        } else {
          traceFinal.value = { answer: event.answer, citations: event.citations, loop_count: event.loop_count };
          if (event.tokens) traceTokens.value = event.tokens;
          answerQuality.value = null;
          judgeError.value = "";
          traceStatus.value = "done";
        }
      },
    );
    if (traceStatus.value === "running") traceStatus.value = "error";
  } catch (e) {
    traceError.value = e instanceof Error ? e.message : String(e);
    traceStatus.value = "error";
  } finally {
    traceRunning.value = false;
  }
}

async function evaluateAnswer() {
  if (!traceFinal.value || judging.value) return;
  judging.value = true;
  judgeError.value = "";
  try {
    answerQuality.value = await judgeAnswerQuality({
      query: traceQuery.value.trim(),
      answer: traceFinal.value.answer,
      contexts: traceFinal.value.citations.map((c) => c.content || "").filter(Boolean),
    });
  } catch (e) {
    judgeError.value = e instanceof Error ? e.message : String(e);
  } finally {
    judging.value = false;
  }
}

function gtOf(id: string) {
  return gtMap.value[id] ?? 0;
}

function setGt(id: string, v: number) {
  gtMap.value = { ...gtMap.value, [id]: v };
  if (!query.value.trim()) return;
  putRetrievalLabel({
    query: query.value,
    chunk_id: id,
    relevance: v,
  }).catch((e) => {
    hint.value = String(e);
  });
  if (v >= 2) {
    if (!selectedGtChunks.value.includes(id)) {
      selectedGtChunks.value = [...selectedGtChunks.value, id];
    }
  } else {
    selectedGtChunks.value = selectedGtChunks.value.filter((x) => x !== id);
  }
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
    searchQuery.value = body.search_query || q;
    nextAction.value = body.next_action === "generate" ? "generate" : "search";
    rerankModel.value = body.rerank.model || rerankModel.value;
    const tm = body.timings;
    lat.value = {
      plan: tm?.plan_ms ?? 0,
      vector: (tm?.embed_ms ?? 0) + (tm?.vector_ms ?? 0),
      bm25: tm?.bm25_ms ?? 0,
      rrf: tm?.rrf_ms ?? 0,
      rerank: tm?.rerank_ms ?? 0,
      final: tm?.final_ms ?? 0,
      total: ms,
    };
    hits.value = {
      vector: body.vector.actual_count ?? 0,
      bm25: body.bm25.actual_count ?? 0,
      final: body.final.length,
    };
    ran.value = true;
    formulaId.value = null;
    const sqNote =
      searchQuery.value !== q ? `；search_query「${searchQuery.value}」` : "";
    const actionNote = nextAction.value === "generate" ? "（Agent 判定不检索，仍用原问题跑检索）" : "";
    hint.value = `检索完成（整次 ${ms} ms）${sqNote}${actionNote}。向量 ${body.vector.actual_count} / BM25 ${body.bm25.actual_count} / Final ${body.final.length}。`;
  } catch (e) {
    hint.value = String(e);
  } finally {
    running.value = false;
  }
}

function reset() {
  query.value = "";
  searchQuery.value = "";
  nextAction.value = "search";
  selectedGtChunks.value = [];
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
      selectedGtChunks: selectedGtChunks.value,
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
}

function load() {
  const raw = localStorage.getItem(STORAGE.value);
  if (!raw) {
    hint.value = "没有已保存的配置。";
    return;
  }
  const c = JSON.parse(raw) as Record<string, unknown>;
  if (typeof c.query === "string") query.value = c.query;
  if (Array.isArray(c.selectedGtChunks)) {
    selectedGtChunks.value = c.selectedGtChunks.filter((x): x is string => typeof x === "string");
  }
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

const uniqueChunks = computed(() => {
  const seen = new Set<string>();
  const list: Cand[] = [];
  for (const c of [...finalRows.value, ...cands.value]) {
    if (seen.has(c.chunkId)) continue;
    seen.add(c.chunkId);
    list.push(c);
  }
  return list;
});

const relevantIds = computed(() => uniqueChunks.value.filter((c) => gtOf(c.chunkId) >= 2).map((c) => c.chunkId));

function finalChunkOrder() {
  return finalRows.value.map((c) => c.chunkId);
}

function precisionAt(at: number) {
  if (!ran.value) return "—";
  const order = finalChunkOrder().slice(0, at);
  if (!order.length) return "0.00";
  const hits = order.filter((id) => relevantIds.value.includes(id)).length;
  return (hits / order.length).toFixed(2);
}

function recallAt(at: number) {
  if (!ran.value) return "—";
  const rel = relevantIds.value;
  if (!rel.length) return "—";
  const order = finalChunkOrder().slice(0, at);
  const hits = order.filter((id) => rel.includes(id)).length;
  return (hits / rel.length).toFixed(2);
}

function hitAt(at: number) {
  if (!ran.value) return "—";
  const rel = relevantIds.value;
  if (!rel.length) return "—";
  const order = finalChunkOrder().slice(0, at);
  return order.some((id) => rel.includes(id)) ? "1.00" : "0.00";
}

function mrrAt(at: number) {
  if (!ran.value) return "—";
  const rel = new Set(relevantIds.value);
  if (!rel.size) return "—";
  const order = finalChunkOrder().slice(0, at);
  const idx = order.findIndex((id) => rel.has(id));
  if (idx < 0) return "0.00";
  return (1 / (idx + 1)).toFixed(2);
}

function ndcgAt(at: number) {
  if (!ran.value) return "—";
  const order = finalChunkOrder().slice(0, at);
  let dcg = 0;
  order.forEach((id, i) => {
    const g = gtOf(id);
    if (g <= 0) return;
    dcg += (2 ** g - 1) / Math.log2(i + 2);
  });
  const ideal = [...uniqueChunks.value]
    .map((c) => gtOf(c.chunkId))
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
const gtHits = computed(() =>
  datasetChunks.value.filter((c) => selectedGtChunks.value.includes(c.chunk_id)).slice(0, 5),
);

watch(query, () => {
  loadGtSelection().catch((e) => {
    hint.value = String(e);
  });
});

onMounted(() => {
  loadDatasetChunks().catch((e) => {
    hint.value = String(e);
  });
  loadKnowledgeBases();
  getMe()
    .then((row) => {
      userTag.value = row.username;
    })
    .catch(() => undefined);
});
</script>

<template>
  <main class="page debug-page">
    <div class="debug-scroll">
    <div class="page-head">
      <div>
        <h1>调试模式</h1>
        <p class="sub">检索已开启的知识库。分数体系不同，勿横向比较大小。</p>
      </div>
    </div>

    <div class="debug-tabs">
      <button type="button" class="debug-tab" :class="{ on: activeTab === 'trace' }" @click="activeTab = 'trace'">
        Agent Trace
      </button>
      <button type="button" class="debug-tab" :class="{ on: activeTab === 'hybrid' }" @click="activeTab = 'hybrid'">
        Hybrid Search
      </button>
    </div>

    <section v-show="activeTab === 'trace'" class="trace-wrap">
      <div class="trace-stats">
        <div class="stat-card">
          <p class="stat-label">运行状态</p>
          <p class="stat-value" :class="traceStatus">{{ traceStatusText }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">终止原因</p>
          <p class="stat-value small">{{ traceStopReason }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">总 Token</p>
          <p class="stat-value">{{ traceTokens ? traceTokens.total_tokens : "—" }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">总耗时</p>
          <p class="stat-value">{{ traceTotalMs }} ms</p>
        </div>
      </div>

      <section class="card pad trace-panel">
        <div class="trace-cols">
          <div class="trace-left">
            <h2 class="trace-sec-title">请求</h2>
            <p class="tiny">旁路运行 Agent 图，逐节点记录执行链。不影响真实会话。</p>
            <label class="trace-field-label">知识库</label>
            <select v-model="traceKbId" class="trace-kb">
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
                {{ kb.name }}{{ kb.is_default ? "（默认）" : "" }}
              </option>
            </select>
            <div class="trace-scenarios">
              <p class="trace-field-label">快速场景</p>
              <div class="scenario-tabs">
                <button
                  v-for="(sc, i) in TRACE_SCENARIOS"
                  :key="sc.category"
                  type="button"
                  class="scenario-tab"
                  :class="{ on: traceScenarioTab === i }"
                  @click="traceScenarioTab = i"
                >
                  {{ sc.category }}
                </button>
              </div>
              <p class="tiny">{{ activeScenario.note }}</p>
              <button
                v-for="item in activeScenario.items"
                :key="item.title"
                type="button"
                class="scenario-card"
                @click="applyScenario(item.question)"
              >
                <strong>{{ item.title }}</strong>
                <span>{{ item.expect }}</span>
              </button>
            </div>
            <label class="trace-field-label">消息</label>
            <textarea
              v-model="traceQuery"
              rows="6"
              placeholder="输入测试问题，例如：会议室预约需要提前多久申请？"
              @keydown.ctrl.enter="runTrace"
              @keydown.meta.enter="runTrace"
            />
            <label class="trace-web">
              <input v-model="traceAllowWeb" type="checkbox" />
              智能搜索（允许联网）
            </label>
            <button class="btn btn-primary trace-run" type="button" :disabled="traceRunning" @click="runTrace">
              {{ traceRunning ? "运行中…" : "▶ 运行测试" }}
            </button>
          </div>

          <div class="trace-right">
            <div class="trace-right-head">
              <h2 class="trace-sec-title">响应</h2>
              <span class="status-badge" :class="traceStatus">{{ traceStatusText }}</span>
            </div>
            <p v-if="traceError" class="hint">{{ traceError }}</p>
            <div class="trace-subtabs">
              <button type="button" :class="{ on: traceTab === 'result' }" @click="traceTab = 'result'">结果与诊断</button>
              <button type="button" :class="{ on: traceTab === 'chain' }" @click="traceTab = 'chain'">执行链 {{ traceSteps.length }}</button>
              <button type="button" :class="{ on: traceTab === 'tools' }" @click="traceTab = 'tools'">Tool 与证据 {{ traceToolSteps.length }}</button>
              <button type="button" :class="{ on: traceTab === 'model' }" @click="traceTab = 'model'">模型调用 {{ traceModelCalls }}</button>
              <button type="button" :class="{ on: traceTab === 'json' }" @click="traceTab = 'json'">原始 JSON</button>
            </div>

            <div v-show="traceTab === 'result'" class="trace-result-grid">
              <div class="trace-answer-card">
                <div class="trace-answer-head">
                  <h3>最终回复</h3>
                  <div class="trace-answer-actions">
                    <button v-if="traceFinal && !judging" class="linkish" type="button" @click="evaluateAnswer">
                      评估回答
                    </button>
                    <span v-if="judging" class="tiny">评估中…</span>
                    <button v-if="traceFinal" class="linkish" type="button" @click="copyAnswer">
                      复制回复
                    </button>
                  </div>
                </div>
                <p v-if="traceFinal" class="trace-answer-text">{{ traceFinal.answer }}</p>
                <p v-else-if="traceRunning" class="tiny">生成中…</p>
                <p v-else class="tiny">运行后在这里显示最终回复。</p>
                <div v-if="judgeError" class="tiny judge-err">{{ judgeError }}</div>
                <div v-if="answerQuality" class="judge-result">
                  <span class="judge-pill">忠实 {{ answerQuality.faithfulness }}/5</span>
                  <span class="judge-pill">切题 {{ answerQuality.relevance }}/5</span>
                  <span class="judge-pill">完整 {{ answerQuality.completeness }}/5</span>
                  <ul v-if="answerQuality.issues.length" class="judge-issues">
                    <li v-for="issue in answerQuality.issues" :key="issue">{{ issue }}</li>
                  </ul>
                  <p v-else class="tiny">无明显问题。</p>
                </div>
              </div>
              <div class="trace-delay-card">
                <div class="trace-delay-head">
                  <h3>延迟归因</h3>
                  <span class="tiny">总耗时 {{ traceTotalMs }} ms</span>
                </div>
                <div v-for="bar in traceDelayBars" :key="bar.label + bar.ms" class="delay-row">
                  <p class="delay-label">
                    <span>{{ bar.label }}</span>
                    <span>{{ bar.ms }} ms · {{ bar.pct }}%</span>
                  </p>
                  <div class="delay-bar"><i :style="{ width: bar.pct + '%' }" /></div>
                </div>
                <p v-if="!traceSteps.length" class="tiny">暂无数据。</p>
              </div>
              <div class="trace-tips">
                <div class="trace-tips-head">
                  <h3>问题定位提示</h3>
                  <span class="tiny">先看结论，再进入执行链验证</span>
                </div>
                <p v-for="(tip, i) in traceTips" :key="i">{{ tip }}</p>
              </div>
            </div>

            <ol v-show="traceTab === 'chain'" class="trace-steps">
              <li v-for="(step, i) in traceSteps" :key="i" class="trace-step">
                <span class="trace-idx">{{ i + 1 }}</span>
                <div class="trace-body">
                  <p class="trace-title">
                    {{ traceStepTitle(step) }}
                    <span class="trace-ms">{{ step.elapsed_ms }}ms<template v-if="step.tokens"> · {{ step.tokens.total_tokens }} tokens</template></span>
                  </p>
                  <p v-if="step.query" class="trace-detail">query：{{ step.query }}</p>
                  <p v-if="step.subtasks?.length" class="trace-detail">子任务：{{ step.subtasks.join(" / ") }}</p>
                </div>
              </li>
            </ol>
            <p v-show="traceTab === 'chain' && !traceSteps.length" class="tiny">运行后逐步显示执行链。</p>

            <div v-show="traceTab === 'tools'" class="trace-tools">
              <div v-for="(step, i) in traceToolSteps" :key="i" class="trace-step">
                <div class="trace-body">
                  <p class="trace-title">{{ step.tool }} · 命中 {{ step.hits ?? 0 }} 条 <span class="trace-ms">{{ step.elapsed_ms }}ms</span></p>
                  <p class="trace-detail">query：{{ step.query }}</p>
                </div>
              </div>
              <p v-if="!traceToolSteps.length" class="tiny">本轮未调用 Tool；若问题需要知识库数据，请检查知识库选择或 reason 决策（执行链 Tab）。</p>
              <div v-if="traceFinal?.citations.length" class="trace-cites">
                <h3>证据（引用来源）</h3>
                <p v-for="(c, i) in traceFinal.citations" :key="i" class="trace-detail">
                  [{{ i + 1 }}] {{ c.document_name }} · score {{ c.score.toFixed(3) }}
                </p>
              </div>
            </div>

            <div v-show="traceTab === 'model'" class="trace-model">
              <table v-if="traceModelCalls" class="trace-table">
                <thead>
                  <tr><th>#</th><th>节点</th><th>说明</th><th>耗时</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(step, i) in traceSteps.filter((s) => s.node === 'reason' || s.node === 'generate')" :key="i">
                    <td>{{ i + 1 }}</td>
                    <td>{{ step.node }}</td>
                    <td>{{ traceStepTitle(step) }}</td>
                    <td>{{ step.elapsed_ms }} ms</td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="tiny">运行后显示模型调用明细（reason / generate 各计一次）。</p>
            </div>

            <div v-show="traceTab === 'json'" class="trace-json">
              <button class="btn" type="button" @click="copyRawJson">复制调试响应 JSON</button>
              <pre>{{ traceEvents.length ? traceRawJson : "运行后显示原始事件。" }}</pre>
            </div>
          </div>
        </div>
      </section>
    </section>

    <div v-show="activeTab === 'hybrid'">
      <div class="trace-stats">
        <div class="stat-card">
          <p class="stat-label">检索状态</p>
          <p class="stat-value small" :class="hybridStatus">{{ hybridStatusText }}</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">总耗时</p>
          <p class="stat-value">{{ ran ? lat.total : "—" }}<span v-if="ran" class="stat-unit"> ms</span></p>
        </div>
        <div class="stat-card">
          <p class="stat-label">命中漏斗</p>
          <p class="stat-value small funnel">
            向量 {{ ran ? hits.vector : "—" }} · BM25 {{ ran ? hits.bm25 : "—" }} · Final {{ ran ? hits.final : "—" }}
          </p>
          <p class="stat-sub">召回 → 最终送入 LLM</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">Recall@{{ primaryEvalK }} / MRR@{{ primaryEvalK }}</p>
          <p class="stat-value">{{ recallAt(primaryEvalK) }}<span class="stat-unit"> / {{ mrrAt(primaryEvalK) }}</span></p>
          <p class="stat-sub">基于 GT 标注；未标注时为 —</p>
        </div>
      </div>
      <p v-if="hint && /失败|错误|Error|未配置/i.test(hint)" class="hint">{{ hint }}</p>
      <section class="top-grid">
      <div class="card pad">
        <label>Test Query</label>
        <p class="tiny">模拟 Agent 输入；运行后先经 reason 生成 search_query，再对该词做向量化与混合检索。</p>
        <textarea v-model="query" rows="3" placeholder="例如：帮我查一下那个代号" />
        <div class="hybrid-actions">
          <button class="btn" type="button" @click="save">保存</button>
          <button class="btn" type="button" @click="load">加载</button>
          <button class="btn" type="button" @click="reset">重置</button>
          <button class="btn btn-primary" type="button" :disabled="running" @click="run">
            {{ running ? "检索中…" : "运行" }}
          </button>
        </div>
      </div>
      <div class="card pad gt-card">
        <label id="gt-chunk-label">数据集 / Ground Truth</label>
        <p class="tiny">下拉多选切片编号（Chunk_1…），写入 retrieval_label。</p>
        <ChunkMultiSelect
          v-model="selectedGtChunks"
          :options="datasetChunks"
          :disabled="!datasetChunks.length"
          :hint="gtQueryHint"
          placeholder="选择切片编号…"
          @toggle="toggleGtChunk"
        />
        <p v-if="!datasetChunks.length" class="tiny">暂无切片。请先在文档页上传并等待向量化完成。</p>
        <p v-else class="tiny">共 {{ datasetChunks.length }} 条切片可选。</p>
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
        <div v-if="ran" class="pipe-actions">
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
          <p class="pipe-stat">整次 {{ ran ? lat.total : "—" }}ms<span v-if="ran"> · 改写 {{ lat.plan }}ms</span></p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node vector">
          <h3>Vector Search</h3>
          <p>召回 {{ ran ? vectorRows.length : k }} 条</p>
          <p class="pipe-stat">pgvector<span v-if="ran"> · {{ lat.vector }}ms</span></p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node bm25">
          <h3>BM25 Search</h3>
          <p>召回 {{ ran ? bm25Rows.length : bm25K }} 条</p>
          <p class="pipe-stat">Elasticsearch<span v-if="ran"> · {{ lat.bm25 }}ms</span></p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node rrf">
          <h3>RRF Fusion</h3>
          <p>融合后 {{ ran ? rrfRows.length : n }} 条</p>
          <p class="pipe-stat">应用层<span v-if="ran"> · {{ lat.rrf }}ms</span></p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node rerank">
          <h3>Rerank</h3>
          <p>精排后 {{ ran ? rerankRows.length : m }} 条</p>
          <p class="pipe-stat">{{ rerankModel || "模型见配置" }}<span v-if="ran"> · {{ lat.rerank }}ms</span></p>
        </div>
        <span class="pipe-arrow" aria-hidden="true">→</span>
        <div class="pipe-node final">
          <h3>Final Context</h3>
          <p>送入 LLM {{ ran ? finalRows.length : m }} 条</p>
          <p class="pipe-stat">相关过滤后<span v-if="ran"> · {{ lat.final }}ms</span></p>
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
                <th>Chunk</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in vectorRows" :key="c.chunkId">
                <td>{{ c.vectorRank }}</td>
                <td>{{ c.vectorScore?.toFixed(3) }}</td>
                <td class="chunk-cell"><span class="chunk-code">{{ chunkLabelOf(c.chunkId) }}</span><span class="chunk-content">{{ chunkContentOf(c.chunkId) }}</span></td>
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
                <th>Chunk</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in bm25Rows" :key="c.chunkId">
                <td>{{ c.bm25Rank }}</td>
                <td>{{ c.bm25Score?.toFixed(2) }}</td>
                <td class="chunk-cell"><span class="chunk-code">{{ chunkLabelOf(c.chunkId) }}</span><span class="chunk-content">{{ chunkContentOf(c.chunkId) }}</span></td>
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
                <th>Chunk</th>
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
                <td class="chunk-cell"><span class="chunk-code">{{ chunkLabelOf(c.chunkId) }}</span><span class="chunk-content">{{ chunkContentOf(c.chunkId) }}</span></td>
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
                <th>Chunk</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in rerankRows" :key="c.chunkId">
                <td>{{ c.rerankRank }}</td>
                <td>{{ c.rerankScore?.toFixed(3) }}</td>
                <td class="chunk-cell"><span class="chunk-code">{{ chunkLabelOf(c.chunkId) }}</span><span class="chunk-content">{{ chunkContentOf(c.chunkId) }}</span></td>
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
                  <select :value="gtOf(c.chunkId)" @change="setGt(c.chunkId, Number(($event.target as HTMLSelectElement).value))">
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
        <p class="tiny">只根据 Ground Truth（≥2 视为相关，切片级），不用检索分推断。</p>
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
    </div>
    </div>
  </main>
</template>

<style scoped>
.debug-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0;
  font-size: 12.5px;
  background: transparent;
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.debug-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 1rem 1.25rem 2rem;
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
.top-grid > .card.pad > label {
  margin: 0 0 0.45rem;
  font-size: 0.8rem;
  color: var(--text);
}
.top-grid .btn {
  margin-top: 0.4rem;
  width: 100%;
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
.tiny.sq {
  color: var(--teal);
}
.tiny.warn {
  color: #b45309;
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
.gt-inline {
  margin-top: 0.6rem;
  padding-top: 0.55rem;
  border-top: 1px dashed var(--line);
}
.gt-inline h3 {
  margin: 0 0 0.3rem;
  font-size: 0.8rem;
  color: var(--text);
}
.gt-inline ul {
  margin: 0;
  padding-left: 1.1rem;
}
.gt-inline li {
  font-size: 0.8rem;
}
.gt-inline span {
  margin-left: 0.5rem;
  color: var(--muted);
  font-size: 0.78rem;
}
.chunk-cell {
  max-width: 16rem;
}
.chunk-cell .chunk-code {
  display: block;
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
  color: var(--text);
}
.chunk-cell .chunk-content {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 15rem;
  font-size: 0.72rem;
  color: var(--muted);
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

.trace-wrap {
  margin-bottom: 1rem;
}
.trace-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  margin-bottom: 0.9rem;
}
.stat-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  padding: 0.8rem 1rem;
}
.stat-label {
  margin: 0 0 0.3rem;
  font-size: 0.78rem;
  color: var(--muted);
}
.stat-value {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text);
}
.stat-value.small {
  font-size: 0.95rem;
  line-height: 1.5;
}
.stat-value.running {
  color: var(--teal);
}
.stat-value.error {
  color: var(--danger);
}
.stat-value.done {
  color: #15803d;
}
.stat-unit {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--muted);
}
.stat-sub {
  margin: 0.2rem 0 0;
  font-size: 0.7rem;
  color: var(--muted);
}
.stat-value.funnel {
  font-size: 0.95rem;
}
.trace-panel {
  padding: 1rem 1.15rem;
}
.trace-cols {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.4fr);
  gap: 1.5rem;
}
.trace-sec-title {
  margin: 0 0 0.3rem;
  font-size: 1rem;
  color: var(--text);
}
.trace-left {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.trace-field-label {
  margin: 0.4rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
.trace-left textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.55rem 0.65rem;
  font: inherit;
  font-size: 0.88rem;
  background: #fff;
  color: var(--text);
  resize: vertical;
}
.trace-left textarea:focus-visible,
.trace-kb:focus-visible {
  outline: none;
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
}
.trace-kb {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.45rem 0.5rem;
  font: inherit;
  font-size: 0.85rem;
  background: #fff;
  color: var(--text);
}
.trace-web {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.82rem;
  color: var(--muted);
  cursor: pointer;
}
.trace-scenarios {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-top: 0.3rem;
}
.scenario-tabs {
  display: flex;
  gap: 0.9rem;
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
  margin-bottom: 0.2rem;
}
.scenario-tab {
  border: none;
  background: none;
  padding: 0.4rem 0;
  font: inherit;
  font-size: 0.82rem;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
}
.scenario-tab.on {
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.scenario-card {
  text-align: left;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 10px;
  padding: 0.55rem 0.7rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font: inherit;
}
.scenario-card:hover {
  border-color: var(--teal);
}
.scenario-card strong {
  font-size: 0.82rem;
  color: var(--text);
}
.scenario-card span {
  font-size: 0.75rem;
  color: var(--muted);
}
.trace-run {
  margin-top: 0.5rem;
  align-self: flex-start;
}
.trace-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.trace-right-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.status-badge {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--line);
  color: var(--muted);
}
.status-badge.running {
  color: var(--teal);
  border-color: var(--teal);
}
.status-badge.done {
  color: #15803d;
  border-color: #86efac;
}
.status-badge.error {
  color: var(--danger);
  border-color: var(--danger);
}
.trace-subtabs {
  display: flex;
  gap: 1rem;
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
}
.trace-subtabs button {
  border: none;
  background: none;
  padding: 0.45rem 0;
  font: inherit;
  font-size: 0.85rem;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
}
.trace-subtabs button.on {
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.trace-result-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 0.9rem;
}
.trace-answer-card,
.trace-delay-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.85rem 1rem;
  background: #fff;
  min-height: 12rem;
}
.trace-answer-head,
.trace-delay-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}
.trace-answer-head h3,
.trace-delay-head h3,
.trace-tips h3,
.trace-cites h3 {
  margin: 0;
  font-size: 0.9rem;
  color: var(--text);
}
.trace-answer-text {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.7;
  white-space: pre-wrap;
  color: var(--text);
}
.delay-row {
  margin-bottom: 0.65rem;
}
.delay-label {
  margin: 0 0 0.25rem;
  display: flex;
  justify-content: space-between;
  font-size: 0.78rem;
  color: var(--text);
}
.delay-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--teal-soft);
  overflow: hidden;
}
.delay-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--teal);
}
.trace-tips {
  grid-column: 1 / -1;
  border: 1px dashed var(--line);
  border-radius: 12px;
  padding: 0.75rem 1rem;
}
.trace-tips-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.4rem;
}
.trace-tips p {
  margin: 0.25rem 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--text);
}
.trace-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.debug-tabs {
  display: flex;
  gap: 0.3rem;
  margin-bottom: 0.9rem;
  border-bottom: 1px solid var(--line);
}
.debug-tab {
  border: none;
  background: none;
  padding: 0.5rem 0.9rem;
  font: inherit;
  font-size: 0.85rem;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.debug-tab:hover {
  color: var(--text);
}
.debug-tab.on {
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.hybrid-actions {
  display: flex;
  justify-content: flex-start;
  flex-wrap: nowrap;
  gap: 0.4rem;
  margin: 0.6rem 0 0;
}
.hybrid-actions .btn {
  flex: 1;
  min-width: 0;
  justify-content: center;
  padding-left: 0.4rem;
  padding-right: 0.4rem;
  font-size: 0.75rem;
  white-space: nowrap;
}
.trace-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.trace-step {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #f8fafc;
}
.trace-idx {
  flex-shrink: 0;
  width: 1.4rem;
  height: 1.4rem;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.72rem;
  font-weight: 700;
}
.trace-body {
  min-width: 0;
}
.trace-title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.trace-ms {
  margin-left: 0.4rem;
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--muted);
}
.trace-detail {
  margin: 0.2rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
  word-break: break-all;
}
.trace-tools,
.trace-model,
.trace-json {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.trace-cites {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--line);
}
.trace-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.trace-table th,
.trace-table td {
  text-align: left;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--line);
  color: var(--text);
}
.trace-table th {
  font-size: 0.72rem;
  color: var(--muted);
  font-weight: 500;
}
.trace-json pre {
  margin: 0;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #f8fafc;
  font-size: 0.72rem;
  line-height: 1.5;
  overflow: auto;
  max-height: 26rem;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text);
}
@media (max-width: 900px) {
  .trace-cols,
  .trace-result-grid {
    grid-template-columns: 1fr;
  }
  .trace-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.judge-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.45rem;
}
.judge-pill {
  padding: 0.08rem 0.5rem;
  border-radius: 999px;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 0.68rem;
}
.judge-issues {
  margin: 0.2rem 0 0;
  padding-left: 1.1rem;
  width: 100%;
  color: var(--muted);
  font-size: 0.68rem;
  line-height: 1.5;
}
.judge-err {
  margin-top: 0.3rem;
  color: var(--danger);
}
.trace-answer-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
