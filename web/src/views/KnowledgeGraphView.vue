<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  listKnowledgeBases,
  getKnowledgeGraph,
  searchKnowledgeGraphDetails,
  getGraphDocuments,
  type KnowledgeBase,
  type KnowledgeGraph,
  type GraphEntity,
  type GraphLink,
  type GraphSearchDetailOut,
  type GraphDocumentOut,
  type SearchHit,
} from "../api";
import Icon from "../components/Icon.vue";

interface SimNode extends GraphEntity {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface SimLink {
  source: number;
  target: number;
  rel: string;
  document_id: string | null;
}

interface LinkPath {
  links: GraphLink[];
}

const route = useRoute();
const router = useRouter();

const kbs = ref<KnowledgeBase[]>([]);
const selectedKbId = ref<string>("");
const graph = ref<KnowledgeGraph>({ entities: [], links: [] });
const loading = ref(false);
const error = ref("");

const entityTypeFilter = ref("");
const relationTypeFilter = ref("");
const searchInput = ref("");

const activeTab = ref<"detail" | "path" | "neighbor" | "search">("detail");
const selectedNodeId = ref<string | null>(null);

const containerRef = ref<HTMLDivElement | null>(null);
const size = ref({ width: 800, height: 500 });
const scale = ref(1);
const isFullscreen = ref(false);

const pathStartId = ref<string>("");
const pathEndId = ref<string>("");
const pathMaxHops = ref<1 | 2 | 3>(2);
const pathRel = ref("");
const foundPaths = ref<LinkPath[]>([]);

const expandNeighbors1 = ref(true);
const expandNeighbors2 = ref(false);

const assistQuery = ref("");
const assistDepth = ref<1 | 2 | 3>(2);
const assistRel = ref("");
const assistLoading = ref(false);
const assistResult = ref<GraphSearchDetailOut | null>(null);

const sourceDocs = ref<Record<string, GraphDocumentOut>>({});
const hoveredLinkKey = ref<string | null>(null);

function linkKey(link: SimLink) {
  const a = simNodes[link.source];
  const b = simNodes[link.target];
  if (!a || !b) return "";
  return `${a.id}|${b.id}|${link.rel}|${link.document_id}`;
}

const typeColor = (type: string) => {
  const map: Record<string, string> = {
    concept: "#60a5fa",
    entity: "#34d399",
    event: "#fbbf24",
    person: "#f87171",
    organization: "#a78bfa",
    location: "#22d3ee",
    object: "#9ca3af",
    system: "#f472b6",
  };
  return map[type] || "#9ca3af";
};

function hashId(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h << 5) - h + id.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h) / 2147483647;
}

let simNodes: SimNode[] = [];
let simLinks: SimLink[] = [];
let rafId: number | null = null;

const entityTypes = computed(() => Array.from(new Set(graph.value.entities.map((e) => e.type))).sort());
const relationTypes = computed(() => Array.from(new Set(graph.value.links.map((l) => l.rel))).sort());

const filteredEntityIds = computed(() => {
  const q = searchInput.value.trim().toLowerCase();
  return new Set(
    graph.value.entities
      .filter((e) => {
        if (entityTypeFilter.value && e.type !== entityTypeFilter.value) return false;
        if (!q) return true;
        return e.name.toLowerCase().includes(q) || e.type.toLowerCase().includes(q);
      })
      .map((e) => e.id),
  );
});

const filteredLinkIds = computed(() => {
  const q = searchInput.value.trim().toLowerCase();
  return new Set(
    graph.value.links
      .filter((l) => {
        if (relationTypeFilter.value && l.rel !== relationTypeFilter.value) return false;
        if (!q) return true;
        return l.rel.toLowerCase().includes(q);
      })
      .map((l) => `${l.from_id}|${l.to_id}|${l.rel}|${l.document_id}`),
  );
});

const visibleNodes = computed(() => simNodes.filter((n) => filteredEntityIds.value.has(n.id)));
const visibleLinks = computed(() =>
  simLinks.filter((l) => {
    const fromVisible = filteredEntityIds.value.has(simNodes[l.source]?.id);
    const toVisible = filteredEntityIds.value.has(simNodes[l.target]?.id);
    if (!fromVisible || !toVisible) return false;
    const key = `${graph.value.links.find((gl) => gl.from_id === simNodes[l.source]?.id && gl.to_id === simNodes[l.target]?.id && gl.rel === l.rel)?.from_id}|${graph.value.links.find((gl) => gl.from_id === simNodes[l.source]?.id && gl.to_id === simNodes[l.target]?.id && gl.rel === l.rel)?.to_id}|${l.rel}|${l.document_id}`;
    return filteredLinkIds.value.has(key);
  }),
);

