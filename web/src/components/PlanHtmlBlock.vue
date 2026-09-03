<script setup lang="ts">
import { ref } from "vue";
import type { PlanHtmlEvent } from "../types/travel";

defineProps<{
  data: PlanHtmlEvent;
}>();

const frameRef = ref<HTMLIFrameElement | null>(null);

function onFrameLoad() {
  try {
    const doc = frameRef.value?.contentDocument;
    if (!doc) return;
    const height = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0);
    if (height > 0 && frameRef.value) {
      frameRef.value.style.height = `${height + 8}px`;
    }
  } catch {
    // ignore
  }
}
</script>

<template>
  <iframe
    v-if="data.html"
    ref="frameRef"
    class="plan-html-frame"
    :srcdoc="data.html"
    title="差旅行程方案"
    @load="onFrameLoad"
  />
  <iframe
    v-else-if="data.url"
    class="plan-html-frame"
    :src="data.url"
    title="差旅行程方案"
  />
</template>

<style scoped>
.plan-html-frame {
  display: block;
  width: 100%;
  min-height: 480px;
  border: none;
  background: transparent;
  border-radius: var(--radius, 12px);
}
</style>
