<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  listConversations,
  listMessages,
  messageFromErrorBody,
  type ChatMessage,
  type Citation,
  type Conversation,
} from "../api";
import Icon from "../components/Icon.vue";
import { selectedKb, selectedKbId } from "../kb";

const route = useRoute();
const router = useRouter();
const draft = ref(typeof route.query.q === "string" ? route.query.q : "");
const messages = ref<ChatMessage[]>([]);
const conversationId = ref<string>(typeof route.query.c === "string" ? route.query.c : "");
const error = ref("");
const streaming = ref(false);
const mode = ref<"chat" | "agent" | "report">("chat");
const CHAT_MAP = "zhiyu-chat-by-kb";

function chatMap(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(CHAT_MAP) || "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

function rememberConversation(id: string) {
  conversationId.value = id;
  const kb = selectedKbId.value;
  const map = chatMap();
  if (id && kb) map[kb] = id;
  else if (kb) delete map[kb];
  localStorage.setItem(CHAT_MAP, JSON.stringify(map));
  const query: Record<string, string> = {};
  if (id) query.c = id;
  router.replace({ path: "/chat", query });
}
const conversations = ref<Conversation[]>([]);
const sidebarOpen = ref(true);
const box = ref<HTMLElement | null>(null);

async function refreshConversations() {
  conversations.value = await listConversations(selectedKbId.value || undefined);
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        useGraph
          ? {
              task: mode.value === "report" ? "report" : "agent",
              query: q,
              knowledge_base_id: selectedKbId.value || undefined,
            }
          : {
              query: q,
              knowledge_base_id: selectedKbId.value || undefined,
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
    conversationId.value = chatMap()[selectedKbId.value] || "";
  }
  try {
    await refreshConversations();
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
  if (draft.value) ask();
});

watch(selectedKbId, async (kb) => {
  if (streaming.value) return;
  conversationId.value = chatMap()[kb] || "";
  messages.value = [];
  try {
    await refreshConversations();
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
});

function openCite(c: Citation) {
  router.push({ path: `/documents/${c.document_id}`, hash: hashFor(c) });
}

const kbName = () => (selectedKb.value?.is_default ? "默认" : selectedKb.value?.name || "默认");
</script>

<template>
  <main class="page chat-page">
    <aside class="chat-side" :class="{ collapsed: !sidebarOpen }">
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
        <p class="sub">与「{{ kbName() }}」知识库对话，回答会标注引用来源</p>
      </div>
      <div class="head-actions">
        <div class="mode-switch" role="group" aria-label="提问模式">
          <button type="button" :class="{ on: mode === 'chat' }" :disabled="streaming" @click="mode = 'chat'">
            对话
          </button>
          <button type="button" :class="{ on: mode === 'agent' }" :disabled="streaming" @click="mode = 'agent'">
            Agent
          </button>
          <button type="button" :class="{ on: mode === 'report' }" :disabled="streaming" @click="mode = 'report'">
            报告
          </button>
        </div>
        <button class="btn" type="button" @click="newChat">+ 新对话</button>
      </div>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <div ref="box" class="thread">
      <div v-for="m in messages" :key="m.id" :class="['msg', m.role]">
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
              @click="openCite(c)"
            >
              <span>{{ c.document_name }}</span>
              <em v-if="c.page_start != null">第 {{ c.page_start }} 页</em>
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

    <div class="composer card">
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
  </main>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0.9rem;
  width: min(1280px, calc(100% - 1.5rem));
  min-height: calc(100vh - 8rem);
}
.chat-side {
  position: relative;
  width: 15.5rem;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chat-side.collapsed {
  width: auto;
  align-self: center;
  background: none;
  border: none;
  border-radius: 0;
}
.fold {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  margin: 0;
  transform: translate(50%, -50%);
  border: none;
  background: none;
  color: #b0b8c0;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}
.chat-side.collapsed .fold {
  position: static;
  transform: none;
}
.fold:hover {
  color: #8b949e;
}
.fold :deep(.ico) {
  width: 18px;
  height: 18px;
}
.fold.open :deep(.ico) {
  transform: rotate(90deg);
}
.side-body {
  padding: 0.85rem 0.7rem 0.8rem;
  overflow: auto;
}
.side-body h2 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}
.side-item {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  border-top: 1px solid var(--line);
  padding: 0.7rem 0.15rem;
  cursor: pointer;
  color: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-item.on {
  color: var(--teal);
  font-weight: 600;
}
.side-empty {
  color: var(--muted);
  font-size: 0.85rem;
}
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 8rem);
}
.thread {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1rem;
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
  font-size: 0.82rem;
  margin-bottom: 0.35rem;
}
.user .bubble {
  background: var(--teal);
  color: #fff;
  border-radius: 14px;
  padding: 0.75rem 0.95rem;
}
.assistant .bubble {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.65rem 0.9rem;
}
pre {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  font: inherit;
  line-height: 1.55;
}
.thinking {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--muted);
}
.spin {
  width: 0.95rem;
  height: 0.95rem;
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
  margin-top: 0.8rem;
  padding-top: 0.7rem;
  border-top: 1px solid var(--line);
}
.cites p {
  margin: 0 0 0.45rem;
  color: var(--muted);
  font-size: 0.85rem;
}
.cite {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  background: #f3f5f7;
  border: none;
  border-radius: 8px;
  padding: 0.5rem 0.7rem;
  margin-bottom: 0.4rem;
  cursor: pointer;
  text-align: left;
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
}
.more {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--muted);
  letter-spacing: 0.2em;
  padding: 0.2rem 0;
  cursor: pointer;
}
.composer {
  padding: 0.8rem 0.9rem;
}
.composer textarea {
  width: 100%;
  border: none;
  resize: vertical;
  outline: none;
}
.composer-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted);
  font-size: 0.8rem;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.mode-switch {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.mode-switch button {
  border: none;
  background: none;
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  color: var(--muted);
}
.mode-switch button.on {
  background: var(--teal);
  color: #fff;
}
.mode-switch button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
