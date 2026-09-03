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
import ToolsLayout from "./views/ToolsLayout.vue";
import MyTripsView from "./views/MyTripsView.vue";
import ToolPlaceholderView from "./views/ToolPlaceholderView.vue";
import BasicsLayout from "./views/BasicsLayout.vue";
import MenuManageView from "./views/MenuManageView.vue";

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
    {
      path: "/tools",
      component: ToolsLayout,
      children: [
        { path: "", redirect: { name: "tools-trips" } },
        { path: "trips", name: "tools-trips", component: MyTripsView },
        {
          path: "trips/new",
          name: "tools-trips-new",
          component: ToolPlaceholderView,
          meta: { title: "创建新行程", sub: "在 Multi Agent 对话中描述出行需求，生成方案后会进入我的行程单。" },
        },
        {
          path: "consult",
          name: "tools-consult",
          component: ToolPlaceholderView,
          meta: { title: "资讯中心", sub: "智能资讯入口占位，能力后续接入。" },
        },
        {
          path: "consult/history",
          name: "tools-consult-history",
          component: ToolPlaceholderView,
          meta: { title: "历史记录", sub: "资讯会话历史占位，能力后续接入。" },
        },
        {
          path: "image",
          name: "tools-image",
          component: ToolPlaceholderView,
          meta: { title: "生图台", sub: "文生图入口占位，能力后续接入。" },
        },
        {
          path: "image/works",
          name: "tools-image-works",
          component: ToolPlaceholderView,
          meta: { title: "我的作品", sub: "生图作品列表占位，能力后续接入。" },
        },
        {
          path: "market",
          name: "tools-market",
          component: ToolPlaceholderView,
          meta: { title: "工具市场", sub: "更多 AI 工具入口占位，能力后续接入。" },
        },
      ],
    },
    { path: "/documents/:id", name: "reader", component: ReaderView },
    { path: "/settings", name: "settings", component: SettingsView },
    {
      path: "/monitoring",
      name: "monitoring",
      component: ToolPlaceholderView,
      meta: { title: "监控", sub: "系统运行监控入口占位，能力后续接入。" },
    },
    {
      path: "/basics",
      component: BasicsLayout,
      children: [
        { path: "", redirect: { name: "basics-menus" } },
        { path: "menus", name: "basics-menus", component: MenuManageView },
      ],
    },
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