const stats = computed(() => {
  return {
    totalNodes: graph.value.entities.length,
    totalLinks: graph.value.links.length,
    shownNodes: visibleNodes.value.length,
    shownLinks: visibleLinks.value.length,
    entityTypeCount: entityTypes.value.length,
    relationTypeCount: relationTypes.value.length,
  };
});

const selectedNode = computed(() =>
  selectedNodeId.value ? graph.value.entities.find((e) => e.id === selectedNodeId.value) || null : null,
);

function initSimulation() {
  const { width, height } = size.value;
  const cx = width / 2;
  const cy = height / 2;
  const idToIndex = new Map(graph.value.entities.map((e, i) => [e.id, i]));
  simNodes = graph.value.entities.map((e) => ({
    ...e,
    x: cx + (hashId(e.id) - 0.5) * 80,
    y: cy + (hashId(e.id + "_y") - 0.5) * 80,
    vx: 0,
    vy: 0,
  }));
  simLinks = graph.value.links
    .map((l) => {
      const s = idToIndex.get(l.from_id);
      const t = idToIndex.get(l.to_id);
      if (s === undefined || t === undefined) return null;
      return { source: s, target: t, rel: l.rel, document_id: l.document_id };
    })
    .filter((l): l is SimLink => l !== null);
  startSimulation();
}

function startSimulation() {
  if (rafId !== null) cancelAnimationFrame(rafId);
  let alpha = 1;
  const minAlpha = 0.02;
  const cooling = 0.985;
  const centerStrength = 0.012;
  const repel = 6000;
  const linkDistance = 380;
  const spring = 0.0025;
  const nodeRadius = 36;
  const damping = 0.88;
  const { width, height } = size.value;

  const step = () => {
    const cx = width / 2;
    const cy = height / 2;
    for (let i = 0; i < simNodes.length; i++) {
      const a = simNodes[i];
      a.vx += (cx - a.x) * centerStrength * alpha;
      a.vy += (cy - a.y) * centerStrength * alpha;
    }
    for (let i = 0; i < simNodes.length; i++) {
      for (let j = i + 1; j < simNodes.length; j++) {
        const a = simNodes[i];
        const b = simNodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (repel / (dist * dist)) * alpha;
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
        // 碰撞：避免节点重叠
        const overlap = nodeRadius * 2 - dist;
        if (overlap > 0) {
          const separate = (overlap * 0.05 + 0.5) * alpha;
          const sx = (dx / dist) * separate;
          const sy = (dy / dist) * separate;
          a.vx += sx;
          a.vy += sy;
          b.vx -= sx;
          b.vy -= sy;
        }
      }
    }
    for (const link of simLinks) {
      const a = simNodes[link.source];
      const b = simNodes[link.target];
      if (!a || !b) continue;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (dist - linkDistance) * spring * alpha;
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }
    for (const n of simNodes) {
      n.vx *= damping;
      n.vy *= damping;
      n.x += n.vx;
      n.y += n.vy;
      n.x = Math.max(16, Math.min(width - 16, n.x));
      n.y = Math.max(16, Math.min(height - 16, n.y));
    }
    alpha *= cooling;
    if (alpha > minAlpha) {
      rafId = requestAnimationFrame(step);
    } else {
      rafId = null;
    }
  };
  step();
}

