<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import Icon from "../components/Icon.vue";

const route = useRoute();
const tripOpen = ref(true);
const consultOpen = ref(true);
const imageOpen = ref(true);
const moreOpen = ref(true);

watch(
  () => route.path,
  (p) => {
    if (p.startsWith("/tools/trips")) tripOpen.value = true;
    if (p.startsWith("/tools/consult") || p.startsWith("/tools/news")) consultOpen.value = true;
    if (p.startsWith("/tools/image")) imageOpen.value = true;
    if (p.startsWith("/tools/market")) moreOpen.value = true;
  },
  { immediate: true },
);

const onTripsList = computed(() => route.path === "/tools/trips");
const onTripsNew = computed(() => route.path.startsWith("/tools/trips/new"));
const onTrips = computed(() => onTripsList.value || onTripsNew.value);
const onNewsList = computed(() => route.path === "/tools/news");
const onNewsDetail = computed(() => route.name === "tools-news-detail");
const onConsultHistory = computed(() => route.path.startsWith("/tools/consult/history"));
const onConsult = computed(() => onNewsList.value || onNewsDetail.value || onConsultHistory.value);
const onImageDesk = computed(() => route.path === "/tools/image");
const onImageWorks = computed(() => route.path.startsWith("/tools/image/works"));
const onImage = computed(() => onImageDesk.value || onImageWorks.value);
const onMarket = computed(() => route.path.startsWith("/tools/market"));
</script>

<template>
  <main class="page tools-page">
    <aside class="tools-nav" aria-label="工具二级菜单">
      <div class="nav-head">
        <h1 class="nav-title">工具</h1>
        <p class="nav-sub">发现更多 AI 工具，提升效率</p>
      </div>
      <div class="nav-card">
        <div class="nav-group">
          <button
            type="button"
            class="nav-parent"
            :class="{ on: onTrips }"
            :aria-expanded="tripOpen"
            @click="tripOpen = !tripOpen"
          >
            <Icon name="plane" />
            <span>旅程</span>
            <Icon class="chev" name="chevron" />
          </button>
          <div v-show="tripOpen" class="nav-children">
            <RouterLink
              to="/tools/trips"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onTripsList }"
            >
              我的行程单
            </RouterLink>
            <RouterLink
              to="/tools/trips/new"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onTripsNew }"
            >
              创建新行程
            </RouterLink>
          </div>
        </div>
        <div class="nav-group">
          <button
            type="button"
            class="nav-parent"
            :class="{ on: onConsult }"
            :aria-expanded="consultOpen"
            @click="consultOpen = !consultOpen"
          >
            <Icon name="headset" />
            <span>AI资讯</span>
            <Icon class="chev" name="chevron" />
          </button>
          <div v-show="consultOpen" class="nav-children">
            <RouterLink
              to="/tools/news"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onNewsList || onNewsDetail }"
            >
              今日热榜
            </RouterLink>
            <RouterLink
              to="/tools/consult/history"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onConsultHistory }"
            >
              历史记录
            </RouterLink>
          </div>
        </div>
        <div class="nav-group">
          <button
            type="button"
            class="nav-parent"
            :class="{ on: onImage }"
            :aria-expanded="imageOpen"
            @click="imageOpen = !imageOpen"
          >
            <Icon name="image" />
            <span>AI生图</span>
            <Icon class="chev" name="chevron" />
          </button>
          <div v-show="imageOpen" class="nav-children">
            <RouterLink
              to="/tools/image"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onImageDesk }"
            >
              生图台
            </RouterLink>
            <RouterLink
              to="/tools/image/works"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onImageWorks }"
            >
              我的作品
            </RouterLink>
          </div>
        </div>
        <div class="nav-group">
          <button
            type="button"
            class="nav-parent"
            :class="{ on: onMarket }"
            :aria-expanded="moreOpen"
            @click="moreOpen = !moreOpen"
          >
            <Icon name="apps" />
            <span>更多工具</span>
            <Icon class="chev" name="chevron" />
          </button>
          <div v-show="moreOpen" class="nav-children">
            <RouterLink
              to="/tools/market"
              class="nav-child"
              active-class=""
              exact-active-class=""
              :class="{ on: onMarket }"
            >
              工具市场
            </RouterLink>
          </div>
        </div>
      </div>
    </aside>
    <section class="tools-main">
      <RouterView />
    </section>
  </main>
</template>

<style scoped>
.tools-page {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 0.75rem;
  font-size: 12.5px;
  background: transparent;
  display: flex;
  gap: 1rem;
  align-items: stretch;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.tools-nav {
  width: 13.75rem;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.nav-head {
  margin: 0 0.15rem 0.85rem;
  flex-shrink: 0;
}
.nav-title {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.nav-sub {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.nav-card {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 0.45rem 0.4rem;
}
.nav-group + .nav-group {
  margin-top: 0.2rem;
}
.nav-parent {
  width: 100%;
  display: grid;
  grid-template-columns: 1.05rem 1fr 0.75rem;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.nav-parent:hover {
  background: #f8fafc;
}
.nav-parent.on {
  background: #eff6ff;
  color: var(--teal);
}
.nav-parent :deep(.ico) {
  width: 1rem;
  height: 1rem;
}
.nav-parent .chev {
  opacity: 0.55;
  color: #94a3b8;
  justify-self: end;
}
.nav-parent .chev :deep(svg) {
  transform: rotate(-90deg);
}
.nav-parent[aria-expanded="true"] .chev :deep(svg) {
  transform: rotate(0deg);
}
.nav-children {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.12rem 0 0.28rem 1.5rem;
}
.nav-child {
  display: block;
  padding: 0.42rem 0.5rem;
  border-radius: 8px;
  color: #4b5563;
  text-decoration: none;
  font-size: 0.78rem;
  font-weight: 400;
}
.nav-child:hover {
  background: #f8fafc;
  text-decoration: none;
}
.nav-child.on {
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 600;
}
.tools-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tools-main :deep(.placeholder-page) {
  padding: 0;
}
</style>
