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
       ├── knowledge   ← 现有 app/graph.py（reason→run_tool→generate）
       ├── plan        ← itinerary_plan_agent（ReAct + travel tools）
       └── booking     ← booking_agent（ReAct + HITL 写工具）
```

- **意图 ≠ Master**：`intent.py` 只输出标签；Master 不再做完整意图识别。
- `chat`：Master 节点直接 LLM 寒暄，不调子 Agent。
- `task=report`：路由 `knowledge`，生成后可选上传 MinIO `reports/{conversation_id}/...`。
- 子 Agent 事件 **不冒泡** 打乱前端主 SSE 序列（等价 GoGo `forwardEvents(false)`）。

## 3. 代码布局（禁止新建 p4/）

全部位于 `server/app/`：

| 文件 | 职责 |
|---|---|
| `intent.py` | 薄意图分类 |
| `master.py` | Supervisor 主图 + `MasterState` |
| `graph.py` | knowledge 子图（现有，少改） |
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
