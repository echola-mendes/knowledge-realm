<script setup lang="ts">
import { computed } from "vue";
import { formatPlanPrice, segmentSummary } from "../utils/flightDisplay";
import type { PlanComparison, TravelPlan } from "../types/travel";

const props = defineProps<{ plan: TravelPlan }>();

const rec = computed(() => props.plan.recommendation);
const recOption = computed(() => {
  const id = rec.value?.option_id;
  return props.plan.options.find((o) => o.id === id) || props.plan.options[0];
});
const recLabel = computed(() => recOption.value?.label || rec.value?.option_id || "—");

function dims(): PlanComparison[] {
  return props.plan.comparison || [];
}

const compareOptionIds = computed(() => {
  const opts = props.plan.options || [];
  const first = props.plan.comparison?.[0];
  if (first?.rows?.length === opts.length) {
    const ids = first.rows.map((r) => r.option_id);
    const matched = ids.filter((id) => opts.some((o) => o.id === id)).length;
    if (matched >= Math.max(1, opts.length / 2)) return ids;
  }
  return opts.map((o) => o.id);
});

function optionLabel(id: string, index?: number): string {
  const found = props.plan.options.find((o) => o.id === id);
  if (found) return found.label;
  const opts = props.plan.options || [];
  if (typeof index === "number" && opts[index]) return opts[index].label;
  return id;
}

function dimValue(dim: PlanComparison, id: string): string {
  const row = (dim.rows || []).find((r) => r.option_id === id);
  const value = row?.value;
  return value == null || value === "" ? "—" : String(value);
}
</script>

<template>
  <div class="card plan-card">
    <h2>行程方案</h2>
    <div v-if="rec || recOption" class="plan-rec">
      <span class="rec-label">推荐：{{ recLabel }}</span>
      <span v-if="rec?.reason" class="rec-reason">{{ rec.reason }}</span>
    </div>
    <ul v-if="recOption?.segments?.length" class="plan-segs">
      <li v-for="(seg, i) in recOption.segments" :key="i">{{ segmentSummary(seg) }}</li>
    </ul>
    <p v-if="recOption?.total_price != null && recOption.total_price !== ''" class="plan-total">
      {{ formatPlanPrice(recOption.total_price) }}
      <span v-if="plan.total_price_summary" class="plan-total-note">{{ plan.total_price_summary }}</span>
    </p>
    <p v-else-if="plan.total_price_summary" class="plan-total">{{ plan.total_price_summary }}</p>

    <table v-if="plan.comparison?.length" class="plan-table">
      <thead>
        <tr>
          <th>维度</th>
          <th v-for="(id, i) in compareOptionIds" :key="id">{{ optionLabel(id, i) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="dim in dims()" :key="dim.dimension">
          <td class="dim">{{ dim.dimension }}</td>
          <td v-for="id in compareOptionIds" :key="dim.dimension + id">{{ dimValue(dim, id) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="plan-options">
      <div v-for="opt in plan.options" :key="opt.id" class="plan-option" :class="{ recommended: opt.id === rec?.option_id }">
        <div class="opt-head">
          <strong>{{ opt.label }}</strong>
          <span class="opt-price">{{ formatPlanPrice(opt.total_price) }}</span>
        </div>
        <p v-for="(seg, i) in opt.segments || []" :key="i" class="opt-seg">{{ segmentSummary(seg) }}</p>
        <p v-if="opt.notes" class="opt-notes">{{ opt.notes }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-card {
  margin: 0.4rem 0;
  padding: 0.7rem 0.85rem;
}
.plan-card h2 {
  font-size: 0.78rem;
  margin: 0 0 0.4rem;
}
.plan-rec {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  background: var(--teal-soft);
  border-radius: 8px;
  padding: 0.4rem 0.6rem;
  font-size: 0.72rem;
}
.rec-label {
  font-weight: 650;
  color: var(--teal);
}
.rec-reason {
  color: var(--text);
}
.plan-segs {
  margin: 0.35rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.72rem;
  color: var(--text);
}
.plan-total {
  font-size: 0.75rem;
  font-weight: 650;
  margin: 0.4rem 0 0.2rem;
}
.plan-total-note {
  font-weight: 500;
  color: var(--muted);
  margin-left: 0.4rem;
}
.plan-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
  margin: 0.3rem 0 0.5rem;
}
.plan-table th,
.plan-table td {
  border-bottom: 1px solid var(--line);
  padding: 0.25rem 0.4rem;
  text-align: left;
}
.plan-table th {
  color: var(--muted);
  font-weight: 500;
}
.plan-table .dim {
  color: var(--muted);
  white-space: nowrap;
}
.plan-options {
  display: grid;
  gap: 0.4rem;
}
.plan-option {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.6rem;
  font-size: 0.72rem;
}
.plan-option.recommended {
  border-color: var(--teal);
  background: var(--teal-soft);
}
.opt-head {
  display: flex;
  justify-content: space-between;
}
.opt-price {
  font-weight: 650;
  color: var(--teal);
}
.opt-seg {
  color: var(--text);
  margin: 0.15rem 0 0;
}
.opt-notes {
  color: var(--muted);
  margin: 0.2rem 0 0;
}
</style>
