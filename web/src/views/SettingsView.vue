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
  <h1>设置</h1>
  <p>本机绑定，无登录。密钥只放在服务器 `.env`，此处不回显。</p>
  <p v-if="configured === true">AI 密钥：已配置</p>
  <p v-else-if="configured === false">AI 密钥：未配置</p>
</template>
