<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  getMe,
  listConversations,
  listMessages,
  messageFromErrorBody,
  renameConversation,
  type ChatMessage,
  type Citation,
  type Conversation,
} from "../api";
import Icon from "../components/Icon.vue";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt({ breaks: true });

const vFocus = { mounted: (el: HTMLInputElement) => el.focus() };

const route = useRoute();
const router = useRouter();
const draft = ref(typeof route.query.q === "string" ? route.query.q : "");
const messages = ref<ChatMessage[]>([]);
const conversationId = ref<string>(typeof route.query.c === "string" ? route.query.c : "");
const conversations = ref<Conversation[]>([]);
const error = ref("");
const streaming = ref(false);
const mode = ref<"chat" | "agent" | "report">(
  route.query.mode === "report" ? "report" : route.query.mode === "agent" ? "agent" : "chat",
);
const smartSearch = ref(false);
const CHAT_KEY = "zhiyu-chat-id";
const userInitial = computed(() => (username.value.trim().charAt(0) || "U").toUpperCase());
const mdContent = (text: string) => md.render(text.replace(/^\s+/, ""));

function syncRouteQuery() {
  const query: Record<string, string> = {};
  if (conversationId.value) query.c = conversationId.value;
  if (mode.value === "report") query.mode = "report";
  else if (mode.value === "agent") query.mode = "agent";
  router.replace({ path: "/chat", query });
}

function rememberConversation(id: string) {
  conversationId.value = id;
  if (id) localStorage.setItem(CHAT_KEY, id);
  else localStorage.removeItem(CHAT_KEY);
  syncRouteQuery();
}
const username = ref("");
const greeting = computed(
  () =>
    `您好${username.value ? `，${username.value}` : ""}。我是知域助手，可以帮您查已开启知识库里的资料，也可以直接问答。请问需要什么帮助？`,
);
const greetingMsg = computed<ChatMessage>(() => ({
  id: "greet",
  role: "assistant",
  content: greeting.value,
}));
const threadMessages = computed(() => (messages.value.length ? messages.value : [greetingMsg.value]));
const sidebarOpen = ref(true);
const listSearch = ref("");
const listAction = ref<"new" | "search">("new");

function toggleListAction(action: "search" | "new") {
  listAction.value = listAction.value === action && action === "search" ? "new" : action;
}

function openSidebar(action: "new" | "search" = "new") {
  sidebarOpen.value = true;
  listAction.value = action;
}

const listSearchInput = ref<HTMLInputElement | null>(null);
watch(listAction, (action) => {
  if (action === "search") nextTick(() => listSearchInput.value?.focus());
});
const box = ref<HTMLElement | null>(null);
const activeDoc = ref<string>("");
const showAllSources = ref(false);

type DocCite = {
  document_id: string;
  document_name: string;
  score: number;
  chunks: Citation[];
};

function groupCitesByDoc(rows: Citation[]): DocCite[] {
  const map = new Map<string, DocCite>();
  for (const c of rows) {
    const cur = map.get(c.document_id);
    if (!cur) {
      map.set(c.document_id, {
        document_id: c.document_id,
        document_name: c.document_name,
        score: typeof c.score === "number" ? c.score : 0,
        chunks: [c],
      });
      continue;
    }
    cur.chunks.push(c);
    if (typeof c.score === "number" && c.score > cur.score) cur.score = c.score;
  }
  return [...map.values()];
}

const chatTitle = computed(() => {
  const row = conversations.value.find((c) => c.id === conversationId.value);
  return row?.title || (messages.value.length ? "对话" : "新对话");
});

const editingTitle = ref(false);
const titleDraft = ref("");

function startEditTitle() {
  if (!conversationId.value) return;
  titleDraft.value = chatTitle.value;
  editingTitle.value = true;
}
async function saveTitle() {
  const id = conversationId.value;
  editingTitle.value = false;
  const title = titleDraft.value.trim();
  if (!id || !title || title === chatTitle.value) return;
  try {
    const updated = await renameConversation(id, title);
    const row = conversations.value.find((c) => c.id === id);
    if (row) row.title = updated.title;
  } catch (e) {
    error.value = messageFromErrorBody(String(e), "标题保存失败");
  }
}

