<script setup lang="ts">
import { computed } from "vue";
import { flightLabel, flightPrice, type FlyaiFlightItem, type TravelError } from "../types/travel";

const props = defineProps<{ flights: FlyaiFlightItem[]; error?: TravelError | null }>();

const rows = computed(() =>
  props.flights.slice(0, 6).map((item) => {
    const rec = item as Record<string, unknown>;
    return {
      no: flightLabel(item),
      airline: String(item.airlineName ?? rec.airline ?? rec.depPlanAirlineName ?? "—"),
      dep: String(item.depAirport ?? rec.depAirportName ?? rec.depCity ?? "—"),
      arr: String(item.arrAirport ?? rec.arrAirportName ?? rec.arrCity ?? "—"),
      time: [item.depTime, item.arrTime].filter(Boolean).join(" – ") || "—",
      price: flightPrice(item),
    };
  }),
);
</script>

<template>
  <div class="card travel-card">
    <h2>机票搜索结果</h2>
    <p v-if="error" class="travel-hint">机票搜索失败：{{ error.message }}</p>
    <p v-else-if="!rows.length" class="travel-hint">暂无机票数据</p>
    <table v-else class="travel-table">
      <thead>
        <tr>
          <th>航班</th>
          <th>航司</th>
          <th>出发</th>
          <th>到达</th>
          <th>时间</th>
          <th>价格</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.no + r.dep + r.time">
          <td>{{ r.no }}</td>
          <td>{{ r.airline }}</td>
          <td>{{ r.dep }}</td>
          <td>{{ r.arr }}</td>
          <td>{{ r.time }}</td>
          <td class="price">{{ r.price }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="flights.length > rows.length" class="travel-hint">仅展示前 {{ rows.length }} 条，共 {{ flights.length }} 条</p>
  </div>
</template>

<style scoped>
.travel-card {
  margin: 0.4rem 0;
  padding: 0.7rem 0.85rem;
}
.travel-card h2 {
  font-size: 0.78rem;
  margin: 0 0 0.4rem;
}
.travel-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
.travel-table th {
  text-align: left;
  color: var(--muted);
  font-weight: 500;
  border-bottom: 1px solid var(--line);
  padding: 0.25rem 0.4rem;
}
.travel-table td {
  border-bottom: 1px solid var(--line);
  padding: 0.3rem 0.4rem;
}
.travel-table .price {
  font-weight: 650;
  color: var(--teal);
}
.travel-hint {
  font-size: 0.68rem;
  color: var(--muted);
  margin: 0.2rem 0 0;
}
</style>
