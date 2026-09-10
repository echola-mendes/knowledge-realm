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
  → task=knowledge → knowledge_flow（Workflow；非 Tool Calling）
  → task=react    → graph.py（标准 Tool Calling ReAct）
  → task=agent|report
       → thin_intent（knowledge | plan | booking | chat）
       → MasterAgent
            ├── knowledge ← build_graph()（与 task=react 共用 graph.py；本期不接决策审计）
            ├── plan      ← plan_agent（手写 JSON / 自有图；暂不改）
            └── booking   ← booking_agent（手写 JSON + HITL；暂不改）
```

- **意图 ≠ Master**：`intent.py` 只输出标签；Master 不再做完整意图识别。
- `chat`：Master 节点直接 LLM 寒暄，不调子 Agent。
- `task=report`：路由 `knowledge`，生成后可选上传 MinIO `reports/{conversation_id}/...`。
- 子 Agent 事件 **不冒泡** 打乱前端主 SSE 序列（等价 GoGo `forwardEvents(false)`）。

### 2.1 knowledge_flow（长期，`task=knowledge`）

- **工作流编排**（analyze / Simple·Complex / decompose / sufficiency / rewrite / merge / gap / generate）；节点内**直接调**检索函数，**不是** LLM `bind_tools`。
- **`search_chunks`（经 Tool 函数）负责** Vector+BM25→RRF→Rerank→Context Expansion。禁止在 Agent 内自建第二套检索。
- 预算：`MAX_LOOPS` **仅计补充检索**；每 Qi 初始检索 1 次不计入；`MAX_SUB_QUESTIONS` 硬上限 5（引导 ≤3）；`MAX_EVIDENCE=10`。
- **Merge 去重键**：`chunk_id`（禁止再按 `parent_id` 压成 1 条）。
- `web_search` / `search_graph`：**不进** Decomposition/Sufficiency 主流程。
- 不改 `/api/chat`；Simple **不**强行改走 Chat API。

### 2.2 graph.py ReAct（长期，`task=react` + Master knowledge）

- 标准循环：`bind_tools` → `AIMessage.tool_calls` → `ToolNode` → `ToolMessage` → …；无 tool_calls 时 **content 即终答**（无手写 JSON `action` 路由）。
- 工具包：`app/agent/tools/`（一工具一模块 + `registry.py`）；运行时经 `configurable` 注入 `session`/`user_id`/`conversation_id`/`knowledge_base_id`；**禁止**闭包；**禁止**上述字段进 LLM Tool Schema。
- 门控：`bind_tools` 时按 `allow_web` / 是否启用图谱裁剪列表。
- 检索 kb：只来自 configurable；未指定 `None` = 全部已开启库（与 Chat 一致）。
- 允许一轮多个 tool_calls；硬上限 `MAX_LOOPS` / `MAX_TOOL_CALLS`。
- Citations：聚合本轮检索类 Tool 结构化结果。

## 3. 代码布局（禁止新建 p4/）

全部位于 `server/app/`：

| 文件 | 职责 |
|---|---|
| `intent.py` | 薄意图分类 |
| `master.py` | Supervisor 主图 + `MasterState` |
| `knowledge_flow.py` | `task=knowledge` Workflow Agentic RAG |
| `graph.py` | 标准 Tool Calling ReAct（`task=react`；Master knowledge 共用） |
| `agent/tools/` | `@tool` 实现 + `registry`；旧 import 薄封装 re-export |
| `plan_agent.py` | 规划子 Agent + plan tools |
| `booking_agent.py` | 预订子 Agent + booking tools |
| `travel/flyai.py` | flyai search-flight / book（Step 2/3） |
| `travel/minio_store.py` | plans / reports 上传与回看 URL |

路由层仍在 `server/app/routers/master.py`。

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

**仅 `task=react`** 另增稳定中间态（与 Graph 同套 stream；前端可先忽略）：

| type | 用途 |
|---|---|
| `agent_start` / `agent_end` | ReAct 起止 |
| `tool_call` / `tool_result` | 工具调用与结构化结果摘要 |
| `answer_delta` | 终答增量（可与现有 `token` 并存以兼容旧前端） |

**传输时机（react）**：`stream_mode=["updates","custom"]`；LLM 用 `model.stream` + `get_stream_writer` 边生成边推 `token`；节点 updates 推 tool_*；`_agent_persist` 在出字之后、`citations` 之前。knowledge / Master 路径仍可伪流式。

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
- **node_type**：Chat / knowledge_flow 仍以 `route` / `retrieve` / `generate`（knowledge 用 `decision.step` + IO）为主；**`task=react`** 使用 `tool_call` / `tool_result`（及必要终答 span），`String(20)` 内命名。
- **本期**：`task=agent` Master knowledge 调用 `graph.py` **不接**决策审计；booking/plan 仍下一期。
- 能力与埋点**同步**落地，禁止后补；chat 模式审计口径不变。

## 9. 切块存储：Parent-Child（V1）

长期数据约束（一张 `document_chunk`，不另建向量表）：

- `role`：`parent` | `child`；存量默认 `child`
- `parent_id`：child → parent；短 section 仅一行 `role=child` 且 `parent_id=null`（无空父）
- **检索单位**：仅 child（向量 / BM25 / RRF / Rerank）；parent **无 embedding、不进 ES**
- **生成上下文（V3）**：门槛后每命中独立 ±1；邻居须过锚点余弦 + query 分双条件才并入 `content`；同父多命中保留多条。**禁止**默认 parent 全文 / V0 同 heading center-out 作为主路径。
- 导入页切的是 child 策略，与「命中后邻居组装」分维；不做组装 UI
