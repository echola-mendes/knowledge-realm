import { ref } from "vue";

export interface NavItemDef {
  match: string;
  label: string;
  icon: string;
  to: string;
}

export interface NavNode {
  id: string;
  label: string;
  icon: string;
  to?: string;
  custom?: boolean;
  enabled: boolean;
  children?: NavNode[];
}

// 侧边栏菜单的固定元数据，id 作为稳定 key；默认顺序即页面展示顺序
export const NAV_ITEMS: readonly NavItemDef[] = [
  { match: "home", label: "首页", icon: "home", to: "/" },
  { match: "chat", label: "对话", icon: "chat", to: "/chat" },
  { match: "search", label: "搜索", icon: "search", to: "/search" },
  { match: "kbs", label: "知识库", icon: "db", to: "/knowledge-bases" },
  { match: "docs", label: "文档", icon: "doc", to: "/documents" },
  { match: "knowledge-graph", label: "图谱", icon: "nodes", to: "/knowledge-graph" },
  { match: "insights", label: "检测", icon: "spark", to: "/insights" },
  { match: "tools", label: "工具", icon: "tools", to: "/tools" },
  { match: "monitoring", label: "监控", icon: "monitor", to: "/monitoring/decisions" },
  { match: "basics", label: "基础", icon: "sliders", to: "/basics" },
  { match: "settings", label: "设置", icon: "gear", to: "/settings" },
  { match: "debug", label: "调试", icon: "bug", to: "/debug" },
];

export const MAX_MENU_DEPTH = 3;

/** 工具 / 基础 / 监控：侧栏只作入口，二级菜单在页内布局，不在侧栏展开子项 */
export const PAGE_SECTION_IDS = new Set(["tools", "basics", "monitoring"]);

/** 页内二级菜单的内置结构：菜单管理页可见，改名 / 开关 / 排序会同步到对应布局页 */
export const SECTION_TREE_DEFAULTS: Record<string, NavNode[]> = {
  tools: [
    {
      id: "tools-trips",
      label: "旅程",
      icon: "plane",
      enabled: true,
      children: [
        { id: "tools-trips-list", label: "我的行程单", icon: "doc", to: "/tools/trips", enabled: true },
        { id: "tools-trips-new", label: "创建新行程", icon: "doc", to: "/tools/trips/new", enabled: true },
      ],
    },
    {
      id: "tools-consult",
      label: "AI资讯",
      icon: "headset",
      enabled: true,
      children: [
        { id: "tools-news", label: "今日热榜", icon: "doc", to: "/tools/news", enabled: true },
        {
          id: "tools-consult-history",
          label: "历史记录",
          icon: "doc",
          to: "/tools/consult/history",
          enabled: true,
        },
      ],
    },
    {
      id: "tools-image",
      label: "AI生图",
      icon: "image",
      enabled: true,
      children: [
        { id: "tools-image-desk", label: "生图台", icon: "doc", to: "/tools/image", enabled: true },
        { id: "tools-image-works", label: "我的作品", icon: "doc", to: "/tools/image/works", enabled: true },
      ],
    },
    {
      id: "tools-market",
      label: "更多工具",
      icon: "apps",
      enabled: true,
      children: [
        { id: "tools-market-page", label: "工具市场", icon: "doc", to: "/tools/market", enabled: true },
      ],
    },
  ],
  monitoring: [
    { id: "monitoring-decisions", label: "决策审计", icon: "spark", to: "/monitoring/decisions", enabled: true },
    { id: "monitoring-operations", label: "操作审计", icon: "list", to: "/monitoring/operations", enabled: true },
  ],
  basics: [
    { id: "basics-menus", label: "菜单管理", icon: "list", to: "/basics/menus", enabled: true },
    { id: "basics-jobs", label: "定时任务", icon: "refresh", to: "/basics/jobs", enabled: true },
  ],
};

/** 页内二级里不可删除的内置节点 id（分区自身的删除沿用顶层内置菜单语义，不在此列） */
export const BUILTIN_SECTION_DESCENDANT_IDS: Set<string> = new Set();
{
  const walk = (nodes: NavNode[]) => {
    for (const n of nodes) {
      BUILTIN_SECTION_DESCENDANT_IDS.add(n.id);
      if (n.children) walk(n.children);
    }
  };
  for (const children of Object.values(SECTION_TREE_DEFAULTS)) walk(children);
}

function cloneSectionNode(n: NavNode): NavNode {
  return { ...n, children: n.children ? n.children.map(cloneSectionNode) : undefined };
}

/** 补齐页内分区缺失的内置子节点（用户自定义子节点保留、顺序不动，缺失的按内置顺序追加） */
function refillSectionChildren(nodes: NavNode[]): NavNode[] {
  return nodes.map((node) => {
    const defaults = SECTION_TREE_DEFAULTS[node.id];
    let withChildren = node;
    if (defaults) {
      const children = [...(node.children ?? [])];
      const present = new Set(children.map((c) => c.id));
      for (const d of defaults) {
        if (!present.has(d.id)) children.push(cloneSectionNode(d));
      }
      withChildren = { ...node, children };
    }
    if (withChildren.children?.length) {
      return { ...withChildren, children: refillSectionChildren(withChildren.children) };
    }
    return withChildren;
  });
}

