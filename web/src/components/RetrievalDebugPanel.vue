<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  putRetrievalLabel,
  runRetrievalDebug,
  type RetrievalDebugResponse,
  type RetrievalDebugRow,
} from "../api";

const props = defineProps<{ query: string }>();

const open = ref(false);
const loading = ref(false);
const error = ref("");
const data = ref<RetrievalDebugResponse | null>(null);
const formulaId = ref<string | null>(null);
const vectorK = ref(5);
const bm25K = ref(5);
const rrfK = ref(5);
const rerankK = ref(5);
const vectorThreshold = ref(0.3);
const rrfConst = ref(60);
const evalK = ref(5);
const GT = ["Not Relevant", "Partial", "Relevant", "Highly Relevant"];

const labels = computed(() => data.value?.labels || {});

watch(
  () => props.query,
  (q) => {
    if (q) run();
  },
);

async function run() {
  if (!props.query.trim()) return;
  loading.value = true;
  error.value = "";
  formulaId.value = null;
  try {
    data.value = await runRetrievalDebug({
      query: props.query,
      vector_k: vectorK.value,
      bm25_k: bm25K.value,
      rrf_k: rrfK.value,
      rerank_k: rerankK.value,
      vector_threshold: vectorThreshold.value,
      rrf_k_const: rrfConst.value,
      eval_k: evalK.value,
    });
  } catch (e) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
}

async function setGt(row: RetrievalDebugRow, relevance: number) {
  if (!data.value) return;
  await putRetrievalLabel({
    query: data.value.query,
    document_id: row.document_id,
    relevance,
  });
  await run();
}

function n(v: number | null | undefined) {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(4) : "—";
}
</script>

