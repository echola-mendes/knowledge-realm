<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { getMe, type AppUser } from "./api";
import Icon from "./components/Icon.vue";
import { loadKnowledgeBases } from "./kb";
import { debugEnabled } from "./debugFlag";

const route = useRoute();
const me = ref<AppUser | null>(null);
const isLogin = computed(() => route.name === "login");
const initial = computed(() => (me.value?.username?.trim().charAt(0) || "?").toUpperCase());

const allLinks = [
  { to: "/", label: "首页", icon: "home", match: "home" },
  { to: "/chat", label: "对话", icon: "chat", match: "chat" },
  { to: "/search", label: "搜索", icon: "search", match: "search" },
  { to: "/documents", label: "文档", icon: "doc", match: "docs" },
  { to: "/knowledge-bases", label: "知识库管理", icon: "db", match: "kbs" },
  { to: "/debug", label: "调试", icon: "bug", match: "debug" },
  { to: "/settings", label: "设置", icon: "gear", match: "settings" },
] as const;

const links = computed(() => allLinks.filter((item) => item.match !== "debug" || debugEnabled.value));

function navOn(match: string) {
  const p = route.path;
  if (match === "home") return p === "/";
  if (match === "docs") return p === "/documents" || p.startsWith("/documents/");
  if (match === "kbs") return p === "/knowledge-bases";
  if (match === "chat") return p === "/chat";
  if (match === "search") return p === "/search";
  if (match === "debug") return p === "/debug";
  if (match === "settings") return p === "/settings";
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

const navPinned = ref(false);
const navHover = ref(false);
const navOpen = computed(() => navPinned.value || navHover.value);

function collapseNav() {
  navPinned.value = false;
  navHover.value = false;
}

function holdNav() {
  navPinned.value = true;
}

function onNavLeave() {
  navHover.value = false;
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
    <aside
      class="sidenav"
      :class="{ collapsed: !navOpen, pinned: navPinned }"
      @mouseenter="navHover = true"
      @mouseleave="onNavLeave"
      @click="holdNav"
    >
      <header class="sidenav-head">
        <RouterLink class="brand" to="/" aria-label="知域">
          <span class="mark" aria-hidden="true"></span>
          <span class="brand-text">知域</span>
        </RouterLink>
      </header>
      <nav class="nav">
        <RouterLink
          v-for="item in links"
          :key="item.to"
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
    <div class="app-main" @click="collapseNav">
      <RouterView />
      <footer class="footer-note">🔒 检索与问答时，文本片段会发往所配置的第三方 AI。</footer>
    </div>
  </div>
</template>
