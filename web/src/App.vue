<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { getMe, type AppUser } from "./api";
import Icon from "./components/Icon.vue";
import { loadKnowledgeBases } from "./kb";
import { debugEnabled } from "./debugFlag";
import { NAV_ITEMS, navConfig, type NavItemDef } from "./navConfig";

const route = useRoute();
const me = ref<AppUser | null>(null);
const isLogin = computed(() => route.name === "login");
const initial = computed(() => (me.value?.username?.trim().charAt(0) || "?").toUpperCase());

const links = computed<NavItemDef[]>(() => {
  const { order, labels } = navConfig.value;
  const byMatch = new Map(NAV_ITEMS.map((item) => [item.match, item]));
  const list: NavItemDef[] = [];
  for (const match of order) {
    const item = byMatch.get(match);
    if (!item) continue;
    if (item.match === "debug" && !debugEnabled.value) continue;
    list.push({ ...item, label: labels[item.match] ?? item.label });
  }
  return list;
});

function navOn(match: string) {
  const p = route.path;
  const qMode = typeof route.query.mode === "string" ? route.query.mode : "";
  if (match === "home") return p === "/";
  if (match === "chat") return p === "/chat" && qMode !== "report";
  if (match === "kbs") return p === "/knowledge-bases";
  if (match === "docs") return p === "/documents" || p.startsWith("/documents/");
  if (match === "search") return p === "/search";
  if (match === "debug") return p === "/debug";
  if (match === "settings") return p === "/settings";
  if (match === "knowledge-graph") return p === "/knowledge-graph";
  if (match === "insights") return p === "/insights";
  if (match === "tools") return p === "/tools" || p.startsWith("/tools/");
  if (match === "monitoring") return p === "/monitoring";
  if (match === "basics") return p === "/basics" || p.startsWith("/basics/");
  return false;
}

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
        <RouterLink
          v-for="item in links"
          :key="item.match"
          :to="item.to"
          active-class=""
          exact-active-class=""
          :class="{ on: navOn(item.match) }"
        >
          <Icon :name="item.icon" />
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
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
