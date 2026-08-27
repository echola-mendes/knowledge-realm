<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getMe,
  listConversations,
  listMessages,
  messageFromErrorBody,
  type ChatMessage,
  type Citation,
  type Conversation,
} from "../api";
import Icon from "../components/Icon.vue";
import RetrievalDebugPanel from "../components/RetrievalDebugPanel.vue";
import { debugEnabled, setDebugEnabled } from "../debugFlag";

const route = useRoute();
const router = useRouter();
const draft = ref(typeof route.query.q === "string" ? route.query.q : "");
const messages = ref<ChatMessage[]>([]);
const conversationId = ref<string>(typeof route.query.c === "string" ? route.query.c : "");
const error = ref("");
const streaming = ref(false);
const mode = ref<"chat" | "agent" | "report">("chat");
const debugQuery = ref("");
const CHAT_KEY = "zhiyu-chat-id";

function rememberConversation(id: string) {
  conversationId.value = id;
  if (id) localStorage.setItem(CHAT_KEY, id);
  else localStorage.removeItem(CHAT_KEY);
  const query: Record<string, string> = {};
  if (id) query.c = id;
  router.replace({ path: "/chat", query });
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
const threadMessages = computed(() => [greetingMsg.value, ...messages.value]);
const sidebarOpen = ref(false);
const box = ref<HTMLElement | null>(null);
const activeCite = ref<string>("");
const citeFocus = ref(false);

const panelCites = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i];
    if (m.role === "assistant" && m.citations?.length) return m.citations;
  }
  return [] as Citation[];
});

const shownCite = computed(() => {
  const rows = panelCites.value;
  if (!rows.length) return null;
  return rows.find((c) => c.chunk_id === activeCite.value) || rows[0];
});

async function refreshConversations() {
  conversations.value = await listConversations();
}

async function openConversation(id: string) {
  if (streaming.value) return;
  mode.value = "chat";
  rememberConversation(id);
  try {
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
}
const CITE_LIMIT = 2;
const citeOpen = ref<Record<string, boolean>>({});

function visibleCites(m: ChatMessage) {
  const rows = m.citations || [];
  if (citeOpen.value[m.id] || rows.length <= CITE_LIMIT) return rows;
  return rows.slice(0, CITE_LIMIT);
}

function isThinking(m: ChatMessage) {
  const last = messages.value[messages.value.length - 1];
  return m.role === "assistant" && !m.content.trim() && streaming.value && last === m;
}

function formatScore(score: number | undefined) {
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(3) : "—";
}

function hashFor(c: Citation) {
  if (c.page_start != null) return `#page-${c.page_start}`;
  return "";
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
  debugQuery.value = q;
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
          if (!useGraph) {
            const cid = payload.conversation_id || conversationId.value;
            if (cid) rememberConversation(cid);
          }
          assistant.citations = payload.citations || [];
          if (payload.answer) assistant.content = payload.answer;
        }
        scrollBottom();
      }
    }
    if (!useGraph) await refreshConversations();
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

watch(panelCites, (rows) => {
  citeFocus.value = false;
  activeCite.value = rows[0]?.chunk_id || "";
});

function pickCite(id: string) {
  activeCite.value = id;
  citeFocus.value = true;
}

function openCite(c: Citation) {
  router.push({ path: `/documents/${c.document_id}`, hash: hashFor(c) });
}
</script>

