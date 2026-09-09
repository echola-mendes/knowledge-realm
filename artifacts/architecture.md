# 知域 — Agent 架构（P4 个人出行）

长期约束；实施细节见 `artifacts/execution-plan.md` 与 `docs/multi-agent/PRD-P4.md`。

## 1. 统一入口

- Agent 模式（含差旅、`task=agent|report`）**只走** `/api/agent` 与 `/api/agent/stream`。
- `/api/chat` 保持 P0 LangChain 单链，**禁止**改为 LangGraph。
- **禁止**并行第二条 travel REST API；差旅能力经 Master 子 Agent Tool 暴露。

## 2. 编排模式

**Supervisor + Agents-as-Tools**（同进程 LangGraph）：

```
/api/agent(/stream)
  → thin_intent（一次结构化：knowledge | plan | booking | chat）
  → MasterAgent（按 intent 调度 + 整合回复）
       ├── knowledge   ← Master 意图仍挂 graph.py；`task=knowledge` 入口直连 knowledge_flow（analyze→…→generate）
       ├── plan        ← itinerary_plan_agent（ReAct + travel tools）
       └── booking     ← booking_agent（ReAct + HITL 写工具）
```

- **意图 ≠ Master**：`intent.py` 只输出标签；Master 不再做完整意图识别。
- `chat`：Master 节点直接 LLM 寒暄，不调子 Agent。
- `task=report`：路由 `knowledge`，生成后可选上传 MinIO `reports/{conversation_id}/...`。
- 子 Agent 事件 **不冒泡** 打乱前端主 SSE 序列（等价 GoGo `forwardEvents(false)`）。

### 2.1 knowledge 子图（长期）

- **Agent 负责决策编排**；**`search_chunks`（经 Tool）负责** Vector+BM25→RRF→Rerank→Context Expansion。禁止在 Agent 内自建第二套检索。
- 主路径：`analyze`（simple|complex）→ Simple 单次检索 | Complex `decompose`→按 Qi 检索 → Sufficiency（V0：`len(hits)>0`）→ 仅不足 Qi `rewrite` 再检 → `merge` →（可选 `gap`）→ `generate`。
- 预算：`MAX_LOOPS` **仅计补充检索**；每 Qi 初始检索 1 次不计入；`MAX_SUB_QUESTIONS` 硬上限 5（引导 ≤3）；`MAX_EVIDENCE=10`。
- `web_search` / `search_graph`：**不进** Decomposition/Sufficiency 主流程。
- 不改 `/api/chat`；Simple **不**强行改走 Chat API。

## 3. 代码布局（禁止新建 p4/）

全部位于 `server/app/`：

| 文件 | 职责 |
|---|---|
| `intent.py` | 薄意图分类 |
| `master.py` | Supervisor 主图 + `MasterState` |
| `graph.py` | knowledge 子图（编排：Analysis / Qi / Sufficiency / Merge / Gap） |
| `plan_agent.py` | 规划子 Agent + plan tools |
| `booking_agent.py` | 预订子 Agent + booking tools |
| `travel/flyai.py` | flyai search-flight / book（Step 2/3） |
| `travel/minio_store.py` | plans / reports 上传与回看 URL |
| `tools.py` | 现有 RAG/graph/web tools；travel tools 可 re-export |

路由层仍在 `server/app/routers/master.py`，调用 `master.build_master_graph()`。

## 4. SSE 事件（Agent stream）

在现有 `token` / `citations` 之外，本批新增：

| type | 用途 |
|---|---|
| `intent` | 分类结果（调试/可选展示） |
| `progress` | 子 Agent 进度文案 |
| `travel_data` | 结构化差旅数据（含 flyai `itemList` 机票段） |
| `plan_html` | 方案页 HTML 或 URL |
| `hitl` | 待确认写操作（Step 3） |
| `citations` | 终态（扩展字段：travel、hitl、minio_url 等） |

## 5. 前端契约

- **机票卡片**：`travel_data.flights` = flyai `search-flight` 响应 `itemList`（原字段透传）；组件 `TravelResultCard.vue`。
- **方案页**：来自 `plan_itinerary` 的 `{ recommendation, comparison, total_price, options }` 渲染为 HTML/SSE `plan_html`；**不**直接用 flyai 字段。
- **酒店卡片**：独立结构；无供应商时 `kind: "placeholder"` + 提示文案。

## 6. 存储

- **Postgres**：会话/消息（现有）；`booking_record`（Step 3）；Checkpoint 仍用现有 Postgres checkpointer。
- **MinIO**（本机已部署，env 配置）：`plans/{conversation_id}/{timestamp}.html`；`reports/{conversation_id}/{timestamp}.html`。
- 连接失败：SSE 实时仍可用，提示回看不可用。

## 7. 安全与写操作

- 身份只来自 Session；`user_id` 禁止来自请求体。
- 搜索/出方案：只读，无 HITL。
- `book_*` / `cancel_*`：须经 `pending_action` HITL；Step 3 写操作限流 30/min/用户。

## 8. 决策审计埋点（Trace.md V1.1）

- 新增 Agent 路径时**必须**接入 `app/audit/recorder.py` 的 `DecisionRecorder`：经 `RunnableConfig.configurable["decision_recorder"]` 注入子图节点（注解须严格为 `RunnableConfig`）。
- run 行经主流程会话 savepoint 落库（随主事务提交）；spans 与终态由 Recorder 用独立会话写。
- Recorder 公开方法吞异常——**任何审计故障不得影响主回答**。
- **node_type** 仍为 `route` / `retrieve` / `generate`；knowledge 用 `decision.step`（`analyze`/`decompose`/`retrieve_qi`/`sufficiency`/`rewrite`/`merge`/`gap`/`generate`）+ **`input`/`output`** 区分步骤；retrieve/sufficiency/merge 须带命中摘要 `evidence_refs`（id+excerpt，不塞 parent 全文）。
- 能力与埋点**同步**落地，禁止后补；chat 模式审计口径不变。

## 9. 切块存储：Parent-Child（V1）

长期数据约束（一张 `document_chunk`，不另建向量表）：

- `role`：`parent` | `child`；存量默认 `child`
- `parent_id`：child → parent；短 section 仅一行 `role=child` 且 `parent_id=null`（无空父）
- **检索单位**：仅 child（向量 / BM25 / RRF / Rerank）；parent **无 embedding、不进 ES**
- **生成上下文**：默认 `parent.content`；无 parent / 未 reindex → 降级 V0 同 heading 扩窗
- 导入页切的是 child 策略，与「命中后组装 parent」分维；V1 不做组装 UI
