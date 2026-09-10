# 知域 — AI 决策审计（极简版）

**版本：** V1.1（极简）  
**模块：** 监控 → 决策审计  
**状态：** 待开发（占位页已接入）  
**关联：** [`PRD.md`](PRD.md) §3.7 / §4.4；操作审计见 [`PRD-OPERATIONS.md`](PRD-OPERATIONS.md)

---

## 1. 要解决什么

生产对话里只能看到答案和引用，无法复盘「这一轮为什么选 RAG / Web / Graph、查了哪些资料」。

现有 `/api/agent/trace` + 调试页是**旁路实验**：不落库、不绑 `message_id`，不能事后按会话回看。

**本期只做一件事：** 每条 assistant 回复落一条业务决策链，可在监控页打开。

---

## 2. 目标 / 非目标

### 2.1 目标

- 每轮 AI 回答 → 一条 `DecisionRun`，内含若干 `DecisionSpan`
- 记录：路由/工具选择、选型摘要、证据（chunk 等）、可选耗时/token
- 绑 `conversation_id` + `message_id`，Session 用户隔离
- 监控 → 决策审计：列表 + 详情（线性节点即可）
- 埋点接口统一：`DecisionRecorder`，新 Agent 只加埋点

### 2.2 非目标（明确不做）

| 不做 | 原因 |
| --- | --- |
| LangSmith / 自建 Trace 平台 | 隐私与栈约束；调试页已够技术排查 |
| 三受众 Explain / Validator / Judge | 过重，面试 ROI 低 |
| 独立 Token 看板、告警熔断 | 延期 |
| 把 CoT 原文展示给用户 | 只记结构化决策摘要 |
| 操作审计 | 见 PRD-OPERATIONS |
| 替代 `/debug` | 调试页继续旁路实验 |

粒度澄清：**不是整会话一条链**，而是**每一轮 assistant 消息一条链**。

---

## 3. 入口与边界

```text
侧栏「监控」
  ├── 决策审计   /monitoring/decisions   ← 本文
  └── 操作审计   /monitoring/operations
```

| | 调试页 `/debug` | 决策审计（本期） |
| --- | --- | --- |
| 落库 | ❌ | ✅ |
| 绑 message | ❌ | ✅ |
| 用途 | 开发实验 | 生产复盘 |

`/api/agent/trace` **暂不强制合并**；能复用 Recorder 更好，不做硬性双轨消除。

对话内「查看决策链」：**可选增强**，不做本期验收项。

---

## 4. 覆盖范围（本期）

| 模式 | 路径 | 本期 |
| --- | --- | --- |
| Chat | `/api/chat/stream` | ✅ retrieve + generate |
| 知识 Agent | `task=knowledge` → `knowledge_flow` | ✅ analyze / retrieve / sufficiency / … / generate |
| ReAct | `task=react` → `graph.py`（Tool Calling） | ✅ tool_call / tool_result（+ 终答 span）；Master knowledge 共用图本期不接审计 |
| Multi Agent / Report | `master.py` | ⏳ 下一期再接 |
| plan / booking | 子图 | ⏳ 下一期再接 |

---

## 5. 数据模型（两张表）

### 5.1 `decision_run`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID |
| `message_id` | assistant 消息，流式失败可空 |
| `conversation_id` | 会话 |
| `user_id` | 隔离 |
| `mode` | `chat` / `knowledge` / `react` |
| `query` | 当轮用户问题 |
| `status` | `running` / `success` / `failed` |
| `created_at` | |

索引：`(user_id, created_at)`、`(message_id)`、`(conversation_id)`。

### 5.2 `decision_span`

| 字段 | 说明 |
| --- | --- |
| `id` | UUID |
| `run_id` | FK |
| `seq` | 顺序 |
| `node_type` | `route` / `retrieve` / `generate` / `tool_call` / `tool_result`（≤ `String(20)`；react 用后两者） |
| `decision` | JSONB，最终选择（如 `{"action":"rag"}`） |
| `rationale` | 选型摘要（短文本，非 CoT） |
| `evidence_refs` | JSONB，如 `[{type, id, score, excerpt?}]` |
| `metrics` | JSONB，可选 `elapsed_ms` / `tokens` |
| `created_at` | |

不建 `decision_explanation` 表。不做 `parent_span_id` 树（本期线性即可）。

---

## 6. 埋点（DecisionRecorder）

从 `RunnableConfig.configurable` 注入：

```python
recorder = configurable.get("decision_recorder")
```

```python
class DecisionRecorder:
    def start_run(...) -> UUID: ...
    def add_span(node_type, decision=None, rationale=None, evidence_refs=None, metrics=None) -> UUID: ...
    def finish_run(status: str) -> None: ...
```

`route` / `reason`：写入 `action` + 短 `rationale`（可来自模型 JSON 字段，失败则写「未给出理由」）。  
`retrieve`：工具名、query、候选/入选 chunk id（excerpt 可截断）。  
`generate`：一句结论摘要即可（答案全文已在 message）。

Recorder 故障：**不影响主回答**；该轮可不落库或 `status=failed`。

---

## 7. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/decisions` | 列表：时间、mode、query 摘要、status；筛 conversation_id / 时间 |
| GET | `/api/decisions/{run_id}` | run + 有序 spans |
| GET | `/api/messages/{id}/decision` | 按消息反查（对话页预留） |

Session 鉴权；仅本人数据。

---

## 8. 前端（极简）

**列表：** 时间、模式、问题摘要、状态、详情。  
**详情：** 自上而下节点列表（route → retrieve → generate）；展开看 decision / rationale / evidence / metrics。  
**不做：** DAG 编辑器、多 Tab 解释视图、跳转 LangSmith。

样式：`web/style.md` Operate 工具页，对齐调试/基础页。

---

## 9. 验收

1. 知识 Agent 或 Chat 问一轮 → DB 有对应 `decision_run` + spans  
2. `message_id` 能反查到该 run  
3. 监控页能列出并打开详情看到路由与证据 id  
4. Recorder 异常时主流程仍能正常回答  

---

## 10. 技术约束

- 不引入 LangSmith；不新增 Docker 可观测栈  
- Chat 仍用现有 Chain；Agent 仍用现有 LangGraph  
- 身份仅 Session；绑定 `127.0.0.1`  

---

## 11. 以后再说（不写进本期排期）

- Master / plan / booking 全路径  
- 对话页消息旁入口  
- Explain / Judge、指标告警、与操作审计 UNION  
- 按 `biz_id`（行程单/预订）一键拉链  
- **接入 LangSmith 基础 Trace** → 见下一版 [`Trace_LangSmith.md`](Trace_LangSmith.md)

---

## 12. 版本

- **V1.0**：完整审计愿景（含 Explain / Judge / 多 Agent）  
- **V1.1**：极简版；只保留生产落库决策链 + 监控列表详情（本文）  
- **V1.2**：LangSmith 基础 Trace + Decision 保留 → [`Trace_LangSmith.md`](Trace_LangSmith.md)  