function convBucket(iso?: string | null) {
  if (!iso) return "更早";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "更早";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d >= today) return "今天";
  if (d >= yesterday) return "昨天";
  return "更早";
}

function formatConvTime(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

const conversationGroups = computed(() => {
  const q = listSearch.value.trim().toLowerCase();
  const rows = q
    ? conversations.value.filter((c) => c.title.toLowerCase().includes(q))
    : conversations.value;
  const labels = ["今天", "昨天", "更早"] as const;
  const buckets: Record<(typeof labels)[number], Conversation[]> = { 今天: [], 昨天: [], 更早: [] };
  for (const c of rows) buckets[convBucket(c.updated_at)].push(c);
  return labels.filter((label) => buckets[label].length).map((label) => ({ label, items: buckets[label] }));
});

const panelDocs = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i];
    if (m.role === "assistant" && m.citations?.length) return groupCitesByDoc(m.citations);
  }
  return [] as DocCite[];
});

const citeStats = computed(() => {
  const rows = panelDocs.value;
  if (!rows.length) return [] as Array<DocCite & { pct: number; color: string; start: number; end: number }>;
  const weights = rows.map((c) => Math.max(c.score || 0.01, 0.01));
  const total = weights.reduce((s, w) => s + w, 0);
  const colors = ["#2563eb", "#60a5fa", "#93c5fd", "#cbd5e1"];
  let acc = 0;
  return rows.map((c, i) => {
    const pct = (weights[i] / total) * 100;
    const start = acc;
    acc += pct;
    return { ...c, pct: Math.round(pct), color: colors[i % colors.length], start, end: acc };
  });
});

const donutStyle = computed(() => {
  if (!citeStats.value.length) return { background: "#e2e8f0" };
  const parts = citeStats.value.map((s) => `${s.color} ${s.start}% ${s.end}%`);
  return { background: `conic-gradient(${parts.join(", ")})` };
});

const sourceList = computed(() => (showAllSources.value ? panelDocs.value : panelDocs.value.slice(0, 3)));

const shownDoc = computed(() => {
  const rows = panelDocs.value;
  if (!rows.length) return null;
  return rows.find((c) => c.document_id === activeDoc.value) || rows[0];
});

async function refreshConversations() {
  conversations.value = await listConversations();
}

async function openConversation(id: string) {
  if (streaming.value) return;
  rememberConversation(id);
  try {
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
}
const CITE_LIMIT = 2;
const citeOpen = ref<Record<string, boolean>>({});

function docCites(m: ChatMessage) {
  return groupCitesByDoc(m.citations || []);
}

function visibleDocs(m: ChatMessage) {
  const rows = docCites(m);
  if (citeOpen.value[m.id] || rows.length <= CITE_LIMIT) return rows;
  return rows.slice(0, CITE_LIMIT);
}

function isThinking(m: ChatMessage) {
  const last = messages.value[messages.value.length - 1];
  return m.role === "assistant" && !m.content.trim() && streaming.value && last === m;
}

function citePreview(content: string, limit = 72) {
  const text = content.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function chunksPath(documentId: string) {
  return `/documents/${documentId}/chunks`;
}

function scrollBottom() {
  nextTick(() => {
    box.value?.scrollTo({ top: box.value.scrollHeight });
  });
}

async function loadHistory() {
  if (!conversationId.value) return;
  const rows = await listMessages(conversationId.value);
  messages.value = rows;
  scrollBottom();
}

async function ask() {
  const q = draft.value.trim();
  if (!q || streaming.value) return;
  error.value = "";
  messages.value.push({ id: "u-" + Date.now(), role: "user", content: q });
  const assistant: ChatMessage = { id: "a-" + Date.now(), role: "assistant", content: "" };
  messages.value.push(assistant);
  draft.value = "";
  streaming.value = true;
  scrollBottom();
  const useGraph = mode.value !== "chat";
  try {
    const res = await fetch(useGraph ? "/api/agent/stream" : "/api/chat/stream", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        useGraph
          ? {
              task: mode.value === "report" ? "report" : "agent",
              query: q,
              conversation_id: conversationId.value || undefined,
              allow_web: smartSearch.value,
            }
          : {
              query: q,
              conversation_id: conversationId.value || undefined,
            },
      ),
    });
    if (!res.ok || !res.body) throw new Error(messageFromErrorBody(await res.text(), res.statusText));
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6)) as {
          type: string;
          text?: string;
          answer?: string;
          conversation_id?: string;
          citations?: Citation[];
        };
        if (payload.type === "token" && payload.text) assistant.content += payload.text;
        if (payload.type === "citations") {
          const cid = payload.conversation_id || conversationId.value;
          if (cid) rememberConversation(cid);
          assistant.citations = payload.citations || [];
          if (payload.answer) assistant.content = payload.answer;
        }
        scrollBottom();
      }
    }
    await refreshConversations();
  } catch (e) {
    error.value = String(e);
  } finally {
    streaming.value = false;
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
}

