# 当前子需求：ReAct graph.py 标准 Tool Calling 重构

> 需求来源：`docs/agent/flow.md`（只读）+ 本轮对话决议  
> 关联备注：`docs/agent/react.md`（流式体验动机，非独立需求）

## 1. 目标

将共用的 `server/app/agent/graph.py` 从手写 JSON `action`/`next_action` 路由，重构为标准 LangChain/LangGraph Tool Calling ReAct（`bind_tools` + `ToolNode` + `tools_condition` + `ToolMessage`），并：

- 拆分 `agent/tools/` 包与 registry（禁止闭包注入运行时）；
- 为 **`task=react`** 提供稳定 SSE 事件流（与 Graph 同套实现）；
- 决策审计在 **`task=react`** 下改为按 tool_call / tool_result 记 span。

## 2. 背景

当前 `graph.py` 用 LLM 输出 JSON 决定 `rag`/`web`/`graph`/`generate`，自维护 `next_action` / `subtasks` 路由。`flow.md` 要求改为官方 Tool Calling 循环；对话页已有 `task=react` 入口直连该图；`task=agent` 的 Master **knowledge** 分支也调用同一 `build_graph()`。Text2SQL 演示实现与 `tools.py` 中部分 `@tool` 草稿已存在，但未按「无闭包 / registry / 标准循环」落地。

## 3. 功能范围

- **重构 `graph.py`**：标准 `agent ⇄ tools` 循环；无 `tool_calls` 时以模型当轮 `content` 为终答（不再手写 JSON action 分发）。
- **工具包**：`app/agent/tools/`（`registry.py` + `knowledge.py` / `graph.py` / `web.py` / `text2sql.py`）；旧 `from app.agent.tools import search_knowledge` 等路径保留薄封装 re-export。
- **Runtime**：`session` / `user_id` / `conversation_id` / `knowledge_base_id` 等仅经 `config["configurable"]` 注入；禁止进入 LLM Tool Schema；禁止闭包捕获。
- **工具门控**：`bind_tools` 时按 `allow_web`、是否具备图谱检索条件裁剪列表（无则不 bind `web_search` / `search_graph`）。
- **多库检索**：`knowledge_base_id` 只来自 context；未指定时为 `None` → 与 Chat 一致搜全部已开启库（`search_kb_ids`）。
- **多 tool_calls**：允许一轮多个；去掉以 `subtasks`/`subtask_index` 作为手写路由协议。
- **Citations**：聚合本轮 messages 中所有 `search_knowledge` / `search_graph` 结构化结果。
- **Streaming（仅 `task=react`）**：与 Graph 同实现；SSE 含 agent_start / tool_call / tool_result / answer_delta / agent_end 等稳定协议；前端本期可不展示中间态，至少不因未知事件崩溃且能消费终答（如 `answer_delta` 或现有兼容字段）。
- **决策审计（仅 `task=react`）**：`mode=react`；span 按 tool_call / tool_result（及必要的终答节点）记录；`node_type` 长度适配现有字段约束。
- **文档同步（Phase 4 / 约定）**：`docs/PRD.md`、`docs/TECH.md`、必要时 `docs/Trace.md` 与行为对齐（不在 Phase 1 改代码）。

## 4. 非目标

- 不修改：`task=knowledge` → `knowledge_flow.py`；P0 `/api/chat` / `/api/chat/stream`。
- 不修改：`booking_agent`、`plan_agent`、Master 意图路由本身（仅 knowledge 子调用的 `graph.py` 行为随重构变化）。
- **`task=agent` 经 Master knowledge 调用 `graph.py` 时：本期不注入 / 不落决策审计**（维持现状）。
- 新 SSE 协议**不**覆盖 `task=agent` 全路径，也**不**要求统一改造 plan/booking 的现有 stream 事件。
- 本期不做对话页 Reason/Tool Call/Tool Result 的完整 Trace UI（Phase 3 前端展示下期）。
- 不引入第二套向量检索；`search_knowledge` 内部仍走现有 `search_chunks`（Vector+BM25→RRF→Rerank）。
- 不改操作审计占位页；不做 LangSmith / 自建 Trace 平台。

## 5. 业务规则

