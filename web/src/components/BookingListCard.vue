<script setup lang="ts">
import type { BookingItem } from "../types/travel";

const props = defineProps<{ items: BookingItem[] }>();

function kindLabel(kind: string) {
  if (kind === "flight") return "机票";
  if (kind === "hotel") return "酒店";
  return kind;
}
</script>

<template>
  <div class="card booking-card">
    <h2>我的预订</h2>
    <p v-if="!items.length" class="booking-hint">暂无预订记录</p>
    <table v-else class="booking-table">
      <thead>
        <tr>
          <th>类型</th>
          <th>订单</th>
          <th>状态</th>
          <th>支付</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>{{ kindLabel(item.kind) }}</td>
          <td>{{ item.external_id || item.id.slice(0, 8) }}</td>
          <td>{{ item.status }}</td>
          <td>
            <a
              v-if="item.pay_url"
              class="booking-pay"
              :href="item.pay_url"
              target="_blank"
              rel="noopener"
            >
              去支付
            </a>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.booking-card {
  margin: 0.4rem 0;
  padding: 0.7rem 0.85rem;
}
.booking-card h2 {
  font-size: 0.78rem;
  margin: 0 0 0.4rem;
}
.booking-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
.booking-table th {
  text-align: left;
  color: var(--muted);
  font-weight: 500;
  border-bottom: 1px solid var(--line);
  padding: 0.25rem 0.4rem;
}
.booking-table td {
  border-bottom: 1px solid var(--line);
  padding: 0.3rem 0.4rem;
}
.booking-pay {
  color: var(--teal);
  text-decoration: none;
}
.booking-pay:hover {
  text-decoration: underline;
}
.booking-hint {
  font-size: 0.68rem;
  color: var(--muted);
  margin: 0;
}
</style>
