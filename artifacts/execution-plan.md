# Execution Plan

> 子需求：ReAct Agent 标准 Tool Calling 优化  
> 栈约束：见 `AGENTS.md`；保留 `bind_tools`+`ToolNode`+`tools_condition`；不改 knowledge_flow / 旧 chat API  
> 已确认（确认①）：① 关 `parallel_tool_calls` + 进 ToolNode 前预算截断双保险；② citations 去重后按 `score` top-N，无 score 保首次；③ `reason` 挂 `tool_call`/`tool_result` 可选字段，不新增独立事件；④ 只强化 `citations`，不维护 react `evidence` state  
> 全局硬约束：禁止新增 `rewrite` / `select_tool` / `rerank` / `reflect` / `decide` 类 LangGraph Node；「下一步做什么」只由下一轮 `node_agent` LLM 决策（含改写 query / 选工具 / 是否继续）

---

## Step 1：`MAX_TOOL_CALLS` 双保险硬上限

### 目标
使实际 Tool **执行**总次数始终 ≤ `MAX_TOOL_CALLS`（含模型仍并行发出多个 `tool_calls` 的情况）。

### 方案
- `server/app/agent/graph.py`：`bind_tools` 时传 `parallel_tool_calls=False`（若客户端/模型不支持则吞掉并依赖第二道）。
- 在进入 `ToolNode` 执行前：按 `remaining = MAX_TOOL_CALLS - tool_call_count` 截断本轮待执行的 `tool_calls`（改写最后一条 `AIMessage` 或其等价输入），只执行预算内调用；被截断的不计入执行。
- 保留现有「预算耗尽则 `_bound_tools` 返回空列表、模型只能终答」行为。
- 不单靠 `loop_count`；`tool_call_count` 仍按**实际执行数**累加。
- 单测：模拟一轮 `tool_calls` 数量 > 剩余预算 → 实际执行 ≤ 剩余；多轮累计不超过 `MAX_TOOL_CALLS`。

### 验收
- [✅] 单测：一轮并行多个 `tool_calls` 超过剩余预算时，实际执行次数 ≤ 剩余预算，且最终累计 ≤ `MAX_TOOL_CALLS`
- [✅] `bind_tools` 调用路径包含 `parallel_tool_calls=False`（源码断言或等价单测）
- [✅] 既有 `test_p1_graph` / `test_react_*` 中与循环相关的用例仍通过（最小必要适配）

---

## Step 2：增强 Tool description

### 目标
让 LLM 能正确理解各 Tool 用途、重试与切换时机；schema 仍仅业务参数。

### 方案
仅改各 `@tool` docstring（必要时 `description=`），不改实现逻辑：
- `search_knowledge`：知识库语义/关键词综合检索；证据不足可换 query 重试
- `search_graph`：实体、关系、关联文档
- `web_search`：仅允许联网且库内不足/需外部最新信息时
- `text2sql`：仅结构化业务数据查询
- 验收：schema（args）仍不含 `session`/`user_id`/`knowledge_base_id` 等 runtime

### 验收
- [✅] 四个 Tool 的 description/docstring 含用途与使用时机要点（人工对照 prd-sub §3.2）
- [✅] 断言或既有工具 schema 检查：args 不含 runtime 字段（可复用/扩展 `test_p1_tools` 类检查）

---

## Step 3：citations 去重与 score top-N 保质

### 目标
按 `document_id + chunk_id` 去重；截断时保留高 score；无 score 保留首次出现；不维护 react `evidence`；前端 citations 形态兼容。

### 方案
- 在 `graph.py` 将 append+`[-MAX_CITATIONS:]` 替换为合并函数：键=`(document_id, chunk_id)`；同键保留更高 `score`（缺失 score 视为最低并保首次键序）；最后按 score 降序取 top-`MAX_CITATIONS`（无 score 的条目按首次出现次序排在有 score 之后或稳定穿插——约定：有 score 按分数降序，无 score 按首次出现追加在已选满前的空位，总数 ≤ N）。
- `node_tools` 与终答聚合路径共用该函数。
- 不读写/填充 react 路径的 `evidence` state。
- 字段保持与 `CitationOut` / 现 Tool 输出兼容（`document_id`/`chunk_id`/`score`/title/snippet 等现有键）。

