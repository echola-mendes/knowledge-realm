<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getHealth } from "../api";

const configured = ref<boolean | null>(null);

onMounted(async () => {
  const h = await getHealth();
  configured.value = h.ai_configured;
});
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <h1>设置</h1>
        <p class="sub">本机 · 无需登录 · 数据仅保存在当前设备</p>
      </div>
    </div>

    <section class="card item">
      <h2>AI 密钥 <span v-if="configured === true" class="tag">已配置</span><span v-else-if="configured === false" class="tag off">未配置</span></h2>
      <p>密钥已在本机 `.env` 保存，仅用于调用你配置的第三方 AI。本页只展示配置状态，不显示或修改密钥内容。</p>
    </section>

    <section class="card item">
      <h2>隐私说明</h2>
      <p class="banner">检索与问答时，文本片段会发往所配置的第三方 AI。</p>
      <p>文档、索引与对话记录默认保存在本机，原件不会作为整库上传到云端。</p>
    </section>

    <section class="card item">
      <h2>数据与本机</h2>
      <p>知识库与索引存储于本机 PostgreSQL + 本地文件目录。</p>
    </section>
  </main>
</template>

<style scoped>
.item {
  padding: 1.15rem 1.25rem;
  margin-bottom: 1rem;
}
.item h2 {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
}
.item p {
  margin: 0;
  color: #4b5563;
  line-height: 1.6;
}
.tag {
  margin-left: 0.4rem;
  font-size: 0.75rem;
  background: var(--teal-soft);
  color: var(--teal);
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
  font-weight: 500;
}
.tag.off {
  background: #eee;
  color: #666;
}
.banner {
  background: var(--teal-soft);
  color: var(--teal) !important;
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  margin-bottom: 0.7rem !important;
}
</style>