const KEY = "zhiyu-nav-tree-v2";
const LEGACY_KEY = "zhiyu-nav-config";

function defaultTree(): NavNode[] {
  return NAV_ITEMS.map((item) => {
    const node: NavNode = {
      id: item.match,
      label: item.label,
      icon: item.icon,
      to: item.to,
      enabled: true,
    };
    if (SECTION_TREE_DEFAULTS[item.match]) {
      node.children = SECTION_TREE_DEFAULTS[item.match].map(cloneSectionNode);
    }
    return node;
  });
}

function sanitizeNode(raw: unknown, depth: number): NavNode | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const id = typeof r.id === "string" && r.id.trim() ? r.id.trim() : "";
  const label = typeof r.label === "string" && r.label.trim() ? r.label.trim() : "";
  if (!id || !label) return null;
  const node: NavNode = {
    id,
    label,
    icon: typeof r.icon === "string" && r.icon.trim() ? r.icon.trim() : "doc",
    enabled: r.enabled !== false,
  };
  if (typeof r.to === "string" && r.to.trim()) node.to = r.to.trim();
  if (r.custom === true) {
    node.custom = true;
    // 兜底：自定义菜单必须有落地路由
    if (!node.to) node.to = `/m/${node.id}`;
  }
  if (depth < MAX_MENU_DEPTH - 1 && Array.isArray(r.children)) {
    const children = r.children
      .map((c) => sanitizeNode(c, depth + 1))
      .filter((c): c is NavNode => c !== null);
    if (children.length) node.children = children;
  }
  return node;
}

function sanitizeTree(raw: unknown): NavNode[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((n) => sanitizeNode(n, 0)).filter((n): n is NavNode => n !== null);
}

/** 旧版扁平配置（order + labels）迁移为树形结构 */
function migrateLegacy(): NavNode[] | null {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { order?: unknown; labels?: unknown };
    if (!Array.isArray(parsed.order)) return null;
    const labels = (parsed.labels ?? {}) as Record<string, unknown>;
    const byMatch = new Map(NAV_ITEMS.map((item) => [item.match, item]));
    const tree: NavNode[] = [];
    for (const match of parsed.order) {
      if (typeof match !== "string") continue;
      const item = byMatch.get(match);
      if (!item) continue;
      const label = labels[match];
      tree.push({
        id: item.match,
        label: typeof label === "string" && label.trim() ? label.trim() : item.label,
        icon: item.icon,
        to: item.to,
        enabled: true,
      });
    }
    return tree;
  } catch {
    return null;
  }
}

/** 校验：剔除非法节点；仅首用或旧配置迁移时补齐内置菜单，用户显式删除的内置菜单不复活（可用「恢复默认」找回） */
function normalize(raw: unknown, opts: { mergeDefaults: boolean }): NavNode[] {
  let tree = refillSectionChildren(sanitizeTree(raw));
  if (!opts.mergeDefaults) return tree;
  const known = new Set<string>();
  const walk = (nodes: NavNode[]) => {
    for (const n of nodes) {
      known.add(n.id);
      if (n.children) walk(n.children);
    }
  };
  walk(tree);
  const defaults = defaultTree();
  const missing = defaults.filter((d) => !known.has(d.id));
  const merged = [...tree];
  for (const item of missing) {
    const idx = NAV_ITEMS.findIndex((i) => i.match === item.id);
    let at = -1;
    for (let j = idx - 1; j >= 0 && at < 0; j -= 1) {
      const pos = merged.findIndex((n) => n.id === NAV_ITEMS[j].match);
      if (pos >= 0) at = pos + 1;
    }
    for (let j = idx + 1; j < NAV_ITEMS.length && at < 0; j += 1) {
      const pos = merged.findIndex((n) => n.id === NAV_ITEMS[j].match);
      if (pos >= 0) at = pos;
    }
    if (at < 0) merged.push(item);
    else merged.splice(at, 0, item);
  }
  return refillSectionChildren(merged);
}

function read(): NavNode[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return normalize(JSON.parse(raw), { mergeDefaults: false });
  } catch {
    /* fallthrough */
  }
  const legacy = migrateLegacy();
  if (legacy) return normalize(legacy, { mergeDefaults: true });
  return normalize(null, { mergeDefaults: true });
}

export const navTree = ref<NavNode[]>(read());

export function saveNavTree(next: NavNode[]) {
  navTree.value = normalize(next, { mergeDefaults: false });
  try {
    localStorage.setItem(KEY, JSON.stringify(navTree.value));
  } catch {
    /* ignore */
  }
}

export function resetNavConfig() {
  try {
    localStorage.removeItem(KEY);
    localStorage.removeItem(LEGACY_KEY);
  } catch {
    /* ignore */
  }
  navTree.value = normalize(null, { mergeDefaults: true });
}

export function findNavNode(tree: NavNode[], id: string): NavNode | null {
  for (const n of tree) {
    if (n.id === id) return n;
    if (n.children) {
      const hit = findNavNode(n.children, id);
      if (hit) return hit;
    }
  }
  return null;
}

export function newNavNode(label: string): NavNode {
  const id = `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
  return {
    id,
    label,
    icon: "doc",
    to: `/m/${id}`,
    custom: true,
    enabled: true,
  };
}
