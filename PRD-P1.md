# 知域 — P1（V1.5）架构

**状态：** 可执行（提出人已确认边界）  
**依据：** `PRD.md` 第 18 节 P1 名单；提出人对方案的 11 条调整  
**基线：** P0 已完成且稳定。实现细节以 `memory-bank/design-document.md` 为准；本文只写 P1。

**P1.1、P1.2、P1.3 已完成。** 当前只允许 **P1.4**（最小图谱落库 + 知识关联）。一次只做计划中未验证的那一步。禁止给 Agent 加 `search_graph` Tool（留给后续阶段）。

---

## 1. 硬边界

1. **不重构 P0。** 不改现有 `/api/chat`、`/api/chat/stream` 语义。旧 RAG 问答**不得**进入 LangGraph。  
2. **P1 是增量。** 新模块、新路由、新表（如需要）；不替换切块、embedding、`document_chunk`、余弦 SQL。  
3. **Agent** 是 P1 的通用智能编排。**Research Report 是 Agent 的一种任务模式**（`task=report`），不是第二套 Runtime。  
4. **Agent 必须复用 P0 RAG，不重写检索。** `search_knowledge` 是对 P0 检索**函数**的内部封装，直接调用现有 `search.py`，**不**经 HTTP 调用 `POST /api/search`。P0 的 `/api/search` 与 Agent Tool 共享同一检索实现。LangGraph **只决定**：何时搜、搜什么、是否再搜、如何使用结果。  
5. **智能摘要、自动标签、文档对比** 只用 LangChain Chain，**不** Graph 化。  
6. **知识关联、知识图谱与 LangGraph 解耦。** 图谱一期可最小落库（实体/关系），**不做复杂可视化。** 以后可将图谱查询做成 Agent Tool。  
7. **LangGraph 第一阶段只做：** State、Node、Tool、Conditional Edge、Loop、Streaming。  
8. **第一阶段不做：** Checkpoint、Human-in-the-loop、Subgraph、Multi-Agent。  
9. **Agent Loop 必须有上限：** `max_loops=3`（硬限制，防止空转与费用失控）。  
10. **渐进交付。** 不一次做完 P1。设计完成 → 只实现 P1.1 → 验证后再开下一阶段。

---

## 2. 功能怎么落地（不是一次做完）

| 功能 | 机制 | 阶段 |
|---|---|---|
| 智能摘要 | LangChain Chain；读文档 chunk / 解析稿 | **P1.1** |
| 自动标签 | LangChain Chain；只**追加**到现有 `tag` / `document_tag`，不删用户已打标签 | **P1.1** |
| 文档对比 | LangChain Chain；两篇 `document_id` | P1.2 |
| Agent | 一张 StateGraph；Tool 含 `search_knowledge` | P1.3 |
| 研究报告 | 同一 Agent 图，`task=report` | P1.3（同图不同任务） |
| 知识关联 | Chain 或一次检索 + 说明；不进图 | P1.4 |
| 知识图谱 | 最小 `entity` / `entity_link` 持久化；无复杂可视化 | P1.4 |

---

## 3. P1 整体架构

```text
[P0 不变]
  导入 → 解析 → 切块 → Embedding → document_chunk
  POST /api/search          余弦 TopK（可筛库/标签/kind）
  POST /api/chat[_stream]   LangChain 单链 RAG（不进图）

[P1 增量]
  Chain：摘要 / 自动标签 / 对比
  Tool：search_knowledge → 直接调用 search.py 函数（禁止 HTTP 调 /api/search）
  Graph（仅 Agent）：决定是否调用 Tool、循环次数 ≤ 3、流式输出
```

P0 负责「会搜、会一次问答」。P1 Agent 负责「多步时要不要再搜」。检索实现只有一份。

---

## 4. 模块边界

| 路径（落地时） | 允许 | 禁止 |
|---|---|---|
| `server/app/chat.py`、`routers/chat.py` | 保持 P0 | 改语义、改走 Graph |
| `server/app/search.py` | 供 HTTP 与 Tool 共用 | 为 Agent 另写一套向量查询 |
| `server/app/p1/chains.py` | 摘要、标签、对比 Chain | import LangGraph |
| `server/app/p1/tools.py` | `search_knowledge` 内部调用 `search.py` 函数 | HTTP 调 `/api/search`；在 Tool 里手写第二套 `<=>` SQL |
| `server/app/p1/graph.py` | 一张 StateGraph | Checkpoint、HITL、Subgraph、多 Agent |
| `server/app/routers/p1.py` | P1 HTTP / SSE | 改 `/api/chat` |
| `web` | 文档页按钮；Agent 另入口或对话页「模式」 | 把默认对话改成 Graph |

LlamaIndex、MinerU、Docker、Redis、Celery：仍禁止。

---

## 5. Agent / RAG 调用关系

