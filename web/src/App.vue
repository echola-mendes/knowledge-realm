<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <div class="shell">
    <header>
      <strong>知域</strong>
      <nav>
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/documents">文档</RouterLink>
        <RouterLink to="/search">搜索</RouterLink>
        <RouterLink to="/chat">对话</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: sans-serif;
  color: #222;
}
.shell header {
  display: flex;
  gap: 1.5rem;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #ddd;
}
nav {
  display: flex;
  gap: 1rem;
}
a {
  color: #245;
}
main {
  padding: 1rem;
}
</style>
