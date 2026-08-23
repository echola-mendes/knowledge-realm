<script setup lang="ts">
import { nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listMessages, messageFromErrorBody, type ChatMessage, type Citation } from "../api";
import { selectedKb, selectedKbId } from "../kb";

const route = useRoute();
const router = useRouter();
const draft = ref(typeof route.query.q === "string" ? route.query.q : "");
const messages = ref<ChatMessage[]>([]);
const conversationId = ref<string>(typeof route.query.c === "string" ? route.query.c : "");
const error = ref("");
const streaming = ref(false);
const box = ref<HTMLElement | null>(null);

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
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: q,
        knowledge_base_id: selectedKbId.value || undefined,
        conversation_id: conversationId.value || undefined,
      }),
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
          conversationId.value = payload.conversation_id || conversationId.value;
          assistant.citations = payload.citations || [];
          if (payload.answer) assistant.content = payload.answer;
        }
        scrollBottom();
      }
    }
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
  conversationId.value = "";
  messages.value = [];
  draft.value = "";
  error.value = "";
  router.replace({ path: "/chat" });
}

onMounted(async () => {
  try {
    await loadHistory();
  } catch (e) {
    error.value = String(e);
  }
  if (draft.value) ask();
});

function openCite(c: Citation) {
  router.push({ path: `/documents/${c.document_id}`, hash: hashFor(c) });
}

const kbName = () => (selectedKb.value?.is_default ? "默认" : selectedKb.value?.name || "默认");
</script>

<template>
  <main class="page chat-page">
    <div class="page-head">
      <div>
        <h1>对话</h1>
        <p class="sub">与「{{ kbName() }}」知识库对话，回答会标注引用来源</p>
      </div>
      <button class="btn" type="button" @click="newChat">+ 新对话</button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <div ref="box" class="thread">
      <div v-for="m in messages" :key="m.id" :class="['msg', m.role]">
        <div v-if="m.role === 'assistant'" class="who">知域</div>
        <div class="bubble">
          <pre>{{ m.content }}</pre>
          <div v-if="m.role === 'assistant' && m.citations?.length" class="cites">
            <p>引用来源 ({{ m.citations.length }})</p>
            <button
              v-for="c in m.citations"
              :key="c.chunk_id"
              type="button"
              class="cite"
              @click="openCite(c)"
            >
              <span>{{ c.document_name }}</span>
              <em v-if="c.page_start != null">第 {{ c.page_start }} 页</em>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="composer card">
      <textarea
        v-model="draft"
        rows="3"
        placeholder="继续追问，或输入新问题..."
        @keydown="onKey"
      ></textarea>
      <div class="composer-bar">
        <span>Enter 发送 · Shift+Enter 换行</span>
        <button class="btn btn-primary" type="button" :disabled="streaming" @click="ask">发送</button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.chat-page {
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
  padding: 0.9rem 1rem;
}
pre {
  margin: 0;
  white-space: pre-wrap;
  font: inherit;
  line-height: 1.6;
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
.cite em {
  font-style: normal;
  color: var(--muted);
  white-space: nowrap;
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
</style>
