# Execution Plan

> 子需求：ReAct `graph.py` 标准 Tool Calling 重构  
> 栈约束：FastAPI + LangGraph；检索仅经 Tool→`search_chunks`；身份只来自 Session/`configurable`；不改 Chat / knowledge_flow / booking / plan  
> 已确认：见 `artifacts/prd-sub.md` R1–R14（含 Q1–Q10、A1、agent knowledge 不接审计）

## Step 1：拆分 `agent/tools/` 包 + 旧路径 re-export + configurable 取上下文

### 目标
按 `flow.md` 落地工具包与 registry；去掉闭包版 `build_agent_tools`；Tool 执行时从 `configurable` 读 `session`/`user_id`/`knowledge_base_id` 等；旧 `from app.agent.tools import search_knowledge` 等仍可用。

### 方案
- 新建 `server/app/agent/tools/`：`knowledge.py` / `graph.py` / `web.py` / `text2sql.py` / `registry.py` / `__init__.py`。
- 每个文件：`@tool`（仅业务参数）+ 可被 knowledge_flow 等调用的纯函数实现（迁移自现 `tools.py`）。
- `registry.py`：`AGENT_TOOLS` 全量列表；`tools_for(*, allow_web, enable_graph)`（或等价）按门控返回 bind 子集（R4）。
- Tool 内用 LangGraph/LangChain 惯例从运行配置读取 context（`configurable`），**禁止**闭包捕获 session（R2）。
- `text2sql`：包装现有 `app.agent.text2sql` 实现；Schema 仅 `question`（等业务字段）。
- 删除或替换根级 `tools.py`：改为包，或薄文件 re-export 到包（保证既有 import 不断）（R11）。
- `search_knowledge`：`knowledge_base_id` **不进** Tool Schema；执行时用 configurable 中的值，`None` → 多库（R5/A1）。

### 验收
- [✅] `from app.agent.tools import search_knowledge, search_graph, web_search` 仍可 import，且 `search_knowledge` 签名/行为对 knowledge_flow 兼容（至少既有 `test_p1_tools` / knowledge 相关测试或等价冒烟通过）
- [✅] `@tool` schema（args）不含 `session` / `user_id` / `conversation_id` / `knowledge_base_id`
- [✅] `tools_for(allow_web=False)` 结果不含 `web_search`；`enable_graph=False` 不含 `search_graph`

---

## Step 2：重构 `graph.py` 为标准 Tool Calling 循环

### 目标
`reason/agent ⇄ tools`；无手写 JSON action 路由；无独立 generate 节点（无 tool_calls 时 content 即终答）；支持多 tool_calls 与 MAX 循环上限；聚合 citations。

### 方案
- State 以 messages 为主（可保留少量辅助字段：citations、loop_count、usage 等）；删除以 `next_action`/`subtasks`/`subtask_index` 作为工具路由协议（R6）。
- `model.bind_tools(tools_for(...))`；`ToolNode` + `tools_condition`；有 `tool_calls` → tools → agent，否则 END。
- 达 `MAX_LOOPS` / `MAX_TOOL_CALLS` 后强制不再调工具、以已有 context 产出终答（content 或最后一轮无 tools 调用）。
- 从本轮 `ToolMessage` / 结构化 tool 结果聚合 `search_knowledge`/`search_graph` citations（R7）；结构化可序列化结果（flow.md §6）。
- 适配依赖旧 API 的调用方：`initial_state` / `build_graph` / `reset_graph`；`plan_agent_search`（若仍被 retrieval_debug 使用）改为基于新 agent 节点或明确废弃并改调用方（最小改动）。
- `task=agent` Master knowledge 继续 `build_graph().invoke`，**不**注入 `decision_recorder`（R12）。

### 验收
- [✅] `graph.py` 中不存在以 `json.loads` 解析 `action`/`next_action` 作为工具路由的逻辑
- [✅] 单测或契约：模拟带 `tool_calls` 的 AIMessage → ToolNode 执行 → 再进入 agent；无 `tool_calls` → 结束且 `answer`/`content` 为终答
- [✅] 一轮多个 `tool_calls` 均可执行（不截成只跑第一个）
- [✅] `test_p1_graph` / `test_react_agent_task`（及因 API 变更必改的最小测试）通过

