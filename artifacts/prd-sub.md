# 当前子需求：ReAct Agent 标准 Tool Calling 优化

> 需求来源：`docs/agent/react_agent.md`（只读）  
> 前置：`ReAct graph.py 标准 Tool Calling 重构`（2026-09-10）已全 ✅；本轮在现有 `bind_tools` + `ToolNode` + `tools_condition` 上优化，不改回手写 JSON。

## 1. 目标

检查并优化当前 ReAct 实现（主文件 `server/app/agent/graph.py` + Tool description），使 `MAX_TOOL_CALLS` 成为真实硬上限，强化 Tool 描述与证据聚合，补齐安全流式事件（含 `reason` 摘要），并在必要时收紧 Prompt；保持 Registry 可扩展与现有对外契约兼容。

## 2. 背景

上一子需求已落地标准 Tool Calling 循环与 `task=react` SSE/审计。实测仍有缺口：

- **预算**：`tool_call_count` 在 `node_tools` 执行后累加；一轮多个 `tool_calls` 可一次击穿 `MAX_TOOL_CALLS=6`。
- **Tool 描述偏薄**：各 `@tool` docstring 未充分表达使用时机 / 重试 / 切换条件。
- **证据**：`citations` 为 append + 截取最后 20，无 `document_id+chunk_id` 去重，后续结果可挤掉早期高质证据；`evidence` 字段存在但未真正参与保质逻辑。
- **Streaming**：`agent_start` / `tool_call` / `tool_result` / `token` / `answer_delta` / `agent_end` 已有；安全 `reason` 摘要未必齐。
- **Prompt**：已有 Observation→再决策协议与「会话历史≠本轮证据」条款；工具切换时机仍可再靠 Tool description 补强，Prompt 按需再收紧。
- **关键张力**：模型易把会话历史旧答当成「足够」而跳过本轮检索；「足够」必须定义为**本轮 Tool Observation 足够**。

## 3. 功能范围

按推荐优先级落地（Registry 贯穿验收，不单独占业务 Step）：

1. **硬上限**：实际 Tool **执行**总次数 ≤ `MAX_TOOL_CALLS`（优先关闭并行或等价可靠预算检查，不单靠 `loop_count`）。
2. **Tool 描述增强**：`search_knowledge` / `search_graph` / `web_search` / `text2sql`；schema 保持简单，不暴露 runtime context。
3. **Evidence / citations**：按 `document_id + chunk_id` 去重；避免后续结果挤掉早期高质证据；最终保留高质量/高相关；**citations 输出格式兼容前端**。
4. **Streaming 补全**：确认多轮 `Agent→Tool→Agent→…→Final` 事件完整；补齐安全 `reason` 短摘要（不暴露完整 CoT）；事件类型含 `agent_start` / `tool_call` / `tool_result` / `answer_delta` / `agent_end` / `error`。
5. **Prompt（按需）**：明确何时调 Tool / 改写 query / 切换工具 / 交叉验证 / 停止；强调足够=本轮 Observation；`allow_web=false` 禁止 `web_search`。不新增 rewrite Node。
6. **清理**：仅清理 `graph.py` 中旧 ReAct / 旧 knowledge_flow 无效残留；不大重构。
7. **Registry**：新增 Tool 仍只注册、不改主循环（验收确认）。

## 4. 非目标

- 不修改 `knowledge_flow.py` 核心流程；不改旧 `/api/chat`、`/api/chat/stream`。
- 禁止新增 `rewrite` / `select_tool` / `rerank` / `reflect` / `decide` 类 LangGraph Node；任何「下一步做什么」必须仍由下一轮 `node_agent` 的 LLM 决策完成（含 Query Rewrite / Tool Selection / Rerank / Reflection）。
- 不把 `search_knowledge` 内部 Vector+BM25+RRF+Rerank 拆成多个 Agent Tool。
- 不改变现有 Tool 业务能力；不暴露完整 Chain-of-Thought。
- 不为「架构漂亮」做无关重构；不改前端已有接口格式，除非 Streaming 必须增加**兼容**字段。
- 不引入第二套向量集合 / 改栈。

## 5. 业务规则

- 保留标准 Tool Calling：`bind_tools` / `AIMessage.tool_calls` / `ToolNode` / `tools_condition` / `agent ⇄ tools`。
- **足够 = 本轮 Tool Observation 足够**，不是会话历史里好像知道；会话历史与 LTM 只作对话上下文，不得当作本轮检索证据；无本轮证据不得点名虚构文档来源。
- `allow_web=false` 时绝不能调用 `web_search`（门控 + Prompt）。
- Query rewrite 仍由 Agent 下一次 Tool Call 的 `query` 参数完成；图拓扑保持 `agent ⇄ tools`，不增加决策类 Node。
- 身份 / KB 等 runtime 仍经 `configurable`，不进 Tool Schema。
- 技术栈约束见根目录 `AGENTS.md`（P1 Agent 允许 LangGraph；检索经 Tool→现有 pgvector 路径）。

## 6. 输入与输出

- **输入**：既有 `task=react` invoke / stream 请求（含 `allow_web`、可选 `knowledge_base_id`、会话历史）。
- **输出**：终答 + 兼容的 `citations`；stream 时多轮安全事件（含可选安全 `reason`）；决策审计 span 行为不退化。

## 7. 涉及模块

- `server/app/agent/graph.py`（预算、prompt、证据聚合、必要清理）
- `server/app/agent/tools/*.py`（description）
- `server/app/agent/tools/registry.py`（确认零主循环改动）
- `server/app/routers/master.py`（react stream 事件 / `reason` / `error` 补齐，按需）
- 相关单测：`test_react_*` / `test_p1_graph` 等最小必要更新
- Phase 4：按需同步 `docs/PRD.md`、`docs/TECH.md`、`artifacts/architecture.md`

## 8. 验收标准

- 实际 Tool 执行次数在任意并行/多轮场景下均 ≤ `MAX_TOOL_CALLS`。
- Tool description 能表达各工具用途、重试与切换时机；schema 无 runtime 字段。
- citations：同 `document_id+chunk_id` 去重；截断策略不单纯「只留最后 20」导致早期高质证据丢失；前端 citations 字段形态兼容。
- `task=react` stream 支持完整多轮循环事件；有安全 `reason` 摘要路径；无完整 CoT 泄漏；有 `error` 事件路径。
- Prompt（若本轮收紧）明确「足够=本轮 Observation」与工具策略；无 rewrite Node。
- 新增 Tool 只需注册，不改 ReAct 主循环。
- `knowledge_flow.py`、旧 chat API、Tool 业务能力未改。

## 9. 待确认问题

（确认①已决议）

1. **并行**：关 `parallel_tool_calls` + 进 ToolNode 前按剩余预算截断 —— **双保险**。
2. **高质量**：去重后按 `score` top-N；无 score 保首次出现。
3. **`reason`**：挂在 `tool_call` / `tool_result` 可选字段；**不**新增独立事件。
4. **`evidence`**：只强化 `citations`；**不**维护 react 的 `evidence` state。