<template>
  <main class="page chat-page">
    <aside class="chat-side card" :class="{ collapsed: !sidebarOpen }">
      <button
        class="fold"
        type="button"
        :class="{ open: sidebarOpen }"
        :aria-expanded="sidebarOpen"
        :title="sidebarOpen ? '折叠对话记录' : '展开对话记录'"
        @click="sidebarOpen = !sidebarOpen"
      >
        <Icon :name="sidebarOpen ? 'chevron' : 'chat'" />
      </button>
      <div v-if="sidebarOpen" class="side-body">
        <button class="btn new-chat" type="button" @click="newChat">+ 新对话</button>
        <h2>对话记录</h2>
        <button
          v-for="c in conversations"
          :key="c.id"
          type="button"
          class="side-item"
          :class="{ on: c.id === conversationId }"
          @click="openConversation(c.id)"
        >
          {{ c.title }}
        </button>
        <p v-if="!conversations.length" class="side-empty">暂无对话</p>
      </div>
    </aside>
    <div class="chat-main">
    <div class="page-head">
      <div>
        <h1>对话</h1>
        <p class="sub hint">默认检索全部已开启的知识库，回答会标注引用来源</p>
      </div>
      <div class="head-actions">
        <div class="mode-switch" role="group" aria-label="Question mode">
          <button type="button" :class="{ on: mode === 'chat' }" :aria-pressed="mode === 'chat'" :disabled="streaming" @click="mode = 'chat'">
            Chat
          </button>
          <button type="button" :class="{ on: mode === 'agent' }" :aria-pressed="mode === 'agent'" :disabled="streaming" @click="mode = 'agent'">
            Agent
          </button>
          <button type="button" :class="{ on: mode === 'report' }" :aria-pressed="mode === 'report'" :disabled="streaming" @click="mode = 'report'">
            Report
          </button>
        </div>
        <label class="debug-toggle">
          <span>Debug</span>
          <input
            type="checkbox"
            role="switch"
            :checked="debugEnabled"
            @change="setDebugEnabled(($event.target as HTMLInputElement).checked)"
          />
        </label>
      </div>
    </div>
    <p v-if="error" class="hint err">{{ error }}</p>

    <div class="stage">
    <div ref="box" class="thread">
      <div v-for="m in threadMessages" :key="m.id" :class="['msg', m.role]">
        <div v-if="m.role === 'assistant'" class="who">知域</div>
        <div class="bubble">
          <div v-if="isThinking(m)" class="thinking">
            <span class="spin" aria-hidden="true"></span>
            思考中……
          </div>
          <pre v-else>{{ m.content.replace(/^\s+/, "") }}</pre>
          <div v-if="m.role === 'assistant' && m.citations?.length" class="cites">
            <p>引用来源 ({{ m.citations.length }})</p>
            <button
              v-for="c in visibleCites(m)"
              :key="c.chunk_id"
              type="button"
              class="cite"
              :class="{ on: c.chunk_id === shownCite?.chunk_id }"
              @click="pickCite(c.chunk_id)"
            >
              <span>{{ c.document_name }}</span>
              <em v-if="debugEnabled">{{ formatScore(c.score) }}</em>
            </button>
            <button
              v-if="m.citations.length > CITE_LIMIT && !citeOpen[m.id]"
              type="button"
              class="more"
              @click="citeOpen[m.id] = true"
            >
              …
            </button>
          </div>
        </div>
      </div>
    </div>
    <aside v-if="panelCites.length" class="cite-side card" aria-label="引用文档">
      <h2>引用文档</h2>
      <label v-if="citeFocus" class="cite-pick">
        <span>文档</span>
        <select v-model="activeCite">
          <option v-for="c in panelCites" :key="c.chunk_id" :value="c.chunk_id">
            {{ c.document_name }}{{ c.page_start != null ? ` · 第 ${c.page_start} 页` : "" }}
          </option>
        </select>
      </label>
      <article v-if="citeFocus && shownCite" class="cite-body">
        <p class="cite-meta">
          <span>{{ shownCite.document_name }}</span>
          <em v-if="shownCite.page_start != null">第 {{ shownCite.page_start }} 页</em>
        </p>
        <p v-if="debugEnabled" class="cite-score">分数 {{ formatScore(shownCite.score) }}</p>
        <pre>{{ shownCite.content }}</pre>
        <button class="btn-link" type="button" @click="openCite(shownCite)">打开全文</button>
      </article>
      <div v-else class="cite-list">
        <article v-for="c in panelCites" :key="c.chunk_id" class="cite-body">
          <p class="cite-meta">
            <span>{{ c.document_name }}</span>
            <em v-if="c.page_start != null">第 {{ c.page_start }} 页</em>
          </p>
          <p v-if="debugEnabled" class="cite-score">分数 {{ formatScore(c.score) }}</p>
          <pre>{{ c.content }}</pre>
          <button class="btn-link" type="button" @click="openCite(c)">打开全文</button>
        </article>
      </div>
    </aside>
    </div>

    <div class="composer card pad">
      <textarea
        v-model="draft"
        rows="3"
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
        <span>Enter 发送 · Shift+Enter 换行</span>
        <button class="btn btn-primary" type="button" :disabled="streaming" @click="ask">发送</button>
      </div>
    </div>
    </div>
    <RetrievalDebugPanel v-if="debugEnabled" :query="debugQuery" />
  </main>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0.85rem;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem 2rem;
  min-height: calc(100vh - 8rem);
  font-size: 12.5px;
  background: transparent;
}
.chat-page .btn {
  padding: 0.5rem 0.85rem;
  border-radius: 10px;
  font-size: inherit;
}
.chat-page .page-head h1 {
  font-size: 1.05rem;
}
.hint {
  color: var(--muted);
  font-size: 0.75rem;
}
.hint.err {
  color: var(--danger);
}
.chat-side {
  position: relative;
  width: 14.5rem;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chat-side.collapsed {
  width: auto;
  align-self: center;
  background: none;
  border: none;
  box-shadow: none;
  border-radius: 0;
}
.fold {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  min-height: 24px;
  margin: 0;
  transform: translate(50%, -50%);
  border: none;
  background: none;
  color: #94a3b8;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  border-radius: 6px;
}
.fold:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 2px;
}
.chat-side.collapsed .fold {
  position: static;
  transform: none;
}
.fold:hover {
  color: #64748b;
}
.fold :deep(.ico) {
  width: 18px;
  height: 18px;
}
.fold.open :deep(.ico) {
  transform: rotate(90deg);
}
.side-body {
  padding: 0.75rem 0.7rem 0.7rem;
  overflow: auto;
}
.new-chat {
  width: 100%;
  justify-content: center;
  margin-bottom: 0.65rem;
}
.side-body h2 {
  margin: 0 0 0.4rem;
  font-size: 0.78rem;
}
.side-item {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  border-top: 1px solid var(--line);
  padding: 0.55rem 0.15rem;
  cursor: pointer;
  color: inherit;
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-item.on {
  color: var(--teal);
  font-weight: 600;
  background: #f0f7ff;
}
.side-empty {
  color: var(--muted);
  font-size: 0.75rem;
}
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.stage {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0.75rem;
}
.cite-side {
  width: min(22rem, 34vw);
  flex-shrink: 0;
  min-width: 14rem;
  padding: 0.85rem 0.9rem 1rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.cite-side h2 {
  margin: 0 0 0.45rem;
  font-size: 0.78rem;
}
.cite-pick {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  margin-bottom: 0.55rem;
  font-size: 0.68rem;
  color: var(--muted);
}
.cite-pick select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
  background: #fff;
  color: var(--text);
  font-size: 0.72rem;
}
.cite-pick select:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
}
.cite-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}
.cite-list .cite-body {
  flex: none;
  overflow: visible;
  padding-bottom: 0.65rem;
  border-bottom: 1px solid var(--line);
}
.cite-list .cite-body:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.cite-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.cite-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  margin: 0 0 0.35rem;
  font-size: 0.72rem;
  color: var(--text);
}
.cite-score {
  margin: 0 0 0.4rem;
  font-size: 0.68rem;
  color: var(--muted);
}
.cite-body pre {
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--text);
  margin-bottom: 0.5rem;
}
@media (max-width: 900px) {
  .cite-side {
    display: none;
  }
}
.thread {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
}
.msg.user {
  align-self: flex-end;
  max-width: min(36rem, 92%);
}
.msg.assistant {
  align-self: flex-start;
  max-width: min(44rem, 100%);
}
.who {
  color: var(--muted);
  font-size: 0.72rem;
  margin-bottom: 0.25rem;
}
.user .bubble {
  background: #2563eb;
  color: #fff;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
}
.assistant .bubble {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
}
pre {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  font: inherit;
  font-size: 0.78rem;
  line-height: 1.5;
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
@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}
.cites {
  margin-top: 0.55rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--line);
}
.cites p {
  margin: 0 0 0.35rem;
  color: var(--muted);
  font-size: 0.68rem;
}
.cite {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  background: #f0f7ff;
  border: 1px solid #e0edff;
  border-radius: 8px;
  padding: 0.4rem 0.55rem;
  margin-bottom: 0.3rem;
  cursor: pointer;
  text-align: left;
  font-size: 0.72rem;
  min-height: 24px;
}
.cite:hover,
.cite.on {
  background: var(--teal-soft);
  border-color: #bfdbfe;
}
.cite:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
}
.cite span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cite em {
  font-style: normal;
  color: var(--muted);
  white-space: nowrap;
  font-size: 0.68rem;
}
.more {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--muted);
  letter-spacing: 0.2em;
  padding: 0.2rem 0;
  cursor: pointer;
  min-height: 24px;
}
.pad {
  padding: 0.75rem 0.85rem;
}
.composer {
  margin-top: 0.35rem;
}
.composer textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
  resize: vertical;
  font-size: inherit;
}
.composer textarea:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
}
.composer-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted);
  font-size: 0.72rem;
  margin-top: 0.45rem;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.debug-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.72rem;
  color: var(--muted);
  margin: 0;
}
.debug-toggle input {
  accent-color: var(--teal);
}
.mode-switch {
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 0;
  border-bottom: 1px solid var(--line);
  background: none;
}
.mode-switch button {
  border: none;
  background: none;
  border-radius: 0;
  padding: 0.35rem 0.7rem 0.45rem;
  cursor: pointer;
  color: var(--muted);
  font-size: 0.72rem;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.mode-switch button.on {
  background: none;
  color: var(--teal);
  font-weight: 600;
  border-bottom-color: var(--teal);
}
.mode-switch button:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 1px;
}
.mode-switch button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
