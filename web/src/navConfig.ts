import { ref } from "vue";

export interface NavItemDef {
  match: string;
  label: string;
  icon: string;
  to: string;
}

export interface NavConfig {
  order: string[];
  labels: Record<string, string>;
}

// 侧边栏菜单的固定元数据，match 作为稳定 key；默认顺序即页面展示顺序
export const NAV_ITEMS: readonly NavItemDef[] = [
  { match: "home", label: "首页", icon: "home", to: "/" },
  { match: "chat", label: "对话", icon: "chat", to: "/chat" },
  { match: "search", label: "搜索", icon: "search", to: "/search" },
  { match: "kbs", label: "知识库", icon: "db", to: "/knowledge-bases" },
  { match: "docs", label: "文档", icon: "doc", to: "/documents" },
  { match: "knowledge-graph", label: "图谱", icon: "nodes", to: "/knowledge-graph" },
  { match: "insights", label: "检测", icon: "spark", to: "/insights" },
  { match: "tools", label: "工具", icon: "tools", to: "/tools" },
  { match: "monitoring", label: "监控", icon: "monitor", to: "/monitoring" },
  { match: "basics", label: "基础", icon: "sliders", to: "/basics" },
  { match: "settings", label: "设置", icon: "gear", to: "/settings" },
  { match: "debug", label: "调试", icon: "bug", to: "/debug" },
];

const KEY = "zhiyu-nav-config";

function mergeOrder(saved: string[]): string[] {
  const defaults = NAV_ITEMS.map((i) => i.match);
  const known = new Set(defaults);
  const kept = saved.filter((m) => known.has(m));
  const missing = defaults.filter((m) => !kept.includes(m));
  const order = [...kept];
  for (const match of missing) {
    const idx = defaults.indexOf(match);
    // 缺失项按默认位置补齐：优先插到默认前驱之后，其次默认后继之前
    let at = -1;
    for (let j = idx - 1; j >= 0; j -= 1) {
      const pos = order.indexOf(defaults[j]);
      if (pos >= 0) {
        at = pos + 1;
        break;
      }
    }
    if (at < 0) {
      for (let j = idx + 1; j < defaults.length; j += 1) {
        const pos = order.indexOf(defaults[j]);
        if (pos >= 0) {
          at = pos;
          break;
        }
      }
    }
    if (at < 0) order.push(match);
    else order.splice(at, 0, match);
  }
  return order;
}

function normalize(raw: NavConfig | null | undefined): NavConfig {
  const labels: Record<string, string> = {};
  for (const item of NAV_ITEMS) {
    const v = raw?.labels?.[item.match];
    labels[item.match] = typeof v === "string" && v.trim() ? v.trim() : item.label;
  }
  return { order: mergeOrder(Array.isArray(raw?.order) ? raw.order : []), labels };
}

function read(): NavConfig {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return normalize(null);
    return normalize(JSON.parse(raw) as NavConfig);
  } catch {
    return normalize(null);
  }
}

export const navConfig = ref<NavConfig>(read());

export function saveNavConfig(next: NavConfig) {
  navConfig.value = normalize(next);
  try {
    localStorage.setItem(KEY, JSON.stringify(navConfig.value));
  } catch {
    /* ignore */
  }
}

export function resetNavConfig() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  navConfig.value = normalize(null);
}