<template>
  <aside class="drawer" :class="{ open }">
    <button class="tab" type="button" @click="open = !open">Retrieval Debug</button>
    <div v-if="open" class="body">
      <p v-if="error" class="err">{{ error }}</p>
      <p class="tiny">Query：{{ query || "发送一条 Chat / Agent 问题后在此查看" }}</p>
      <div class="params">
        <label>Vector TopK <input v-model.number="vectorK" type="number" min="1" max="20" /></label>
        <label>Vector 阈值 <input v-model.number="vectorThreshold" type="number" min="0" max="1" step="0.01" /></label>
        <label>BM25 TopK <input v-model.number="bm25K" type="number" min="1" max="20" /></label>
        <label>RRF TopK <input v-model.number="rrfK" type="number" min="1" max="20" /></label>
        <label>Rerank TopK <input v-model.number="rerankK" type="number" min="1" max="20" /></label>
        <label>RRF k <input v-model.number="rrfConst" type="number" min="1" max="1000" /></label>
        <label>Eval K <input v-model.number="evalK" type="number" min="1" max="100" /></label>
      </div>
      <button class="btn btn-primary" type="button" :disabled="loading || !query" @click="run">重新检索</button>
      <template v-if="data">
        <section>
          <h3>Vector Search</h3>
          <p class="tiny">TopK {{ data.vector.requested_k }} · 阈值 {{ data.vector.threshold }} · 返回 {{ data.vector.actual_count }}</p>
          <table>
            <tr><th>#</th><th>Sim</th><th>文档</th></tr>
            <tr v-for="r in data.vector.rows" :key="r.chunk_id">
              <td>{{ r.rank }}</td><td>{{ n(r.score) }}</td><td>{{ r.document_name }}</td>
            </tr>
          </table>
        </section>
        <section>
          <h3>BM25</h3>
          <p class="tiny">TopK {{ data.bm25.requested_k }} · 返回 {{ data.bm25.actual_count }}</p>
          <table>
            <tr><th>#</th><th>BM25</th><th>文档</th></tr>
            <tr v-for="r in data.bm25.rows" :key="r.chunk_id">
              <td>{{ r.rank }}</td><td>{{ n(r.score) }}</td><td>{{ r.document_name }}</td>
            </tr>
          </table>
        </section>
        <section>
          <h3>RRF</h3>
          <p class="tiny">候选 {{ data.rrf.candidate_count }} · TopK {{ data.rrf.requested_k }} · k={{ data.rrf.k_const }}</p>
          <table>
            <tr><th>#</th><th>RRF</th><th>V#</th><th>B#</th><th>文档</th></tr>
            <tr v-for="r in data.rrf.rows" :key="r.chunk_id" @click="formulaId = r.chunk_id">
              <td>{{ r.rank }}</td><td>{{ n(r.rrf_score) }}</td><td>{{ r.vector_rank ?? "—" }}</td><td>{{ r.bm25_rank ?? "—" }}</td><td>{{ r.document_name }}</td>
            </tr>
          </table>
          <p v-if="formulaId" class="tiny">
            {{ data.rrf.rows.find((r) => r.chunk_id === formulaId)?.document_name }}：
            1/({{ data.rrf.k_const }}+V)={{ n(data.rrf.rows.find((r) => r.chunk_id === formulaId)?.rrf_from_vector) }}
            + 1/({{ data.rrf.k_const }}+B)={{ n(data.rrf.rows.find((r) => r.chunk_id === formulaId)?.rrf_from_bm25) }}
          </p>
        </section>
        <section>
          <h3>Rerank</h3>
          <p class="tiny">模型 {{ data.rerank.model }} · TopK {{ data.rerank.requested_k }}</p>
          <table>
            <tr><th>#</th><th>Rerank</th><th>文档</th></tr>
            <tr v-for="r in data.rerank.rows" :key="r.chunk_id">
              <td>{{ r.rank }}</td><td>{{ n(r.rerank_score) }}</td><td>{{ r.document_name }}</td>
            </tr>
          </table>
        </section>
        <section>
          <h3>Candidates</h3>
          <div class="table-wrap">
            <table>
              <tr>
                <th>#</th><th>文档</th><th>V#</th><th>V</th><th>B#</th><th>B</th><th>RRF#</th><th>RRF</th><th>Re#</th><th>Re</th><th>Final</th><th>GT</th>
              </tr>
              <tr v-for="r in data.candidates" :key="r.chunk_id">
                <td>{{ r.rank }}</td>
                <td>{{ r.document_name }}</td>
                <td>{{ r.vector_rank ?? "—" }}</td>
                <td>{{ n(r.vector_score) }}</td>
                <td>{{ r.bm25_rank ?? "—" }}</td>
                <td>{{ n(r.bm25_score) }}</td>
                <td>{{ r.rrf_rank ?? "—" }}</td>
                <td>{{ n(r.rrf_score) }}</td>
                <td>{{ r.rerank_rank ?? "—" }}</td>
                <td>{{ n(r.rerank_score) }}</td>
                <td>{{ r.final ? "Y" : "" }}</td>
                <td>
                  <select :value="labels[r.document_id] ?? 0" @change="setGt(r, Number(($event.target as HTMLSelectElement).value))">
                    <option v-for="(name, i) in GT" :key="i" :value="i">{{ i }} {{ name }}</option>
                  </select>
                </td>
              </tr>
            </table>
          </div>
        </section>
        <section>
          <h3>Evaluation</h3>
          <p class="tiny">K={{ data.evaluation.k }} · GT≥2 文档 {{ data.evaluation.relevant_doc_count }}</p>
          <p>Recall@K {{ data.evaluation.recall == null ? "—" : data.evaluation.recall.toFixed(3) }}</p>
          <p>Precision@K {{ data.evaluation.precision == null ? "—" : data.evaluation.precision.toFixed(3) }}</p>
        </section>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.drawer {
  flex: 0 0 auto;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  min-height: 0;
}
.tab {
  writing-mode: vertical-rl;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--muted);
  font-size: 0.72rem;
  padding: 0.6rem 0.25rem;
  cursor: pointer;
  border-radius: 8px;
}
.body {
  width: 22rem;
  max-height: calc(100vh - 8rem);
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  padding: 0.6rem;
  margin-left: 0.35rem;
}
.tiny { color: var(--muted); font-size: 0.7rem; }
.err { color: var(--danger); }
.params { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem; margin: 0.4rem 0; }
.params label { font-size: 0.68rem; color: var(--muted); display: flex; flex-direction: column; gap: 0.1rem; }
.params input, select { font-size: 0.75rem; padding: 0.15rem 0.25rem; }
h3 { font-size: 0.78rem; margin: 0.7rem 0 0.2rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.68rem; }
th, td { border-bottom: 1px solid var(--line); padding: 0.15rem 0.2rem; text-align: left; }
.table-wrap { overflow-x: auto; }
tr { cursor: pointer; }
</style>
