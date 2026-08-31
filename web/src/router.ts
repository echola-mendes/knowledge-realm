import { createRouter, createWebHistory } from "vue-router";
import { getMe } from "./api";
import { debugEnabled } from "./debugFlag";
import HomeView from "./views/HomeView.vue";
import DocumentChunksView from "./views/DocumentChunksView.vue";
import DocumentsView from "./views/DocumentsView.vue";
import SearchView from "./views/SearchView.vue";
import ChatView from "./views/ChatView.vue";
import ReaderView from "./views/ReaderView.vue";
import SettingsView from "./views/SettingsView.vue";
import ChallengeView from "./views/ChallengeView.vue";
import DebugView from "./views/DebugView.vue";
import InsightsView from "./views/InsightsView.vue";
import LoginView from "./views/LoginView.vue";
import KnowledgeBasesView from "./views/KnowledgeBasesView.vue";
import KnowledgeGraphView from "./views/KnowledgeGraphView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView, meta: { public: true } },
    { path: "/", name: "home", component: HomeView },
    { path: "/documents", name: "documents", component: DocumentsView },
    { path: "/documents/:id/chunks", name: "document-chunks", component: DocumentChunksView },
    { path: "/knowledge-bases", name: "kbs", component: KnowledgeBasesView },
    { path: "/search", name: "search", component: SearchView },
    { path: "/chat", name: "chat", component: ChatView },
    { path: "/debug", name: "debug", component: DebugView },
    { path: "/insights", name: "insights", component: InsightsView },
    { path: "/documents/:id", name: "reader", component: ReaderView },
    { path: "/settings", name: "settings", component: SettingsView },
    { path: "/challenge", name: "challenge", component: ChallengeView },
    { path: "/knowledge-graph", name: "knowledge-graph", component: KnowledgeGraphView },
  ],
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  try {
    await getMe();
  } catch {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "debug" && !debugEnabled.value) {
    return { name: "settings" };
  }
  return true;
});