### 验收
- [✅] 单测：同键重复 citations → 只保留一条且为较高 score
- [✅] 单测：先入高 score、后入大量低 score → 截断后仍保留早期高 score（不被「只留最后 20」挤掉）
- [✅] 单测或契约：无 score 条目按首次出现保留且总数 ≤ `MAX_CITATIONS`
- [✅] 输出仍可被现有 citations / `CitationOut` 消费路径解析（相关 react/sse 测试通过）

---

## Step 4：Streaming `reason` 可选字段 + `error` 路径

### 目标
多轮 `Agent→Tool→Agent→…→Final` 事件保持完整；`tool_call`/`tool_result` 可带安全短 `reason`；失败有 `error` 事件；不新增独立 reason 事件、不泄漏 CoT。

### 方案
- `graph.py`：在 custom writer 或节点 updates 中附带安全 `reason`（如「正在检索知识库」「知识库命中 N 条」类固定模板），禁止模型原始 Thought。
- `routers/master.py` `_stream_react_graph`：透传 `tool_call`/`tool_result` 的可选 `reason`；异常路径 `yield {"type":"error", ...}` 后再结束（与现有 `finish_run("failed")` 协调）。
- 不改非 react 任务的强制事件集；保留 `token`/`answer_delta`/`citations` 兼容。

### 验收
- [✅] 契约/单测：`task=react` SSE 多轮可见 `tool_call`→`tool_result`→终答事件序列；`tool_call` 或 `tool_result` 至少一类带可选 `reason` 且为短摘要
- [✅] 单测或源码断言：无独立 `type=reason` 事件
- [✅] 单测或路径验证：react stream 异常时出现 `type=error`（可用 monkeypatch 抛错）
- [✅] `test_react_sse` / `test_react_agent_task` 通过（兼容字段未破坏）

---

## Step 5：按需收紧 system prompt

### 目标
强化「足够 = 本轮 Observation」、工具切换/改写/停止策略；不新增 rewrite Node。

### 方案
- 仅改 `_system_prompt`：补强何时调 Tool / 换 Tool / 改写 query 再检索 / 交叉验证 / 停止；重申会话历史与 LTM 非本轮证据；`allow_web=false` 禁 web。
- Tool 切换细节以 Step 2 description 为主，Prompt 不堆砌过长。
- 不改图拓扑。

### 验收
- [✅] `_system_prompt` 文本含「本轮 Observation / 本轮 Tool」足够判定与禁止用会话历史冒充证据的明确表述
- [✅] `graph.py` / `build_graph` 无新增 `rewrite`/`select_tool`/`rerank`/`reflect`/`decide` 类 Node；拓扑仍仅 `agent ⇄ tools`
- [✅] 冒烟：相关 `test_p1_graph` / react 图测试通过

---

## Step 6：清理无效残留 + Registry 贯穿确认

### 目标
清理 `graph.py` 中明显旧 ReAct/无用残留；确认新增 Tool 不改主循环。

### 方案
- 只删明确无效残留（若有）；不大重构；不删 knowledge_flow 共享字段（若仍被 knowledge 路径依赖）。
- 核对 `registry` / `tools_for` / `ToolNode(AGENT_TOOLS)` / `bind_tools(tools_for(...))`：主循环无按工具名 if/else。
- Phase 4 前本 Step 不做文档大同步；仅代码清理与确认。

### 验收
- [✅] `node_agent`/`node_tools`/`route_after_agent` 无按具体 tool name 的业务 if/else 路由（审计 span / reason 模板除外）
- [✅] `build_graph` 节点集合仍仅为 agent/tools（无 rewrite/select_tool/rerank/reflect/decide）
- [✅] `git diff` 范围不含 `knowledge_flow.py`、旧 chat 路由行为文件的功能性改动
- [✅] 本子需求相关测试子集通过（`test_react_*`、`test_p1_graph`、工具 schema 相关）
  > 审计：无明显可删旧 ReAct 残留；knowledge_flow 共享 AgentState 字段保留；主循环经 `tools_for`/`ToolNode(AGENT_TOOLS)`/`bind_tools`，无按工具名业务路由。
