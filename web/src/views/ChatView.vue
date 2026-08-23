<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listMessages, type Citation } from "../api";
import { selectedKbId } from "../kb";

const route = useRoute();
const router = useRouter();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const answer = ref("");
const citations = ref<Citation[]>([]);
const conversationId = ref<string>(typeof route.query.c === "string" ? route.query.c : "");
const error = ref("");
const streaming = ref(false);

function hashFor(c: Citation) {
  if (c.page_start != null) return `#page-${c.page_start}`;
  return "";
}

async function ask() {
  error.value = "";
  answer.value = "";
  citations.value = [];
  streaming.value = true;
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        knowledge_base_id: selectedKbId.value || undefined,
        conversation_id: conversationId.value || undefined,
      }),
    });
    if (!res.ok || !res.body) throw new Error(await res.text());
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
        if (payload.type === "token" && payload.text) answer.value += payload.text;
        if (payload.type === "citations") {
          conversationId.value = payload.conversation_id || conversationId.value;
          citations.value = payload.citations || [];
          if (payload.answer) answer.value = payload.answer;
        }
      }
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    streaming.value = false;
  }
}

onMounted(async () => {
  if (conversationId.value) {
    try {
      const rows = await listMessages(conversationId.value);
      const lastAssistant = [...rows].reverse().find((m) => m.role === "assistant");
      if (lastAssistant) {
        answer.value = lastAssistant.content;
        citations.value = (lastAssistant.citations as Citation[]) || [];
      }
    } catch (e) {
      error.value = String(e);
    }
  }
  if (query.value) ask();
});

function openCite(c: Citation) {
  router.push({ path: `/documents/${c.document_id}`, hash: hashFor(c) });
}
</script>

<template>
  <h1>对话</h1>
  <p v-if="error" class="err">{{ error }}</p>
  <p>
    <textarea v-model="query" rows="3" cols="60"></textarea><br />
    <button type="button" :disabled="streaming" @click="ask">提问</button>
  </p>
  <pre class="answer">{{ answer }}</pre>
  <h2>引用</h2>
  <ul>
    <li v-for="c in citations" :key="c.chunk_id">
      <button type="button" class="link" @click="openCite(c)">{{ c.document_name }}</button>
      <span v-if="c.page_start != null"> p.{{ c.page_start }}</span>
    </li>
  </ul>
</template>

<style scoped>
.err {
  color: #a30;
}
.answer {
  white-space: pre-wrap;
  max-width: 48rem;
}
.link {
  background: none;
  border: none;
  color: #245;
  text-decoration: underline;
  cursor: pointer;
  padding: 0;
  font: inherit;
}
</style>
