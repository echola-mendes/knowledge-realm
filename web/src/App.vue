<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { getMe, type AppUser } from "./api";
import Icon from "./components/Icon.vue";
import SideNavItem from "./components/SideNavItem.vue";
import { loadKnowledgeBases } from "./kb";
import { debugEnabled } from "./debugFlag";
import { navTree, type NavNode } from "./navConfig";

const route = useRoute();
const me = ref<AppUser | null>(null);
const isLogin = computed(() => route.name === "login");
const initial = computed(() => (me.value?.username?.trim().charAt(0) || "?").toUpperCase());

const links = computed<NavNode[]>(() =>
  navTree.value.filter((n) => n.enabled && !(n.id === "debug" && !debugEnabled.value)),
);

function loadShell() {
  loadKnowledgeBases().catch(() => undefined);
  getMe()
    .then((row) => {
      me.value = row;
    })
    .catch(() => {
      me.value = null;
    });
}

onMounted(() => {
  if (!isLogin.value) loadShell();
});

watch(isLogin, (login) => {
  if (!login) loadShell();
});
</script>

<template>
  <div v-if="isLogin" class="login-shell">
    <RouterView />
  </div>
  <div v-else class="app-shell">
    <aside class="sidenav collapsed">
      <header class="sidenav-head">
        <RouterLink class="brand" to="/" aria-label="知域">
          <span class="mark" aria-hidden="true"></span>
          <span class="brand-text">知域</span>
        </RouterLink>
      </header>
      <nav class="nav">
        <SideNavItem v-for="item in links" :key="item.id" :node="item" :depth="0" />
      </nav>
      <div class="sidenav-foot">
        <button class="theme-btn" type="button" aria-label="主题">
          <Icon name="sun" />
        </button>
        <RouterLink
          v-if="me"
          class="who"
          to="/settings"
          :title="`${me.username} · 设置`"
          :aria-label="`当前用户 ${me.username}，进入设置`"
        >
          <span class="avatar" aria-hidden="true">{{ initial }}</span>
          <span class="who-name">{{ me.username }}</span>
        </RouterLink>
      </div>
    </aside>
    <div class="app-main">
      <RouterView />
      <footer class="footer-note">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</footer>
    </div>
  </div>
</template>
