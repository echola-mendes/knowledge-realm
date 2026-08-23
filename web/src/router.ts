import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import DocumentsView from "./views/DocumentsView.vue";
import SearchView from "./views/SearchView.vue";
import ChatView from "./views/ChatView.vue";
import ReaderView from "./views/ReaderView.vue";
import SettingsView from "./views/SettingsView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/documents", name: "documents", component: DocumentsView },
    { path: "/search", name: "search", component: SearchView },
    { path: "/chat", name: "chat", component: ChatView },
    { path: "/documents/:id", name: "reader", component: ReaderView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
});
