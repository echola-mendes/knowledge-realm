# P2——RAG 与 Agent 能力增强

**状态：** 范围已按提出人「P2 PRD 边界修正」收敛；实施须先写入 `implementation-plan.md` 再改代码。  
**基线：** P0 / P1.1–P1.4 已落地。检索实现只有一份：`search.py` 的 `search_chunks`。

## 1. 版本目标

P2 主要解决两个问题：

1. 提升 RAG 检索准确性（闲聊误引用等）
2. 增强 Agent 的多轮对话、记忆和工具调用能力

不重构 P0 Chat 进 LangGraph。不把 `/api/chat` 改成拒答。

---

## 2. RAG 检索增强必须作用于统一检索链路

P1 规定：Chat、搜索页、Agent Tool 共用现有 `search.py` / `search_chunks`。

因此 Hybrid Search **不能只服务 Agent**，不要为 Agent 另写一套检索。

```text
Chat / 搜索页 / Agent search_knowledge
        │
        ▼
统一入口 search_chunks（内部流水线，调用方不变）
        │
        ├─ Vector Search（现有 pgvector 余弦）
        └─ Keyword Search（Elasticsearch BM25）
        │
        ▼
       RRF
        │
        ▼
     Rerank（分阶段，见 §3）
        │
        ▼
    相关性判断（分阶段，见 §3）
        │
        ▼
   返回最终检索结果
```

保持 P0/P1 已有行为：

- `search_chunks` 仍然是统一检索入口，现有调用方继续复用
- 无相关结果时不拒答
- 不相关 Chunk 不进入 Context
- 没有相关知识时不生成 Citation
- Chat 仍然可以正常闲聊

RRF、Rerank、相关性判断属于检索流水线**内部实现**，不作为独立产品功能拆分。

---

## 3. RAG 分阶段实现

不要第一阶段一次性做完 Vector + Keyword + RRF + Rerank + 阈值。

### 第一阶段

Hybrid Search：Vector + Keyword → RRF → 返回结果。

### 第二阶段

在 Hybrid 基础上增加 Rerank。

### 第三阶段

增加最终相关性判断。只负责：**检索结果是否进入 Context**。不负责决定 LLM 是否回答。

若结果不相关：

- 不进入 Context
- 不生成 Citation
- Chat 正常调用 LLM
- Agent 正常继续执行（可由 Tool Routing 决定是否用其他 Tool）

Web Search 是 Agent 可选 Tool，不是「检索失败后的强制兜底」。

---

## 4. 时间 / 来源筛选

当前已有：知识库、标签、`kind`。

**不要**假设另有独立「来源」「原始发布时间」字段。现网 `document`：

| 用途 | 现有字段 |
|---|---|
| 类型/来源近似 | `kind`：`pdf` / `docx` / `md` / `txt` / `url` / `note`（上传文件按扩展名，笔记 `note`，公开页 `url`） |
| URL | `source_url`（仅 url 类） |
| 时间 | `created_at` / `updated_at` |

P2 若做「按时间 / 来源筛选」：

- 来源：优先按现有 `kind`（及可选 `source_url` 是否为空），**不新造** `upload` / `manual` / `web` 枚举，除非另开迁移
- 时间：优先 `created_at` / `updated_at`；若业务要「原文发布时间」再新增字段
- 筛选作用在统一 `search_chunks`，不只做搜索页

---

## 5. Agent 会话与记忆

STM、Summary、LTM 是**记忆**；Checkpoint 是**图状态快照**。四者都在 P2 做，不把 Summary / LTM 留到 P3，但**禁止把 Checkpoint 当成第四种记忆或画进 `AgentState` 字段树**。

LTM **不能**用 `document_chunk` 或 `message` 代替，需独立数据模型（表结构见设计文档；是否向量化在 LTM 那一步写死）。

分层详见 `design-document.md` 第 4.7 节。摘要：

```text
图外权威来源
  STM      → conversation / message（最近 6 条）
  Summary  → conversation.summary
  LTM      → user_memory
  Checkpoint → LangGraph checkpointer（AgentState 快照）

图内 AgentState（本轮副本）
  messages / summary / ltm_hits / 裁剪后的 Tool 结果 / 路由字段
```

每次新的 Agent 请求从 DB 灌 STM 与 Summary，重置本轮 `loop_count` 与本轮 Tool 结果。不以 checkpointer 里的旧 `messages` 为聊天权威。

### 5.1 Short-term Memory

复用 `conversation` + `message`。Chat 已支持当前会话最近 6 条进 Prompt。

P2-Agent-1：Agent 也读当前 conversation 的最近 N=6 条进 State / Prompt。不新增聊天记录表。保持 Chat 最近 6 条逻辑兼容。本步不上 Summary、Checkpoint、LTM。

### 5.2 Conversation Summary