```text
用户（task=agent | report）
        │
        ▼
LangGraph
        │
        ▼
reason          ← 只做 LLM 决策（要不要搜、搜什么）；禁止在本节点执行 Tool
        │
        │ 决定：search_knowledge
        ▼
run_tool        ← 只执行 Tool
        │
        ▼
search_knowledge Tool
        │  禁止 HTTP
        ▼
search.py 函数
        │
        ▼
document_chunk + pgvector 余弦（库/标签/kind、阈值 0.30）
        │
        ▼
hits → State.citations
        │
        ├─ loop_count < 3 且 reason 还要搜 ─► 再进入 reason（Conditional Edge）
        ├─ loop_count >= 3 或已够用 ─► generate
        ▼
generate（task=agent 问答 或 task=report 成文）
        │
        ▼
SSE  POST /api/agent/stream（不经过 /api/chat/stream）
```

职责拆开（面试可按此说）：**reason 决策，run_tool 执行，Conditional Edge 控制是否继续循环。** Tool 只调 P0 检索函数，不走 HTTP。

**Research Report：** 仍走这张图。`task=report` 时 generate 侧按报告组织（可先大纲再写），**不新开 Graph、不新开 Agent 进程。**

图谱查询：**第一阶段不是 Tool。** P1.4 落库后，后续阶段才可加 `search_graph` Tool。

---

## 6. LangGraph 第一阶段（P1.3 才引入，不在 P1.1）

**State：** `knowledge_base_id`、`task`（`agent` \| `report`）、`messages`、`citations`、`loop_count`、`max_loops=3`。报告需要时加 `outline`。

**Node：** `reason`（只决策，不执行 Tool）、`run_tool`（只执行 Tool）、`generate`。

**Tool：** 至少 `search_knowledge`（强制）；摘要/对比 Chain 做成 Tool 可放在 P1.3，不提前 Graph 化 Chain 本身。

**Conditional Edge：** 继续搜 vs 生成。

**Loop：** `loop_count` 自增；`>= max_loops` 必须进入 `generate`。

**Streaming：** `POST /api/agent/stream`，event 尽量与 P0 引用字段对齐，便于前端点进阅读页。

**不做：** Checkpoint、HITL、Subgraph、Multi-Agent。

---

## 7. 数据模型（按阶段，P1.1 最小）

**P1.1**
- 摘要：`document.summary` TEXT 可空（P1.1 采用此列，不另建摘要表）。  
- 自动标签：不改标签模型；AI 只 insert 尚不存在的 `document_tag`。

**P1.4（图谱最小，非 P1.1）**
- `entity`：id、knowledge_base_id、name、type、timestamps  
- `entity_link`：from_id、to_id、rel、document_id 可空  
无前端力导向图。

Agent 会话：复用 `conversation` / `message`；可用约定区分，**P1.1 不改这些表。**

---

## 8. API（P0 路径语义冻结）

| 阶段 | 方法 | 说明 |
|---|---|---|
| P1.1 | `POST /api/documents/{id}/summarize` | 生成并保存摘要 |
| P1.1 | `POST /api/documents/{id}/auto-tags` | 追加标签 |
| P1.2 | `POST /api/compare` | 两文档对比 |
| P1.3 | `POST /api/agent`、`POST /api/agent/stream` | Graph；body 含 `task`、`query`、`knowledge_base_id` |
| P1.4 | `POST /api/documents/{id}/graph` | 抽取实体/关系并落库 |
| P1.4 | `GET /api/graph` | 当前库实体与边 JSON；无可视化布局 |
| P1.4 | `GET /api/documents/{id}/related` | 一次检索相近文档；不进图 |

不修改 `POST /api/chat`、`POST /api/chat/stream`、`POST /api/search` 的契约。Agent Tool **不得** HTTP 调用 `/api/search`，只复用 `search.py` 函数。

---

## 9. P0 与 P1 边界（验收用语）

- 打开对话页默认提问 = P0 单链 RAG。  
- 点「摘要 / 自动标签」= P1 Chain，不启动 Graph。  
- 点 Agent / 生成报告 = P1 Graph，检索只通过 `search_knowledge` → **内部** `search.py`（不是 HTTP `/api/search`）。  
- 旧引用、库隔离、0.30 阈值：Agent 搜知识时必须与 P0 搜索一致。

---

## 10. 风险

- DashScope 费用：摘要/打标签按文档；Agent 受 `max_loops=3` 限制。  
- 自动标签与手打标签：只追加。  
- 过早上 Graph 会把摘要也图化 —— **禁止**；P1.1 无 LangGraph。

---

## 11. 当前实施计划

见 `memory-bank/implementation-plan.md` 文末 **P1.4**（已收口）。最小 `entity` / `entity_link`、抽取 Chain、关联走 `search.py`、阅读页列表已落地。无复杂可视化；无 `search_graph` Tool；未改 `/api/chat`。新工作须先改计划。
