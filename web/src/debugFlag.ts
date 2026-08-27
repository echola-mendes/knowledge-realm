import { ref } from "vue";

const KEY = "zhiyu-show-debug";

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export const debugEnabled = ref(read());

export function setDebugEnabled(on: boolean) {
  debugEnabled.value = on;
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
}