当本场历史超过窗口（最近 N=6）时：

- 对更早消息生成 Conversation Summary，**写入** `conversation.summary`
- Agent 上下文 = Summary + 最近 N 条
- 避免把全部 `message` 塞进 Prompt

Checkpoint 可以顺带存下 State 里已加载的 `summary` 字符串，但摘要的权威存储是 `conversation.summary`，不是 checkpointer。

Chat 是否同步用 Summary：实施计划里再定；P2 至少覆盖 Agent。

### 5.3 LangGraph State

P1 已有 `AgentState`。P2 按步骤扩展字段（`summary`、`ltm_hits`、子任务列表等），不重建 State。

### 5.4 Checkpoint（P2-Agent-2，与 Summary 分步）

- 保存「这一次图跑到哪、当前 `AgentState` 是什么」，不保存「这个会话之前发生了什么」（那是 STM / Summary）
- `thread_id` = `conversation_id`
- 同一数据库 Postgres checkpointer，禁止 Redis
- 对 citations / Tool 结果做上限裁剪
- 新 user 轮次必须按第 4.7 节重置策略加载 STM，避免与 checkpoint 旧消息叠两份

### 5.5 Long-term Memory

保存**跨 Conversation** 的长期用户信息，例如：用户背景、技术栈、偏好、长期目标。

- 不是聊天日志（`message`）
- 不是知识库切片（`document_chunk`）
- 本轮读到的结果可放进 State 的 `ltm_hits`；表才是权威
- 由 reason 决定何时读写；禁止第二套「知识库向量表」冒充 LTM

---

## 6. Agent 能力扩展

`reason` 是统一路由节点。禁止每个 Tool 自己判断该不该跑。

### 6.1 Web Search 与 Tool Routing（P2-Agent-5）

新增 `web_search` Tool，与 `search_knowledge` 并列。`reason` 只在三种结果中选：

```text
reason
  ├── DIRECT   （不调 Tool，generate）
  ├── RAG      （search_knowledge）
  └── WEB      （web_search）
```

禁止「RAG 无结果 → 强制 Web Search」。`max_loops` 仍为 3。本步不上 PLAN。

### 6.2 轻量 Task Planning（P2-Agent-6）

在 6.1 的三种路由之上增加：复杂问句可先写入最多 3 条有序子任务。随后每一圈仍由**同一个** `reason` 只选 DIRECT / RAG / WEB 执行当前子任务，最后 generate 汇总。

```text
reason
  ├── DIRECT
  ├── RAG
  ├── WEB
  └── （仅首圈可写入）≤3 条子任务，不是子图、不是动态 DAG
```

不实现复杂 Planner、Multi-Agent、第二张 Graph。`max_loops=3` **保持不变**。子任务数量必须能在 3 圈内跑完。

---

## 7. P2 最终范围

**RAG（统一 `search_chunks` 流水线，分阶段）**

- Hybrid Search（pgvector 向量 + Elasticsearch BM25，RRF 融合）
- RRF / Rerank / 相关性判断（内部阶段，见 §3）
- 时间 / 来源筛选（基于现有字段，见 §4）

**Agent**

- 接入现有 Conversation / Message（短期记忆，P2-Agent-1）
- Checkpoint（图快照，P2-Agent-2；与 Summary 分步）
- Conversation Summary（本场过长历史压缩，P2-Agent-3）
- Long-term Memory（跨会话用户信息，独立存储）
- Web Search + 统一 reason 路由 DIRECT / RAG / WEB（P2-Agent-5）
- 轻量 Task Planning（P2-Agent-6：≤3 子任务，同一张图）

**P3 暂不实现**

- 知识冲突检测、知识缺口分析、自动知识整理、主动知识推荐
- Multi-Agent
- 知识库自动更新
- 复杂知识图谱推理

---

## 8. 验收标准

- [ ] Hybrid 在 `search_chunks` 内，Chat / 搜索 / Agent Tool 同一套结果语义
- [ ] 无相关：不进 Context、无 Citation；Chat 仍闲聊；不拒答
- [ ] 不因无命中强制 Web Search
- [ ] Agent 用 `conversation_id` 读取最近消息；无第二套会话表
- [ ] 历史过长时用 Conversation Summary + 最近 N 条，不把全量 message 进 Prompt
- [ ] Checkpoint：`thread_id` 关联 `conversation_id`；快照可跨请求/重启继续 invoke；STM/Summary 权威仍在表内，不与 checkpoint 旧消息叠两份
- [ ] Long-term Memory 独立于 `message` 与 `document_chunk`，可跨会话使用
- [ ] 时间/来源筛走 `search_chunks`，基于现有 `kind` / `created_at`（或文档另定字段）
- [ ] `max_loops=3` 未放宽；Planning 子任务数量受此约束
- [ ] 无 Multi-Agent
