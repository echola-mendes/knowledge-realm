<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";

const reviewWrong = ref(false);
const stem = ref("题目……");
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1>今日挑战</h1>
        <p class="sub">默认 10 道 · 当前仅为界面草稿</p>
      </div>
      <RouterLink to="/">返回首页</RouterLink>
    </div>

    <section class="card session">
      <label class="switch">
        <input v-model="reviewWrong" type="checkbox" />
        复习错题
      </label>
      <p class="q">{{ stem }}</p>
    </section>
  </main>
</template>

<style scoped>
.session {
  padding: 1.6rem 1.5rem 1.2rem;
}
.switch {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.95rem;
  cursor: pointer;
}
.switch input {
  margin: 0;
  accent-color: var(--teal);
}
.q {
  margin: 1rem 0 0;
  font-size: 1.05rem;
  line-height: 1.5;
  text-align: left;
}
</style>
