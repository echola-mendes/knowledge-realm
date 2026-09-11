# ReAct Agent 标准 Tool Calling 重构

目标：
将 task=agent / task=react 的 graph.py 重构为标准 LangChain/LangGraph
Tool Calling ReAct Agent。

不再使用手写 JSON action/query 路由，不使用闭包，不让 LLM 传递
session/user_id 等运行时参数。

## 1. 标准 Tool Calling

使用：

- langchain_core.tools.tool
- model.bind_tools(...)
- AIMessage.tool_calls
- ToolNode
- tools_condition
- ToolMessage

核心循环：

START
→ agent
→ tools
→ agent
→ ...
→ END

LLM 有 tool_calls 时执行 ToolNode；
没有 tool_calls 时结束并生成最终回答。

不要自己解析 action JSON。
不要自己 if/elif 分发 Tool。

## 2. Tool 独立模块

建立：

agent/tools/
├── __init__.py
├── registry.py
├── knowledge.py
├── graph.py
├── web.py
└── text2sql.py

每个 Tool 使用 @tool。

registry.py 统一导出：

AGENT_TOOLS = [
    search_knowledge,
    search_graph,
    web_search,
    text2sql,
]

以后新增 Tool 只需要：
1. 新增 tools/*.py
2. 在 registry.py 注册

不得修改 ReAct graph 核心循环。

## 3. Runtime Context

不要使用闭包注入 session/user_id。

使用 LangGraph/LangChain 官方 runtime/context 机制。

AgentContext 至少包含：

- user_id
- session
- conversation_id
- knowledge_base_id

这些字段不能出现在 LLM Tool Schema 中。

LLM 只能传递 Tool 真正需要的业务参数，例如：

search_knowledge(query, k)

Tool 执行时从 runtime/context 获取 user_id、DB session 等运行时信息。

## 4. Tool Schema

search_knowledge：
query
knowledge_base_id（如果确实需要）
tag_id（如果确实需要）
kind（如果确实需要）
document_id（如果确实需要）
k

search_graph：
只暴露 LLM 真正需要的业务参数。

web_search：
query。

text2sql：
question。

session、user_id、conversation_id 禁止作为 LLM Tool 参数。

## 5. search_knowledge 内部实现

保持：

Vector Search
+
BM25
↓
RRF
↓
Rerank

这些属于 Retrieval Tool 内部实现，不拆成 Agent Tools。

## 6. Tool Result

Tool 返回结构化、可序列化的结果。

不要直接把 SQLAlchemy 对象、Session、SearchHit 等内部对象
直接返回给 ToolMessage。

search_knowledge 返回：

{
  "tool": "search_knowledge",
  "query": "...",
  "results": [
    {
      "rank": 1,
      "score": 0.91,
      "document_id": "...",
      "document_name": "...",
      "content": "..."
    }
  ]
}

Tool 失败也返回结构化错误信息，让 LLM 可以决定：
重试 / 换 Tool / 最终回答。

## 7. ReAct 状态

尽量使用标准 messages 状态。

不要再维护：

action
query
subtask_index

作为手写 Tool 路由协议。

Tool Calling 本身通过：

AIMessage(tool_calls)
ToolMessage

表达 Action / Observation。

如果需要 Trace，可从 messages/tool_calls 中生成。

## 8. 循环控制

保留硬限制：

MAX_LOOPS / MAX_TOOL_CALLS。

防止：

LLM
→ Tool
→ LLM
→ Tool
→ 无限循环。

达到限制后强制进入最终回答。

## 9. Trace

保留 Agent Trace：

Reason
→ Tool Call
→ Tool Result
→ Reason
→ Tool Call
→ ...
→ Final

不要要求 LLM 输出 Thought 原文；
记录结构化 reason / tool call / tool result 即可。

## 10. P0/P2 RAG 不回归

不要修改：

task=knowledge → knowledge_flow.py

不要修改：

普通 Chat → 原有 /api/chat / /api/chat/stream

本次只重构：

task=agent / task=react → graph.py

## 11. 最终验收

必须能够出现：

User
→ LLM
→ AIMessage.tool_calls
→ ToolNode
→ ToolMessage
→ LLM
→ 再次 Tool Calling 或 Final

新增一个 Tool 时，只修改 tools 模块和 registry，
graph.py 核心循环无需修改。

禁止保留旧的：
json.loads(action)
if action == "rag"
if action == "web"
等手写 Tool 路由逻辑。

## 12. Streaming

本次 Tool Calling 重构必须同时设计 Streaming，
不要先实现 invoke() 再单独重构 streaming。

Agent API 使用 agent.stream(...) / 对应 LangGraph streaming API
将 ReAct 中间事件实时传递给前端。

至少支持：

1. Agent 开始/Reason 状态
2. AIMessage.tool_calls
3. Tool 开始
4. Tool 结束及结构化结果摘要
5. 下一轮 Reason
6. Final Answer token/delta
7. Agent 完成
8. Tool/Agent 错误

推荐前端通过 SSE 接收。

事件统一为稳定协议，例如：

{
  "type": "agent_start",
  ...
}

{
  "type": "tool_call",
  "tool": "search_knowledge",
  "args": {...}
}

{
  "type": "tool_result",
  "tool": "search_knowledge",
  "summary": "...",
  ...
}

{
  "type": "answer_delta",
  "content": "..."
}

{
  "type": "agent_end"
}

不要向前端输出 LLM 的完整 hidden chain-of-thought。
只输出可展示的 reason_summary / tool 状态 / tool result summary。

Streaming 不应改变 ReAct Graph 的业务逻辑；
它只是 Graph 执行事件的实时输出层。

普通 invoke 和 stream 应共享同一套 Graph，
不要维护两套 Agent 实现。

# 实施顺序
Phase 1
标准 Tool Calling
    ↓
@tool
bind_tools
ToolNode
tools_condition
ToolMessage
    ↓
确认 ReAct 循环正确

Phase 2
在同一套 Graph 上增加 stream
    ↓
agent.stream(...)
    ↓
前端实时收到：
Reason
Tool Call
Tool Result
Reason
Tool Call
...
Final Answer

Phase 3
前端 Trace 展示