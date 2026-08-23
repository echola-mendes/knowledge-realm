import { computed, ref } from "vue";
import { listKnowledgeBases, type KnowledgeBase } from "./api";

const KEY = "zhiyu-kb-id";
export const knowledgeBases = ref<KnowledgeBase[]>([]);
export const selectedKbId = ref<string>(sessionStorage.getItem(KEY) || "");

export const selectedKb = computed(() =>
  knowledgeBases.value.find((kb) => kb.id === selectedKbId.value) || knowledgeBases.value[0],
);

export async function loadKnowledgeBases() {
  knowledgeBases.value = await listKnowledgeBases();
  if (!knowledgeBases.value.some((kb) => kb.id === selectedKbId.value)) {
    const def = knowledgeBases.value.find((kb) => kb.is_default) || knowledgeBases.value[0];
    selectedKbId.value = def?.id || "";
  }
  sessionStorage.setItem(KEY, selectedKbId.value);
}

export function selectKb(id: string) {
  selectedKbId.value = id;
  sessionStorage.setItem(KEY, id);
}
