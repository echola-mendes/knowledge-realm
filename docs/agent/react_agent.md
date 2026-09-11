# ReAct Agent 优化任务书

请检查并优化当前 Agent ReAct 实现（主要是 `server/app/agent/graph.py`），目标是让它成为标准、可扩展的 LangGraph + Tool Calling ReAct Agent。

**执行方式：** 走 `lean-coding-workflow` Skill（文档驱动：prd-sub → execution-plan → 逐步验收），便于排查与回溯；不要一次性批量改完。

---

## 现状对照（开工前）

| 条目 | 现状粗判 | 说明 |
|---|---|---|
| 1 Prompt 策略 | 已开了一版 | `_system_prompt` 已写入 Observation→再决策协议；工具切换时机仍可再靠 Tool description 补强 |
| 2 Tool 描述 | 偏薄 | 各 `@tool` description 需按下文增强 |
| 3 `MAX_TOOL_CALLS` 硬上限 | **未修好** | 并行 `tool_calls` 可一次击穿预算；`tool_call_count` 在执行后才累加 |
| 4 Streaming | 大体有 | `tool_call` / `tool_result` / `token` 已推；安全 `reason` 摘要未必齐 |
| 5 Evidence | 仍弱 | append + 截取最后 20，会挤掉早期高质证据 |
| 6 Registry | 有雏形 | 主循环应继续对新增 Tool 零 if/else |
| 7 清理 | 可做 | 只清无效残留，不大重构 |

### 推荐 Step 优先级（Skill 规划时按此排序）

**3（硬上限）→ 2（Tool 描述）→ 5（证据）→ 4（流式补全）→ 1（按需再收紧 prompt）→ 7（清理）**

Registry（6）贯穿全程，不单独占 Step，验收时确认「新增 Tool 不改主循环」。

### 关键张力（写进验收）

任务要求「信息已经足够时停止 Tool Calling 并回答」。实测坑：模型会把**会话历史里的旧答**当成「足够」，从而跳过本轮检索。

**约定：足够 = 本轮 Tool Observation 足够，不是会话里好像知道。**

Prompt / 决策策略必须明确：

- 会话历史与长期记忆只作对话上下文，不得当作本轮检索证据；
- 库内事实须来自本轮 Tool Observation；
- 无本轮证据时不得点名虚构文档来源。

---

## 前提

- 当前已经使用标准 Tool Calling：
  - `model.bind_tools()`
  - `AIMessage.tool_calls`
  - `ToolNode`
  - `tools_condition`
  - `agent -> tools -> agent`
- 保留现有架构，不要改回手写 JSON ReAct。
- 不要把每个 Thought 拆成 LangGraph Node。
- 不要修改 `task=knowledge` 对应的 `knowledge_flow.py` 核心流程。
- `search_knowledge` 内部的 Vector + BM25 + RRF + Rerank 继续封装在 Tool 内，不拆成 Agent Tool。
- 不要暴露完整 Chain-of-Thought，只输出安全的 trace 信息。

---

## 重点优化

### 1. ReAct 决策策略

完善 system prompt，让 Agent 明确：

- 什么时候调用 Tool
- 什么时候继续检索
- 什么时候改写 query 后再次检索
- 什么时候切换 `search_knowledge` / `search_graph` / `web_search` / `text2sql`
- 什么时候需要多来源交叉验证
- 避免重复调用相同 Tool + 相同 query
- 信息已经足够时停止 Tool Calling 并回答（**足够 = 本轮 Observation**，见上文「关键张力」）
- `allow_web=false` 时绝不能调用 `web_search`

不要新增 rewrite Node，query rewrite 仍由 Agent 通过下一次 Tool Call 的 query 参数完成。

### 2. Tool 描述

增强各 Tool 的 description，让 LLM 能正确理解：

- `search_knowledge`：用于知识库语义/关键词综合检索；证据不足时允许换 query 重试
- `search_graph`：用于实体、关系、关联文档问题
- `web_search`：仅在允许联网且知识库信息不足/问题需要外部最新信息时使用
- `text2sql`：仅用于结构化数据查询

Tool schema 保持简单，不把 runtime context 暴露给 LLM。

### 3. MAX_TOOL_CALLS 严格限制

当前 `MAX_TOOL_CALLS=6` 存在问题：一个 `AIMessage` 可能同时产生多个 `tool_calls`，`ToolNode` 会一次执行多个，导致实际调用次数超过 6。

请修复，使 `MAX_TOOL_CALLS` 成为真正的硬上限。

优先保证：

- **实际 Tool 执行总次数 <= MAX_TOOL_CALLS**

如果当前模型支持 `parallel_tool_calls`，可以考虑关闭并行 Tool Call，使一次 Agent round 最多一个 Tool Call；  
如果不适合当前模型，则实现可靠的调用预算检查，不要简单依赖 `loop_count`。

### 4. Streaming

当前 `node_agent` 内部虽然使用 `runnable.stream()`，但需要确认整个 Agent Graph / API 是否真正支持多轮：

`Agent -> Tool -> Agent -> Tool -> Agent -> Final Answer`

请补齐真正的 Graph/Event Streaming，让前端能够获得安全的事件：

- `agent_start`
- `tool_call`
- `tool_result`
- `answer_delta`
- `agent_end`
- `error`

不要向前端输出隐藏 Chain-of-Thought。  
`reason` 只能是安全的简短摘要，例如：「知识库证据不足，尝试扩大检索范围」。

### 5. Evidence 管理

当前 citations/evidence 是简单 append + 截取最后 20 条。请优化为：

- 根据 `document_id + chunk_id` 去重
- 不要因为后续 Tool Result 把前面高质量证据挤掉
- 最终保留高质量/高相关证据
- 保持现有 citations 输出格式兼容前端

### 6. 保持 Tool Registry 扩展能力

新增 Tool 时，ReAct 核心 graph 不应该增加 if/else。继续使用：

- Tool Registry
- `@tool`
- `tools_for(...)`
- `bind_tools(...)`
- `ToolNode`
- `tools_condition`

最终目标：新增一个 Tool，只需要注册 Tool，不需要修改 ReAct 主循环。

### 7. 清理范围

可以清理 `graph.py` 中明显属于旧 ReAct / 旧 knowledge_flow 的无效代码，但不要大规模重构。

特别注意：

- 不要修改 `knowledge_flow.py` 的 Controlled Agentic Workflow
- 不要修改旧 `/api/chat` 和 `/api/chat/stream` 的行为
- 不要改变现有 Tool 的业务能力
- 不要改变前端已有接口格式，除非 Streaming 必须增加兼容字段

---

## 完成后请

1. 先检查当前实现
2. 只修改必要代码
3. 说明修改了哪些文件
4. 给出 ReAct 当前完整调用链
5. 说明现在是否真正满足「标准 Tool Calling ReAct」
6. 检查是否还存在 Tool 调用次数超限、重复调用、Streaming 不完整等问题
7. 不要为了「架构漂亮」进行无关重构

---

## 注意

ReAct 的核心就是「LLM 决策 → Tool Call → Tool Result → LLM 再决策」循环。

不要把「Query Rewrite / Tool Selection / Rerank / Reflection」等人为拆成固定 LangGraph Node。  
这些属于 Agent 决策或 Tool 内部能力，而不是固定 Workflow。