async function loadGraph() {
  if (!selectedKbId.value) return;
  loading.value = true;
  error.value = "";
  try {
    const opts: { knowledgeBaseId?: string; documentId?: string } = { knowledgeBaseId: selectedKbId.value };
    if (route.query.documentId && String(route.query.documentId)) {
      opts.documentId = String(route.query.documentId);
    }
    graph.value = await getKnowledgeGraph(opts);
    await nextTick();
    initSimulation();
    if (route.query.focusEntityId) {
      const focus = String(route.query.focusEntityId);
      if (graph.value.entities.some((e) => e.id === focus)) {
        selectedNodeId.value = focus;
        activeTab.value = "detail";
      }
    } else if (route.query.documentId && graph.value.entities.length) {
      selectedNodeId.value = graph.value.entities[0].id;
      activeTab.value = "detail";
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载图谱失败";
  } finally {
    loading.value = false;
  }
}

function runSearch() {
  // 搜索输入已绑定到本地过滤条件，图谱自动筛选
}

function resetFilters() {
  entityTypeFilter.value = "";
  relationTypeFilter.value = "";
  searchInput.value = "";
}

function updateSize() {
  const el = containerRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  size.value = { width: Math.max(320, rect.width), height: Math.max(320, rect.height) };
  if (simNodes.length) startSimulation();
}

function zoomIn() {
  scale.value = Math.min(scale.value * 1.2, 5);
}
function zoomOut() {
  scale.value = Math.max(scale.value / 1.2, 0.2);
}
function fitCanvas() {
  const nodes = visibleNodes.value;
  if (!nodes.length) {
    scale.value = 1;
    return;
  }
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const minX = Math.min(...xs) - 40;
  const maxX = Math.max(...xs) + 40;
  const minY = Math.min(...ys) - 40;
  const maxY = Math.max(...ys) + 40;
  const contentW = Math.max(1, maxX - minX);
  const contentH = Math.max(1, maxY - minY);
  const scaleX = size.value.width / contentW;
  const scaleY = size.value.height / contentH;
  scale.value = Math.min(scaleX, scaleY, 1);
}
function relayout() {
  initSimulation();
}
async function toggleFullscreen() {
  const el = containerRef.value;
  if (!el) return;
  try {
    if (!document.fullscreenElement) {
      await el.requestFullscreen();
      isFullscreen.value = true;
    } else {
      await document.exitFullscreen();
      isFullscreen.value = false;
    }
  } catch {
    isFullscreen.value = false;
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement;
  nextTick(updateSize);
}

const highlightedNodeIds = computed(() => {
  const set = new Set<string>();
  if (selectedNodeId.value) set.add(selectedNodeId.value);
  if (assistResult.value) {
    assistResult.value.entities.forEach((e) => set.add(e.id));
  }
  foundPaths.value.forEach((p) => {
    p.links.forEach((l) => {
      set.add(l.from_id);
      set.add(l.to_id);
    });
  });
  return set;
});

const highlightedLinkKeys = computed(() => {
  const set = new Set<string>();
  foundPaths.value.forEach((p) => {
    p.links.forEach((l) => set.add(`${l.from_id}|${l.to_id}|${l.rel}|${l.document_id}`));
  });
  if (assistResult.value) {
    assistResult.value.links.forEach((l) => set.add(`${l.from_id}|${l.to_id}|${l.rel}|${l.document_id}`));
  }
  return set;
});

function nodeClass(n: SimNode) {
  const isSelected = selectedNodeId.value === n.id;
  const isHighlighted = highlightedNodeIds.value.has(n.id);
  const hasHighlight = highlightedNodeIds.value.size > 0 || highlightedLinkKeys.value.size > 0;
  return {
    selected: isSelected,
    highlighted: isHighlighted,
    dim: hasHighlight && !isHighlighted && !isSelected,
  };
}

function linkClass(l: SimLink) {
  const gl = graph.value.links.find(
    (gl) => gl.from_id === simNodes[l.source]?.id && gl.to_id === simNodes[l.target]?.id && gl.rel === l.rel,
  );
  const key = gl ? `${gl.from_id}|${gl.to_id}|${gl.rel}|${gl.document_id}` : "";
  const highlighted = highlightedLinkKeys.value.has(key);
  return {
    highlighted,
    dim: highlightedNodeIds.value.size > 0 && !highlighted && !highlightedNodeIds.value.has(simNodes[l.source]?.id) && !highlightedNodeIds.value.has(simNodes[l.target]?.id),
  };
}

function selectNode(id: string) {
  selectedNodeId.value = id;
  activeTab.value = "detail";
  loadSourceDocsForNode(id);
}

async function loadSourceDocsForNode(id: string) {
  const linkDocIds = Array.from(
    new Set(
      graph.value.links
        .filter((l) => l.from_id === id || l.to_id === id)
        .map((l) => l.document_id)
        .filter((d): d is string => !!d),
    ),
  );
  if (!linkDocIds.length) {
    sourceDocs.value = {};
    return;
  }
  try {
    const docs = await getGraphDocuments(linkDocIds);
    sourceDocs.value = Object.fromEntries(docs.map((d) => [d.document_id, d]));
  } catch {
    sourceDocs.value = {};
  }
}

function nodeRelations(id: string) {
  return graph.value.links.filter((l) => l.from_id === id || l.to_id === id);
}

function neighborIds(id: string, hops: 1 | 2) {
  const hop1 = new Set<string>();
  graph.value.links.forEach((l) => {
    if (l.from_id === id) hop1.add(l.to_id);
    if (l.to_id === id) hop1.add(l.from_id);
  });
  if (hops === 1) return hop1;
  const hop2 = new Set<string>();
  hop1.forEach((nid) => {
    graph.value.links.forEach((l) => {
      if (l.from_id === nid && l.to_id !== id) hop2.add(l.to_id);
      if (l.to_id === nid && l.from_id !== id) hop2.add(l.from_id);
    });
  });
  return hop2;
}

function findPaths() {
  foundPaths.value = [];
  if (!pathStartId.value || !pathEndId.value || pathStartId.value === pathEndId.value) return;
  const adj: Record<string, GraphLink[]> = {};
  graph.value.links.forEach((l) => {
    if (pathRel.value && l.rel !== pathRel.value) return;
    adj[l.from_id] = adj[l.from_id] || [];
    adj[l.to_id] = adj[l.to_id] || [];
    adj[l.from_id].push(l);
    adj[l.to_id].push(l);
  });
  const results: LinkPath[] = [];
  const visited = new Set<string>();
  function dfs(current: string, path: GraphLink[]) {
    if (results.length >= 10) return;
    if (path.length > pathMaxHops.value) return;
    if (current === pathEndId.value && path.length > 0) {
      results.push({ links: [...path] });
      return;
    }
    for (const link of adj[current] || []) {
      const next = link.from_id === current ? link.to_id : link.from_id;
      if (visited.has(next)) continue;
      visited.add(next);
      dfs(next, [...path, link]);
      visited.delete(next);
    }
  }
  visited.add(pathStartId.value);
  dfs(pathStartId.value, []);
  foundPaths.value = results;
}

function highlightPath(path: LinkPath) {
  foundPaths.value = [path];
}

async function runAssistSearch() {
  const q = assistQuery.value.trim();
  if (!q || !selectedKbId.value) return;
  assistLoading.value = true;
  try {
    assistResult.value = await searchKnowledgeGraphDetails(
      selectedKbId.value,
      q,
      assistDepth.value,
      assistRel.value || undefined,
      10,
    );
  } catch (e) {
    assistResult.value = null;
  } finally {
    assistLoading.value = false;
  }
}

function highlightAssist() {
  if (!assistResult.value) return;
  // entities/links already reflected in computed highlights
}

function resetAssist() {
  assistQuery.value = "";
  assistResult.value = null;
}

function formatDate(d: string | null | undefined) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("zh-CN");
  } catch {
    return "—";
  }
}

