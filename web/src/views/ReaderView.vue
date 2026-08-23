<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <h1>阅读</h1>
  <p>文档 {{ route.params.id }}</p>
</template>