function newChat() {
  rememberConversation("");
  messages.value = [];
  draft.value = "";
  error.value = "";
}

onMounted(async () => {
  if (!conversationId.value) {
    conversationId.value = localStorage.getItem(CHAT_KEY) || "";
  }
  try {
    const me = await getMe();
    username.value = me.username;
    await refreshConversations();
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
  if (draft.value) ask();
});

watch(panelDocs, (rows) => {
  activeDoc.value = rows[0]?.document_id || "";
  showAllSources.value = false;
});

watch(
  () => route.query.mode,
  (m) => {
    if (m === "report") mode.value = "report";
    else if (m === "agent") mode.value = "agent";
    else if (route.path === "/chat") mode.value = "chat";
  },
);

function setMode(next: "chat" | "agent" | "report") {
  if (streaming.value) return;
  mode.value = next;
  syncRouteQuery();
}

function pickDoc(id: string) {
  activeDoc.value = id;
}
</script>

<template>
  <main class="chat-page">
    <div class="chat-canvas card">
      <aside v-if="sidebarOpen" class="chat-list">
        <header class="list-head">
          <div class="list-head-row">
            <h2>对话</h2>
            <div class="list-tools">
              <button
                class="list-tool-btn"
                type="button"
                title="收起"
                @click="sidebarOpen = false"
              >
                <Icon name="panel-close" />
              </button>
              <button
                class="list-tool-btn"
                :class="{ on: listAction === 'search' }"
                type="button"
                title="搜索对话"
                @click="toggleListAction('search')"
              >                <Icon name="search" />
              </button>
              <button
                class="list-tool-btn"
                type="button"
                title="新建对话"
                @click="toggleListAction('new')"
              >
                <Icon name="plus" />
              </button>
            </div>
          </div>
          <p class="sub">智能问答与任务协作</p>
        </header>
        <div class="new-chat-row">
          <button
            v-if="listAction === 'new'"
            class="btn btn-primary new-chat"
            type="button"
            @click="newChat"
          >
            <Icon name="plus" />
            新建对话
          </button>
          <label v-else class="list-search">
            <Icon name="search" />
            <input ref="listSearchInput" v-model="listSearch" type="search" placeholder="搜索对话" />
          </label>
        </div>
        <div class="list-scroll">
          <section v-for="group in conversationGroups" :key="group.label" class="list-group">
            <h3>{{ group.label }}</h3>
            <button
              v-for="c in group.items"
              :key="c.id"
              type="button"
              class="list-item"
              :class="{ on: c.id === conversationId }"
              @click="openConversation(c.id)"
            >
              <Icon name="session" class="list-icon" />
              <span class="list-title">{{ c.title }}</span>
              <span class="list-time">{{ formatConvTime(c.updated_at) }}</span>
            </button>
          </section>
          <p v-if="!conversations.length" class="list-empty">暂无对话</p>
          <p v-else-if="!conversationGroups.length" class="list-empty">无匹配对话</p>
        </div>
      </aside>
      <div v-else class="list-rail">
        <button class="list-tool-btn" type="button" title="展开对话列表" @click="openSidebar()">
          <Icon name="panel-open" />
        </button>
        <button class="list-tool-btn" type="button" title="搜索对话" @click="openSidebar('search')">
          <Icon name="search" />
        </button>
        <button class="list-tool-btn" type="button" title="新建对话" @click="openSidebar('new')">
          <Icon name="plus" />
        </button>
      </div>

      <div class="chat-column">
        <header class="chat-head">
          <div class="chat-head-top">
            <div class="title-row">
              <h1 v-if="!editingTitle">{{ chatTitle }}</h1>
              <input
                v-else
                v-model="titleDraft"
                class="title-input"
                v-focus
                @keyup.enter="saveTitle"
                @keyup.esc="editingTitle = false"
                @blur="saveTitle"
              />
              <button
                class="icon-btn"
                type="button"
                aria-label="编辑标题"
                :disabled="!conversationId"
                title="编辑标题"
                @click="startEditTitle"
              >
                <Icon name="edit" />
              </button>
            </div>
          </div>
          <div class="chat-head-sub">
            <p class="sub">默认检索全部已开启的知识库，回答会标注引用来源</p>
            <div class="head-tools">
              <div class="mode-switch" role="group" aria-label="Question mode">
                <button type="button" :class="{ on: mode === 'chat' }" :disabled="streaming" @click="setMode('chat')">Chat</button>
                <button type="button" :class="{ on: mode === 'agent' }" :disabled="streaming" @click="setMode('agent')">Agent</button>
                <button type="button" :class="{ on: mode === 'report' }" :disabled="streaming" @click="setMode('report')">Report</button>
              </div>
              <button class="icon-btn" type="button" aria-label="分享">
                <Icon name="share" />
              </button>
              <button class="icon-btn" type="button" aria-label="收藏">
                <Icon name="star" />
              </button>
              <button class="icon-btn" type="button" aria-label="更多">
                <Icon name="more" />
              </button>
            </div>
          </div>
        </header>

        <p v-if="error" class="hint err">{{ error }}</p>

        <div ref="box" class="thread">
          <div v-for="m in threadMessages" :key="m.id" :class="['msg', m.role]">
            <div v-if="m.role === 'user'" class="avatar user-avatar">{{ userInitial }}</div>
            <div v-else class="avatar bot-avatar"><Icon name="brand" /></div>
            <div class="bubble-wrap">
              <div class="msg-meta">
                <span class="msg-who">{{ m.role === "user" ? "你" : "知识助手" }}</span>
              </div>
              <div class="bubble">
                <div v-if="isThinking(m)" class="thinking">
                  <span class="spin" aria-hidden="true"></span>
                  思考中……
                </div>
                <div v-else-if="m.role === 'assistant'" class="md-body" v-html="mdContent(m.content)"></div>
                <pre v-else>{{ m.content.replace(/^\s+/, "") }}</pre>
                <div v-if="m.role === 'assistant' && m.citations?.length" class="cites">
                  <p class="cites-label">引用来源 ({{ docCites(m).length }})</p>
                  <button
                    v-for="d in visibleDocs(m)"
                    :key="d.document_id"
                    type="button"
                    class="cite-chip"
                    :class="{ on: d.document_id === shownDoc?.document_id }"
                    @click="pickDoc(d.document_id)"
                  >
                    <span class="cite-name">{{ d.document_name }}</span>
                  </button>
                  <button
                    v-if="docCites(m).length > CITE_LIMIT && !citeOpen[m.id]"
                    type="button"
                    class="cite-more"
                    @click="citeOpen[m.id] = true"
                  >
                    展开全部
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="composer-wrap">
          <div class="composer card">
            <textarea
              v-model="draft"
              rows="2"
              :placeholder="
                mode === 'report'
                  ? '按主题生成研究报告…'
                  : mode === 'agent'
                    ? 'Agent 可多步检索后再回答…'
                    : '继续追问，或输入新问题...'
              "
              @keydown="onKey"
            ></textarea>
            <div class="composer-bar">
              <div class="composer-left">
                <button class="tool-btn" type="button" title="附件（暂未开放）" disabled>
                  <Icon name="paperclip" />
                </button>
                <button class="tool-btn" type="button" title="图片（暂未开放）" disabled>
                  <Icon name="image" />
                </button>
                <button class="tool-btn tools-btn" type="button" title="工具（暂未开放）" disabled>
                  <Icon name="tools" />
                  <span>工具</span>
                  <i class="chev"></i>
                </button>
              </div>
              <div class="composer-right">
                <span class="composer-hint">Enter 发送，Shift+Enter 换行</span>
                <button class="btn btn-primary send-btn" type="button" :disabled="streaming" @click="ask">
                  <Icon name="send" />
                </button>
              </div>
            </div>
          </div>
          <button
            class="smart-toggle"
            :class="{ on: smartSearch }"
            type="button"
            :disabled="streaming"
            @click="smartSearch = !smartSearch"
          >
            <Icon name="spark" />
            智能搜索
          </button>
        </div>
      </div>

      <aside v-if="panelDocs.length" class="source-side">
        <header class="source-head">
          <h2>资料来源</h2>
        </header>
        <section class="source-overview">
          <h3>来源概览</h3>
          <div class="donut-row">
            <div class="donut" :style="donutStyle">
              <div class="donut-hole">
                <strong>{{ panelDocs.length }}</strong>
                <span>文档</span>
              </div>
            </div>
            <ul class="donut-legend">
              <li v-for="s in citeStats" :key="s.document_id">
                <span class="dot" :style="{ background: s.color }"></span>
                {{ s.document_name }} · {{ s.pct }}%
              </li>
            </ul>
          </div>
        </section>
        <section class="source-all">
          <h3>所有来源</h3>
          <article
            v-for="d in sourceList"
            :key="d.document_id"
            class="source-card"
            :class="{ on: d.document_id === activeDoc }"
            @click="pickDoc(d.document_id)"
          >
            <div class="source-card-top">
              <RouterLink class="source-doc" :to="chunksPath(d.document_id)" @click.stop>
                {{ d.document_name }}
              </RouterLink>
              <span class="source-meta">{{ d.chunks.length }} 段</span>
            </div>
            <div v-for="(c, i) in d.chunks" :key="c.chunk_id" class="source-chunk">
              <p class="source-snippet">{{ citePreview(c.content, 120) }}</p>
              <RouterLink class="source-chunk-link" :to="chunksPath(d.document_id)" @click.stop>
                相关切片 {{ i + 1 }}
              </RouterLink>
            </div>
          </article>
          <button
            v-if="panelDocs.length > 3 && !showAllSources"
            class="btn source-more"
            type="button"
            @click="showAllSources = true"
          >
            查看全部来源
          </button>
        </section>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0.75rem 0.75rem 0.75rem 1rem;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  font-size: 12.5px;
  background: var(--bg);
}
.chat-canvas {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  overflow: hidden;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.chat-list {
  width: 15.5rem;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: none;
  border-right: 1px solid var(--line);
  border-radius: 0;
  box-shadow: none;
  background: transparent;
}
.list-head {
  padding: 1.15rem 0.85rem 0.35rem;
}
.list-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
}
.list-head-row h2 {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
  font-weight: 700;
}
.list-head .sub {
  margin: 0.25rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
.list-tools {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.list-tool-btn {
  flex-shrink: 0;
  border: 1px solid transparent;
  background: none;
  border-radius: 8px;
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--muted);
}
.list-tool-btn:hover {
  background: #f1f5f9;
}
.list-tool-btn.on {
  background: #eff6ff;
  color: var(--teal);
  border-color: var(--line);
}
.list-tool-btn :deep(.ico) {
  width: 15px;
  height: 15px;
}
.new-chat-row {
  display: flex;
  align-items: stretch;
  gap: 0.35rem;
  margin: 0 0.75rem 0.55rem;
  height: 1.85rem;
}
.new-chat {
  flex: 1;
  min-width: 0;
  justify-content: center;
  gap: 0.35rem;
  padding-top: 0;
  padding-bottom: 0;
}
.new-chat :deep(.ico) {
  width: 14px;
  height: 14px;
}
.list-search {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex: 1;
  min-width: 0;
  padding: 0 0.55rem;
  border: 1px solid #2563eb;
  border-radius: 8px;
  background: #f8fafc;
  color: var(--muted);
}
.list-search :deep(.ico) {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.list-search input {
  border: none;
  background: none;
  width: 100%;
  font: inherit;
  font-size: 0.72rem;
  color: inherit;
  outline: none;
}
.list-search input::placeholder {
  color: #94a3b8;
}
.list-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 0.45rem;
}
.list-group h3 {
  margin: 0.5rem 0.35rem 0.25rem;
  font-size: 0.68rem;
  color: var(--muted);
  font-weight: 500;
}
.list-item {
  width: 100%;
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 0.4rem;
  border: none;
  background: none;
  border-radius: 8px;
  padding: 0.45rem 0.5rem;
  cursor: pointer;
  text-align: left;
  font-size: 0.75rem;
  color: inherit;
}
.list-icon {
  flex-shrink: 0;
  color: #94a3b8;
}
.list-item.on .list-icon {
  color: var(--teal);
}
.list-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}
.list-time {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 0.65rem;
  margin-left: auto;
}
.list-empty {
  padding: 0.5rem;
  color: var(--muted);
  font-size: 0.72rem;
}
.list-item.on {
  background: #eff6ff;
  color: var(--teal);
  font-weight: 600;
}
.list-rail {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  padding: 0.75rem 0.35rem;
  border-right: 1px solid var(--line);
}
.list-rail .list-tool-btn {
  background: #fff;
  border-color: var(--line);
}
.chat-column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chat-head {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.85rem 1rem 0.55rem;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.chat-head-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}
.chat-head h1 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title-input {
  font: inherit;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text);
  border: 1px solid var(--teal);
  border-radius: 8px;
  padding: 0.2rem 0.5rem;
  outline: none;
  min-width: 0;
  width: 22rem;
  max-width: 100%;
  background: #fff;
}
.head-tools {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}
.icon-btn {
  border: none;
  background: none;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--muted);
}
.icon-btn:hover {
  background: #f1f5f9;
  color: var(--text);
}
.icon-btn :deep(.ico) {
  width: 19px;
  height: 19px;
}
.chat-head .sub {
  margin: 0;
  font-size: 0.72rem;
  color: var(--muted);
}
.chat-head-sub {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}
.chat-head-sub .sub {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hint {
  padding: 0 1rem;
  color: var(--muted);
  font-size: 0.75rem;
}
.hint.err {
  color: var(--danger);
}
.thread {
  flex: 1;
  min-width: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  padding: 1rem 1.25rem;
}
.msg {
  display: grid;
  grid-template-columns: 2.4rem minmax(0, 1fr) 2.4rem;
  gap: 0.4rem;
  align-items: flex-start;
  max-width: 100%;
}
.msg.assistant {
  align-self: stretch;
}
.msg.user {
  align-self: stretch;
}
.msg.user .avatar {
  grid-column: 3;
  grid-row: 1;
  justify-self: end;
}
.msg.user .bubble-wrap {
  grid-column: 2;
  grid-row: 1;
}
.msg.assistant .bubble-wrap {
  grid-column: 2;
  grid-row: 1;
}
.msg-meta {
  margin-bottom: 0.25rem;
}
.msg.user .msg-meta {
  text-align: right;
}
.msg-who {
  font-size: 0.68rem;
  color: var(--muted);
  font-weight: 500;
}
.avatar {
  flex-shrink: 0;
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
}
.user-avatar {
  background: #2563eb;
  color: #fff;
}
.bot-avatar {
  background: #eff6ff;
  color: var(--teal);
}
.bot-avatar :deep(.ico) {
  width: 14px;
  height: 14px;
}
.bubble-wrap {
  min-width: 0;
  flex: 1;
}
.msg.user .bubble-wrap {
  flex: 1;
}
.bubble {
  border-radius: 12px;
  padding: 0.65rem 0.8rem;
  background: #fff;
  border: 1px solid var(--line);
}
.user .bubble {
  background: #dbeafe;
  color: var(--text);
  border-color: #bfdbfe;
}
pre {
  margin: 0;
  white-space: pre-wrap;
  font: inherit;
  font-size: 0.8rem;
  line-height: 1.55;
}
.md-body {
  font-size: 0.8rem;
  line-height: 1.55;
  word-break: break-word;
}
.md-body > :first-child {
  margin-top: 0;
}
.md-body > :last-child {
  margin-bottom: 0;
}
.md-body p {
  margin: 0.35rem 0;
}
.md-body ul,
.md-body ol {
  margin: 0.35rem 0;
  padding-left: 1.25rem;
}
.md-body li {
  margin: 0.15rem 0;
}
.md-body blockquote {
  margin: 0.4rem 0;
  padding: 0.25rem 0.7rem;
  border-left: 3px solid var(--line);
  color: var(--muted);
}
.md-body code {
  background: #f1f5f9;
  border-radius: 4px;
  padding: 0.05rem 0.3rem;
  font-size: 0.75rem;
}
.md-body pre {
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.5rem 0.7rem;
  overflow-x: auto;
}
.md-body pre code {
  background: none;
  padding: 0;
}
.md-body table {
  border-collapse: collapse;
  margin: 0.4rem 0;
}
.md-body th,
.md-body td {
  border: 1px solid var(--line);
  padding: 0.25rem 0.5rem;
}
.md-body a {
  color: var(--teal);
}
.thinking {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--muted);
  font-size: 0.75rem;
}
.spin {
  width: 0.85rem;
  height: 0.85rem;
  border: 2px solid var(--line);
  border-top-color: var(--teal);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.cites {
  margin-top: 0.65rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--line);
}
.cites-label {
  margin: 0 0 0.4rem;
  font-size: 0.68rem;
  color: var(--muted);
}
.cite-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  width: auto;
  max-width: 100%;
  border: none;
  background: #e2e8f0;
  color: #fff;
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  margin: 0 0.3rem 0.3rem 0;
  cursor: pointer;
  font-size: 0.6rem;
}
.cite-chip.on,
.cite-chip:hover {
  background: #d3dce6;
  color: #fff;
}
.cite-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cite-more {
  border: none;
  background: none;
  color: var(--teal);
  font-size: 0.68rem;
  cursor: pointer;
  padding: 0;
}
.source-side {
  width: min(19rem, 30vw);
  flex-shrink: 0;
  min-width: 14rem;
  align-self: stretch;
  border-radius: 0;
  border: none;
  border-left: 1px solid var(--line);
  box-shadow: none;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
  padding: 0.75rem 0.85rem 1rem;
}
.source-head h2 {
  margin: 0 0 0.65rem;
  font-size: 0.88rem;
}
.source-overview h3,
.source-all h3 {
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  color: var(--muted);
  font-weight: 600;
}
.donut-row {
  display: flex;
  gap: 0.65rem;
  align-items: center;
  margin-bottom: 0.85rem;
}
.donut {
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 50%;
  position: relative;
  flex-shrink: 0;
}
.donut-hole {
  position: absolute;
  inset: 0.85rem;
  border-radius: 50%;
  background: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 0.58rem;
  color: var(--muted);
}
.donut-hole strong {
  font-size: 0.82rem;
  color: var(--text);
}
.donut-legend {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.65rem;
  color: var(--muted);
}
.donut-legend li {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.2rem;
}
.dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  flex-shrink: 0;
}
.source-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.55rem 0.6rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  background: #fff;
}
.source-card.on {
  border-color: var(--teal);
  background: #f0f9ff;
}
.source-card-top {
  display: flex;
  justify-content: space-between;
  gap: 0.35rem;
  align-items: center;
  margin-bottom: 0.25rem;
}
.source-doc {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--teal);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-chunk {
  margin-top: 0.35rem;
  padding-top: 0.35rem;
  border-top: 1px dashed var(--line);
}
.source-chunk:first-of-type {
  margin-top: 0.15rem;
  padding-top: 0;
  border-top: none;
}
.source-snippet {
  margin: 0 0 0.2rem;
  font-size: 0.68rem;
  line-height: 1.45;
  color: var(--muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.source-chunk-link {
  font-size: 0.62rem;
  color: var(--teal);
  text-decoration: none;
}
.source-chunk-link:hover {
  text-decoration: underline;
}
.source-meta {
  font-size: 0.62rem;
  color: var(--muted);
  flex-shrink: 0;
}
.source-more {
  width: 100%;
  justify-content: center;
  margin-top: 0.25rem;
}
.composer-wrap {
  flex-shrink: 0;
  padding: 0.75rem 1rem 0.6rem;
}
.composer {
  margin: 0;
  border-radius: 14px;
  padding: 0.7rem 0.75rem 0.55rem;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.composer textarea {
  width: 100%;
  border: none;
  border-radius: 0;
  padding: 0.15rem 0.35rem 0.4rem;
  resize: none;
  font-size: inherit;
  min-height: 2.4rem;
  background: transparent;
  outline: none;
}
.composer-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.35rem;
}
.composer-left {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.composer-right {
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.tool-btn {
  border: none;
  background: none;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  cursor: pointer;
  color: #475569;
  font-size: 0.8rem;
}
.tool-btn :deep(.ico) {
  width: 16px;
  height: 16px;
}
.tool-btn:not(:disabled):hover {
  background: #f1f5f9;
}
.tool-btn:disabled {
  cursor: not-allowed;
  color: #94a3b8;
}
.tools-btn {
  width: auto;
  padding: 0 0.7rem;
  border: 1px solid var(--line);
  background: #fff;
  white-space: nowrap;
}
.tools-btn .chev {
  width: 0.4rem;
  height: 0.4rem;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: rotate(45deg);
  display: inline-block;
  margin-left: 0.15rem;
  vertical-align: 2px;
}
.composer-hint {
  color: var(--muted);
  font-size: 0.7rem;
  white-space: nowrap;
}
.send-btn {
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  justify-content: center;
  border-radius: 12px;
}
.send-btn :deep(.ico) {
  width: 17px;
  height: 17px;
}
.smart-toggle {
  margin-top: 0.5rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 999px;
  padding: 0.3rem 0.75rem;
  font-size: 0.75rem;
  color: var(--muted);
  cursor: pointer;
}
.smart-toggle :deep(.ico) {
  width: 13px;
  height: 13px;
}
.smart-toggle.on {
  border-color: var(--teal);
  color: var(--teal);
  background: #eff6ff;
  font-weight: 600;
}
.smart-toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mode-switch {
  display: inline-flex;
  gap: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  margin-right: 0.15rem;
}
.mode-switch button {
  border: none;
  background: #fff;
  padding: 0.35rem 0.75rem;
  cursor: pointer;
  color: var(--muted);
  font-size: 0.72rem;
  border-right: 1px solid var(--line);
}
.mode-switch button:last-child {
  border-right: none;
}
.mode-switch button.on {
  background: #eff6ff;
  color: var(--teal);
  font-weight: 600;
}
.mode-switch button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
@media (max-width: 960px) {
  .source-side {
    display: none;
  }
  .chat-list {
    width: 13rem;
  }
  .head-tools .mode-switch {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}
</style>