onMounted(async () => {
  updateSize();
  window.addEventListener("resize", updateSize);
  document.addEventListener("fullscreenchange", onFullscreenChange);
  try {
    kbs.value = await listKnowledgeBases();
    const qKb = route.query.knowledgeBaseId ? String(route.query.knowledgeBaseId) : "";
    const kb = kbs.value.find((k) => k.id === qKb) || kbs.value.find((k) => k.is_default) || kbs.value[0];
    if (kb) selectedKbId.value = kb.id;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载知识库失败";
  }
});

onUnmounted(() => {
  window.removeEventListener("resize", updateSize);
  document.removeEventListener("fullscreenchange", onFullscreenChange);
  if (rafId !== null) cancelAnimationFrame(rafId);
});

watch(selectedKbId, () => {
  router.replace({ query: { ...route.query, knowledgeBaseId: selectedKbId.value || undefined } });
  loadGraph();
});

watch(selectedNodeId, (id) => {
  if (id) loadSourceDocsForNode(id);
});
</script>

<template>
  <main class="page kg-page">
    <div class="page-head">
      <div>
        <h1>知识图谱</h1>
        <p class="sub">浏览已选知识库中的实体与关系，支持筛选、路径探索与检索辅助。</p>
      </div>
    </div>
    <header class="kg-header">
      <div class="kg-toolbar">
        <select v-model="selectedKbId" :disabled="loading">
          <option value="">选择知识库</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
        <select v-model="entityTypeFilter">
          <option value="">全部实体类型</option>
          <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <select v-model="relationTypeFilter">
          <option value="">全部关系类型</option>
          <option v-for="r in relationTypes" :key="r" :value="r">{{ r }}</option>
        </select>
        <input v-model="searchInput" type="text" placeholder="搜索实体或关系…" @keydown.enter="runSearch" />
        <button type="button" @click="runSearch">搜索</button>
        <button type="button" class="secondary" @click="resetFilters">重置</button>
      </div>
    </header>

    <div v-if="error" class="kg-error">{{ error }}</div>

    <div class="kg-body">
      <div ref="containerRef" class="kg-canvas" :class="{ fullscreen: isFullscreen }">
        <div class="kg-controls">
          <button type="button" title="放大" data-tip="放大" @click="zoomIn"><Icon name="plus" /></button>
          <button type="button" title="缩小" data-tip="缩小" @click="zoomOut"><Icon name="minus" /></button>
          <button type="button" title="适应画布" data-tip="适应画布" @click="fitCanvas"><Icon name="maximize" /></button>
          <button type="button" title="重新布局" data-tip="重新布局" @click="relayout"><Icon name="refresh" /></button>
          <button type="button" title="全屏" data-tip="全屏" @click="toggleFullscreen"><Icon name="fullscreen" /></button>
        </div>
        <svg :width="size.width" :height="size.height">
          <g :transform="`translate(${size.width / 2}, ${size.height / 2}) scale(${scale}) translate(${-size.width / 2}, ${-size.height / 2})`">
            <g class="links">
              <g
                v-for="(link, i) in simLinks"
                :key="`l-${i}`"
                class="link-group"
                @mouseenter="hoveredLinkKey = linkKey(link)"
                @mouseleave="hoveredLinkKey = null"
              >
                <line
                  :x1="simNodes[link.source]?.x"
                  :y1="simNodes[link.source]?.y"
                  :x2="simNodes[link.target]?.x"
                  :y2="simNodes[link.target]?.y"
                  :class="linkClass(link)"
                />
                <text
                  v-if="linkKey(link) && (highlightedLinkKeys.has(linkKey(link)) || hoveredLinkKey === linkKey(link))"
                  class="link-label"
                  :x="(simNodes[link.source]?.x + simNodes[link.target]?.x) / 2"
                  :y="(simNodes[link.source]?.y + simNodes[link.target]?.y) / 2"
                  text-anchor="middle"
                  dy="-4"
                >
                  {{ link.rel }}
                </text>
              </g>
            </g>
            <g class="nodes">
              <g
                v-for="n in simNodes"
                :key="n.id"
                class="node"
                :class="nodeClass(n)"
                :transform="`translate(${n.x}, ${n.y})`"
                @click.stop="selectNode(n.id)"
              >
                <circle r="8" :fill="typeColor(n.type)" />
                <text y="22" text-anchor="middle">{{ n.name }}</text>
              </g>
            </g>
          </g>
        </svg>
        <div class="kg-stats">
          节点 {{ stats.totalNodes }} · 关系 {{ stats.totalLinks }} ·
          实体类型 {{ stats.entityTypeCount }} · 关系类型 {{ stats.relationTypeCount }} ·
          显示 {{ stats.shownNodes }} / {{ stats.totalNodes }}
        </div>
        <div v-if="loading" class="kg-loading">加载中…</div>
        <div v-else-if="!simNodes.length" class="kg-empty">该知识库暂无图谱数据</div>
      </div>

      <aside class="kg-side">
        <div class="kg-tabs">
          <button
            v-for="tab in [
              { key: 'detail', label: '节点详情' },
              { key: 'path', label: '路径探索' },
              { key: 'neighbor', label: '邻居节点' },
              { key: 'search', label: '检索辅助' },
            ]"
            :key="tab.key"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key as any"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- 节点详情 -->
        <div v-if="activeTab === 'detail'" class="kg-tab-content">
          <div v-if="selectedNode" class="kg-panel">
            <h3>{{ selectedNode.name }}</h3>
            <span class="type-badge" :style="{ background: typeColor(selectedNode.type) }">{{ selectedNode.type }}</span>
            <div class="meta-grid">
              <div><span>首次出现</span><span>{{ formatDate(selectedNode.created_at) }}</span></div>
              <div><span>来源文档</span><span>{{ selectedNode.source_doc_count || 0 }} 个</span></div>
            </div>
            <h4>关联关系</h4>
            <ul v-if="nodeRelations(selectedNode.id).length" class="rel-list">
              <li
                v-for="rel in nodeRelations(selectedNode.id)"
                :key="`${rel.from_id}-${rel.to_id}-${rel.rel}`"
                @click="selectNode(rel.from_id === selectedNode.id ? rel.to_id : rel.from_id)"
              >
                {{ rel.from_id === selectedNode.id ? "→" : "←" }}
                {{ graph.entities.find((e) => e.id === (rel.from_id === selectedNode.id ? rel.to_id : rel.from_id))?.name }}
                <span class="rel-tag">{{ rel.rel }}</span>
              </li>
            </ul>
            <p v-else class="muted">无关联关系</p>
            <h4>相关文档</h4>
            <ul v-if="Object.keys(sourceDocs).length" class="doc-list">
              <li v-for="doc in Object.values(sourceDocs)" :key="doc.document_id">
                <RouterLink :to="`/documents/${doc.document_id}`">{{ doc.document_name }}</RouterLink>
                <span class="version">v{{ doc.version }}</span>
              </li>
            </ul>
            <p v-else class="muted">无来源文档</p>
          </div>
          <div v-else class="kg-panel muted">点击图谱节点查看详情</div>
        </div>

        <!-- 路径探索 -->
        <div v-else-if="activeTab === 'path'" class="kg-tab-content">
          <div class="kg-panel">
            <label>起点实体</label>
            <select v-model="pathStartId">
              <option value="">选择</option>
              <option v-for="e in graph.entities" :key="e.id" :value="e.id">{{ e.name }}</option>
            </select>
            <label>终点实体</label>
            <select v-model="pathEndId">
              <option value="">选择</option>
              <option v-for="e in graph.entities" :key="e.id" :value="e.id">{{ e.name }}</option>
            </select>
            <label>最大跳数</label>
            <div class="hop-btns">
              <button v-for="h in [1,2,3]" :key="h" :class="{ active: pathMaxHops === h }" @click="pathMaxHops = h">{{ h }} 跳</button>
            </div>
            <label>关系过滤</label>
            <select v-model="pathRel">
              <option value="">全部关系</option>
              <option v-for="r in relationTypes" :key="r" :value="r">{{ r }}</option>
            </select>
            <button type="button" class="primary" @click="findPaths">查找路径</button>
            <div v-if="foundPaths.length" class="path-results">
              <div v-for="(path, idx) in foundPaths" :key="idx" class="path-card" @click="highlightPath(path)">
                <div v-for="(step, sidx) in path.links" :key="sidx" class="path-step">
                  {{ graph.entities.find((e) => e.id === step.from_id)?.name }}
                  <span class="rel-arrow">→ {{ step.rel }}</span>
                </div>
                <div class="path-step">
                  {{ graph.entities.find((e) => e.id === path.links[path.links.length - 1].to_id)?.name }}
                </div>
              </div>
            </div>
            <p v-else-if="pathStartId && pathEndId" class="muted">未找到路径</p>
          </div>
        </div>

        <!-- 邻居节点 -->
        <div v-else-if="activeTab === 'neighbor'" class="kg-tab-content">
          <div v-if="selectedNode" class="kg-panel">
            <h4>一跳邻居</h4>
            <button class="toggle-btn" @click="expandNeighbors1 = !expandNeighbors1">{{ expandNeighbors1 ? "收起" : "展开" }}</button>
            <ul v-if="expandNeighbors1" class="neighbor-list">
              <li
                v-for="id in Array.from(neighborIds(selectedNode.id, 1))"
                :key="id"
                @click="selectNode(id)"
              >
                {{ graph.entities.find((e) => e.id === id)?.name }}
              </li>
            </ul>
            <h4>二跳邻居</h4>
            <button class="toggle-btn" @click="expandNeighbors2 = !expandNeighbors2">{{ expandNeighbors2 ? "收起" : "展开" }}</button>
            <ul v-if="expandNeighbors2" class="neighbor-list">
              <li
                v-for="id in Array.from(neighborIds(selectedNode.id, 2)).slice(0, 20)"
                :key="id"
                @click="selectNode(id)"
              >
                {{ graph.entities.find((e) => e.id === id)?.name }}
              </li>
            </ul>
          </div>
          <div v-else class="kg-panel muted">点击节点查看邻居</div>
        </div>

        <!-- 检索辅助 -->
        <div v-else-if="activeTab === 'search'" class="kg-tab-content">
          <div class="kg-panel">
            <input v-model="assistQuery" type="text" placeholder="输入问题，例如：员工请假需要什么？" />
            <label>检索深度</label>
            <div class="hop-btns">
              <button v-for="h in [1,2,3]" :key="h" :class="{ active: assistDepth === h }" @click="assistDepth = h">{{ h }} 跳</button>
            </div>
            <label>关系过滤</label>
            <select v-model="assistRel">
              <option value="">全部关系</option>
              <option v-for="r in relationTypes" :key="r" :value="r">{{ r }}</option>
            </select>
            <button type="button" class="primary" :disabled="assistLoading" @click="runAssistSearch">在图谱中检索</button>
            <button type="button" class="secondary" @click="resetAssist">重置</button>

            <div v-if="assistResult" class="assist-results">
              <h4>命中路径</h4>
              <div v-for="(path, idx) in assistResult.paths" :key="idx" class="path-card" @click="highlightAssist">
                <span v-for="(e, eidx) in path.entities" :key="e.id">
                  {{ e.name }}<span v-if="eidx < path.rels.length"> → {{ path.rels[eidx] }} → </span>
                </span>
              </div>
              <h4>命中实体</h4>
              <ul class="entity-list">
                <li v-for="e in assistResult.entities" :key="e.id" @click="selectNode(e.id)">{{ e.name }}</li>
              </ul>
              <h4>相关文档</h4>
              <ul class="doc-list">
                <li v-for="doc in assistResult.documents" :key="doc.chunk_id">
                  <RouterLink :to="`/documents/${doc.document_id}`">{{ doc.document_name }}</RouterLink>
                  <span class="score">{{ doc.score.toFixed(2) }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.kg-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 1rem 1.25rem;
  box-sizing: border-box;
  font-size: 12.5px;
  background: transparent;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.kg-page .page-head {
  margin-bottom: 1rem;
  flex-shrink: 0;
}
.kg-page h1 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 0.25rem;
}
.kg-page .sub {
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--muted);
  margin: 0;
}
.kg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.45rem;
  flex-shrink: 0;
}
.kg-toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
.kg-toolbar select,
.kg-toolbar input,
.kg-toolbar button {
  padding: 0.35rem 0.6rem;
  border-radius: 0.4rem;
  border: 1px solid var(--border, #d1d5db);
  background: var(--bg, #fff);
  color: var(--text, #111);
  font-size: 0.85rem;
}
.kg-toolbar button {
  cursor: pointer;
  background: var(--primary, #2563eb);
  color: #fff;
  border-color: var(--primary, #2563eb);
}
.kg-toolbar button.secondary {
  background: var(--bg-soft, #f3f4f6);
  color: var(--text, #111);
  border-color: var(--border, #d1d5db);
}
.kg-error {
  color: #dc2626;
  margin-bottom: 0.5rem;
}
.kg-body {
  display: flex;
  flex: 1;
  gap: 0.75rem;
  min-height: 0;
}
.kg-canvas {
  flex: 1;
  position: relative;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 0.5rem;
  overflow: hidden;
  background: var(--bg-soft, #f9fafb);
}
.kg-canvas svg {
  display: block;
  width: 100%;
  height: 100%;
}
.kg-controls {
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  z-index: 2;
}
.kg-controls button {
  width: 2rem;
  height: 2rem;
  border-radius: 0.4rem;
  border: 1px solid var(--border, #d1d5db);
  background: var(--bg, #fff);
  color: var(--text, #111);
  display: grid;
  place-items: center;
  cursor: pointer;
}
.kg-controls button :deep(.ico) {
  width: 1rem;
  height: 1rem;
}
.kg-controls button::after {
  content: attr(data-tip);
  position: absolute;
  left: calc(100% + 0.45rem);
  top: 50%;
  transform: translateY(-50%);
  padding: 0.25rem 0.5rem;
  border-radius: 0.3rem;
  background: rgba(31, 41, 55, 0.9);
  color: #fff;
  font-size: 0.72rem;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s;
  z-index: 3;
}
.kg-controls button:hover::after {
  opacity: 1;
}
.links line {
  stroke: var(--border-strong, #9ca3af);
  stroke-width: 1.2;
  opacity: 0.35;
  transition: opacity 0.2s;
}
.link-group {
  cursor: pointer;
}
.link-label {
  font-size: 10px;
  fill: var(--primary, #2563eb);
  pointer-events: none;
  text-shadow: 0 0 3px rgba(255, 255, 255, 0.9);
}
.links line.highlighted {
  stroke: var(--primary, #2563eb);
  stroke-width: 2.5;
  opacity: 1;
}
.links line.dim {
  opacity: 0.15;
}
.nodes .node {
  cursor: pointer;
  transition: opacity 0.2s;
}
.nodes .node text {
  font-size: 11px;
  fill: var(--text, #111);
  pointer-events: none;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.9);
  stroke-width: 2.5px;
}
.nodes .node.selected circle {
  stroke: #111827;
  stroke-width: 3;
}
.nodes .node.highlighted circle {
  stroke: var(--primary, #2563eb);
  stroke-width: 2.5;
}
.nodes .node.dim {
  opacity: 0.15;
}
.kg-stats {
  position: absolute;
  left: 0.75rem;
  bottom: 0.75rem;
  padding: 0.35rem 0.6rem;
  border-radius: 0.4rem;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--border, #e5e7eb);
  font-size: 0.75rem;
  color: var(--muted, #6b7280);
}
.kg-loading,
.kg-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--muted, #6b7280);
}
.kg-side {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow: hidden;
}
.kg-tabs {
  display: flex;
  gap: 0.25rem;
  border-bottom: 1px solid var(--border, #e5e7eb);
}
.kg-tabs button {
  flex: 1;
  padding: 0.5rem 0.25rem;
  border: none;
  background: transparent;
  color: var(--muted, #6b7280);
  font-size: 0.8rem;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.kg-tabs button.active {
  color: var(--primary, #2563eb);
  border-bottom-color: var(--primary, #2563eb);
  font-weight: 600;
}
.kg-tab-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.kg-panel {
  background: var(--bg, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 0.5rem;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.kg-panel h3,
.kg-panel h4 {
  margin: 0;
  font-size: 0.95rem;
}
.kg-panel label {
  font-size: 0.75rem;
  color: var(--muted, #6b7280);
}
.kg-panel select,
.kg-panel input {
  padding: 0.35rem 0.5rem;
  border-radius: 0.35rem;
  border: 1px solid var(--border, #d1d5db);
  font-size: 0.85rem;
}
.kg-panel button.primary {
  background: var(--primary, #2563eb);
  color: #fff;
  border: 1px solid var(--primary, #2563eb);
  border-radius: 0.35rem;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
}
.kg-panel button.secondary {
  background: var(--bg-soft, #f3f4f6);
  border: 1px solid var(--border, #d1d5db);
  border-radius: 0.35rem;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
}
.kg-panel button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.type-badge {
  display: inline-block;
  color: #fff;
  font-size: 0.7rem;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  width: fit-content;
}
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
  font-size: 0.8rem;
}
.meta-grid > div {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.meta-grid span:first-child {
  color: var(--muted, #6b7280);
}
.rel-list,
.doc-list,
.entity-list,
.neighbor-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.85rem;
}
.rel-list li,
.doc-list li,
.entity-list li,
.neighbor-list li {
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--border, #f3f4f6);
  cursor: pointer;
}
.rel-list li:hover,
.neighbor-list li:hover,
.entity-list li:hover {
  color: var(--primary, #2563eb);
}
.rel-tag {
  margin-left: 0.3rem;
  padding: 0.05rem 0.3rem;
  border-radius: 0.25rem;
  background: var(--bg-soft, #f3f4f6);
  color: var(--muted, #6b7280);
  font-size: 0.7rem;
}
.version,
.score {
  margin-left: 0.4rem;
  color: var(--muted, #6b7280);
  font-size: 0.75rem;
}
.hop-btns {
  display: flex;
  gap: 0.35rem;
}
.hop-btns button {
  flex: 1;
  padding: 0.3rem;
  border: 1px solid var(--border, #d1d5db);
  background: var(--bg, #fff);
  border-radius: 0.3rem;
  cursor: pointer;
  font-size: 0.8rem;
}
.hop-btns button.active {
  background: var(--primary, #2563eb);
  color: #fff;
  border-color: var(--primary, #2563eb);
}
.path-results {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.path-card {
  padding: 0.5rem;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 0.35rem;
  background: var(--bg-soft, #f9fafb);
  font-size: 0.8rem;
  cursor: pointer;
}
.path-card:hover {
  border-color: var(--primary, #2563eb);
}
.path-step {
  padding: 0.15rem 0;
}
.rel-arrow {
  color: var(--primary, #2563eb);
}
.assist-results {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.assist-results h4 {
  font-size: 0.85rem;
  margin: 0.25rem 0 0;
}
.toggle-btn {
  background: transparent;
  border: none;
  color: var(--primary, #2563eb);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
  width: fit-content;
}
.muted {
  color: var(--muted, #6b7280);
  font-size: 0.8rem;
}
.kg-canvas.fullscreen {
  border-radius: 0;
}
</style>
