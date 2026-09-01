<script setup lang="ts">
import { computed } from "vue";
import type { PlanComparison, TravelPlan } from "../types/travel";

const props = defineProps<{ plan: TravelPlan }>();

const rec = computed(() => props.plan.recommendation);
const recLabel = computed(
  () => props.plan.options.find((o) => o.id === rec.value?.option_id)?.label || rec.value?.option_id || "—",
);

function dims(): PlanComparison[] {
  return props.plan.comparison || [];
}

function optionIds(dim: PlanComparison): string[] {
  return (dim.rows || []).map((r) => r.option_id);
}
</script>

<template>
  <div class="card plan-card">
    <h2>行程方案</h2>
    <div v-if="rec" class="plan-rec">
      <span class="rec-label">推荐：{{ recLabel }}</span>
      <span class="rec-reason">{{ rec.reason }}</span>
    </div>
    <p v-if="plan.total_price_summary" class="plan-total">{{ plan.total_price_summary }}</p>

    <table v-if="plan.comparison?.length" class="plan-table">
      <thead>
        <tr>
          <th>维度</th>
          <th v-for="dim in dims()" :key="dim.dimension">
            <template v-for="(id, i) in optionIds(dim)" :key="id">
              {{ plan.options.find((o) => o.id === id)?.label || id }}<template v-if="i < optionIds(dim).length - 1"> / </template>
            </template>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="dim in dims()" :key="dim.dimension">
          <td class="dim">{{ dim.dimension }}</td>
          <td v-for="(r, i) in dim.rows" :key="r.option_id + i">{{ r.value ?? "—" }}</td>
        </tr>
      </tbody>
    </table>

    <div class="plan-options">
      <div v-for="opt in plan.options" :key="opt.id" class="plan-option" :class="{ recommended: opt.id === rec?.option_id }">
        <div class="opt-head">
          <strong>{{ opt.label }}</strong>
          <span class="opt-price">{{ opt.total_price != null ? `¥${opt.total_price}` : "—" }}</span>
        </div>
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
.plan-total {
  font-size: 0.75rem;
  font-weight: 650;
  margin: 0.4rem 0 0.2rem;
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
.opt-notes {
  color: var(--muted);
  margin: 0.2rem 0 0;
}
</style>