---

## Step 3：`task=react` 检索上下文 A1 + 决策审计 span（tool_call / tool_result）

### 目标
react 路径检索 kb 未指定则为多库；审计按 Q7=B 落 span；agent knowledge 仍无审计。

### 方案
- `_invoke_react_graph` / prepare：会话行 `Conversation.knowledge_base_id` 仍可 resolve 默认库；**检索用** `configurable.knowledge_base_id` = 请求显式值，否则 `None`（A1）。
- react 注入 `decision_recorder`；在 agent/tools 路径记录 `tool_call` / `tool_result`（及必要终答 span）；`node_type` ≤ 现有 `String(20)`。
- Master `node_knowledge` **不**传 `decision_recorder`（维持现状）。
- 监控页：新 `node_type` 至少以原始字符串可展示、详情不崩（不做完整 Trace UI）。

### 验收
- [✅] 单测：react 未传 `knowledge_base_id` 时，检索调用侧看到 `knowledge_base_id is None`（或多库 `search_kb_ids` 行为）
- [✅] 单测或集成：`task=react` 成功轮次产生 `decision_run(mode=react)`，且 spans 含 tool_call/tool_result（或等价命名），而非仅旧 route/retrieve/generate
- [✅] 单测或断言：Master knowledge 路径调用 `build_graph` 时 configurable 无 `decision_recorder`（或无新 run）

---

## Step 4：`task=react` 稳定 SSE（与 Graph 同套）+ 前端可忽略中间事件

### 目标
仅 `task=react` 输出稳定中间事件 + 终答；与 invoke 共用 Graph；现前端可只靠兼容终答字段拿到完整回答（R9/R10）。

### 方案
- `agent_stream` 在 `task=react` 分支对同一 `build_graph` 使用 `stream`（updates/messages/自定义），映射为 SSE：`agent_start`、`tool_call`、`tool_result`、`answer_delta`（或等价）、`agent_end`，以及错误事件；终态仍发 `citations`（或等价）以兼容现 ChatView。
- **兼容**：在发新事件同时，保留或映射现有 `token`/`citations`/`intent`，使当前前端不改也能拼出终答（ChatView 已认 `token`+`citations`）。
- `task=agent|report|knowledge` stream 行为保持现逻辑，不强制换新协议。

### 验收
- [✅] 契约测试：`POST /api/agent/stream` + `task=react` 的 SSE 中出现至少一类 tool 中间事件，且存在可拼出完整回答的 `token` 或 `answer_delta`，并以 `citations`（或文档约定终态）结束
- [✅] 同请求 `task=knowledge` 或 `task=agent` 的 stream 不强制出现新 `tool_call` 协议事件（冒烟：状态码 200 且既有事件类型仍可用）
- [✅] invoke 与 stream 共用同一 `build_graph`（无第二套 ReAct 实现文件）

---

## Step 5：文档与架构长期约束同步

### 目标
长期架构与对外需求/技术说明与实现一致（本 Step 只改文档，不改业务逻辑）。

### 方案
- 更新 `artifacts/architecture.md`：`graph.py` = 标准 Tool Calling ReAct；`agent/tools/` 包 + registry；`task=react`；configurable 注入；react 审计 span 形态；明确 knowledge_flow / booking / plan 边界。
- 更新 `docs/PRD.md`、`docs/TECH.md`；必要时修正 `docs/Trace.md` 中过时的「知识 Agent→graph.py / mode 仅 chat|knowledge」描述。
- **不修改**用户需求源 `docs/agent/flow.md`。

### 验收
- [✅] `architecture.md` 中 Agent/Tool 描述与「Tool Calling + tools 包 + task=react」一致，且不再把 `graph.py` 写成 knowledge_flow 编排
- [✅] `PRD.md` / `TECH.md` 写明 task=react Tool Calling 与 SSE/审计边界（agent knowledge 不接审计）
- [✅] `flow.md` 无改动（git 状态或 diff 确认）