| ID | 规则 | 来源 |
|----|------|------|
| R1 | 身份与 DB session 不得由 LLM 作为 Tool 参数传入 | flow.md + 对话 |
| R2 | Runtime 用 `configurable`，禁止闭包注入 | 对话 Q2=B |
| R3 | 无 tool_calls → 当轮 content 即终答 | 对话 Q1=A |
| R4 | bind 时裁剪工具列表 | 对话 Q3=A |
| R5 | kb 只来自 context；未指定 `None`=全部已开启库 | 对话 Q4=A + A1 |
| R6 | 允许多 tool_calls；去掉 subtasks 手写路由 | 对话 Q5=B |
| R7 | Citations 聚合本轮全部检索类 Tool 结果 | 对话 Q6=A |
| R8 | ReAct 审计 span 按 tool_call/tool_result | 对话 Q7=B |
| R9 | 新 SSE 仅 `task=react` | 对话 Q8=A |
| R10 | 后端先稳；前端可先只消费终答相关事件 | 对话 Q9=A |
| R11 | tools 拆包 + 旧 import 薄封装 re-export | 对话 Q10=A |
| R12 | `task=agent` knowledge 路径本期不接决策审计 | 对话确认「否」 |
| R13 | booking / plan 暂时不改 | 对话 |
| R14 | 用户身份只来自 Session，禁止请求参数指定 user_id | AGENTS.md |

## 6. 输入与输出

**输入**

- `POST /api/agent`、`POST /api/agent/stream`：`task=react`（及既有 `task=agent` 且意图为 knowledge 时内调 `build_graph`）。
- configurable：`session`、`user_id`、`conversation_id`、`knowledge_base_id`（可空）、`allow_web`、`decision_recorder`（仅 react 路径注入）。

**输出**

- 终答文本 + citations（检索类工具聚合）。
- `task=react` stream：稳定 SSE JSON 事件（至少含工具中间态事件类型 + 终答增量/终态）；与普通 invoke 共用同一 Graph。
- `task=react`：`decision_run(mode=react)` + 线性 spans（tool_call / tool_result 等）。

## 7. 涉及模块

- `server/app/agent/graph.py`（核心）
- `server/app/agent/tools.py` → 迁移为 `server/app/agent/tools/` 包 + 兼容导出
- `server/app/agent/text2sql.py`（实现复用，Tool 包装进包内）
- `server/app/routers/master.py`（react 的 invoke/stream/审计接线；agent knowledge 不接审计）
- 决策审计：`server/app/audit/*`、必要时 `DecisionAuditView` 仅保证不崩（新 node_type 可读）
- 测试：ReAct / graph 相关单测与契约；旧 `search_knowledge` import 兼容冒烟
- 文档：`docs/PRD.md`、`docs/TECH.md`（及 Trace 若与 mode/span 不符）

## 8. 验收标准

1. ReAct 循环可观测：User → LLM → `AIMessage.tool_calls` → ToolNode → `ToolMessage` → LLM → 再 tool 或 Final（content 终答）。
2. 代码中不再保留手写 `json.loads(action)` / `if action == "rag"|"web"` 作为 `graph.py` 工具路由。
3. 新增 Tool 只需改 tools 模块 + registry，无需改 ReAct 核心循环。
4. LLM Tool Schema 不含 `session` / `user_id` / `conversation_id`。
5. `allow_web=false` 时模型侧不可 bind `web_search`；无 kb/图谱条件时不 bind `search_graph`。
6. `knowledge_base_id` 未指定时 `search_knowledge` 检索全部已开启库。
7. `task=react` SSE 能推送中间 tool 事件与终答；前端忽略中间事件仍能得到完整回答。
8. `task=react` 落库决策链为 tool_call/tool_result 形态；`task=agent` knowledge 仍无强制新审计。
9. `knowledge_flow`、Chat、booking、plan 行为不因本需求被改坏（回归范围：既有相关测试 + 关键路径冒烟）。
10. 旧 `from app.agent.tools import search_knowledge`（等）仍可用。

## 9. 待确认问题

无。对话决议已闭合；实现细节（具体 SSE 字段名与现有 `token`/`citations` 事件的兼容策略）留 Phase 2 方案设计，不阻塞本子需求定义。
