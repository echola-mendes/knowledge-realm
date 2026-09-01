<script setup lang="ts">
defineProps<{ message: string }>();
</script>

<template>
  <div class="card hotel-card">
    <h2>酒店</h2>
    <p class="hotel-hint">{{ message }}</p>
  </div>
</template>

<style scoped>
.hotel-card {
  margin: 0.4rem 0;
  padding: 0.7rem 0.85rem;
}
.hotel-card h2 {
  font-size: 0.78rem;
  margin: 0 0 0.4rem;
}
.hotel-hint {
  font-size: 0.68rem;
  color: var(--muted);
  margin: 0;
}
</style>
