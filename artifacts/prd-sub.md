# 当前子需求：AI 决策审计极简版（Trace.md V1.1）

> 需求来源：`docs/Trace.md`（用户需求文档，只读）  
> 前置：包拆分已完成（`app/agent/` `app/ingest/` `app/rag/`）；监控侧栏与 `/monitoring/decisions` 占位页已接入  
> 包路径约定：审计代码落 `app/audit/`（见 `docs/split.md`）

## 1. 目标

每条 assistant 回复落一条业务决策链（`DecisionRun` + 线性 `DecisionSpan`），在「监控 → 决策审计」页可按列表打开详情，复盘该轮路由与证据。本期覆盖 Chat 与知识 Agent 两条路径。

## 2. 背景

现有 `/api/agent/trace` + 调试页是旁路实验：不落库、不绑 `message_id`。生产对话只能看到答案与引用，无法事后复盘「为什么选 RAG / Web / Graph、查了什么」。粒度：**每轮 assistant 消息一条链**，非整会话一条。

## 3. 功能范围

### 后端

- 表：`decision_run`、`decision_span`（Alembic 迁移；模型入 `models.py`）
- 埋点：`app/audit/recorder.py` 提供 `DecisionRecorder`（start_run / add_span / finish_run），经 LangGraph `RunnableConfig.configurable` 与函数参数注入
- 接入点：
  - Chat：`/api/chat` 与 `/api/chat/stream`（共用 `_http_chat` → `run_chat`）→ `retrieve` + `generate` 两个 span
  - 知识 Agent：`task=knowledge` → `_invoke_knowledge_graph` → `graph.py` 的 reason / run_tool / generate → `route` + `retrieve` + `generate` span（多圈多组）
- API（Session 鉴权，仅本人数据，新 `routers/decisions.py`）：
  - `GET /api/decisions`（列表：conversation_id / mode / status / 时间过滤）
  - `GET /api/decisions/{run_id}`（run + 有序 spans）
  - `GET /api/messages/{id}/decision`（按 assistant 消息反查，对话页预留）

### 前端

- `/monitoring/decisions` 占位页替换为 `DecisionAuditView.vue`
- 列表：时间、模式、问题摘要、状态；筛 conversation_id / 时间
- 详情：自上而下线性节点（route → retrieve → generate），展开看 decision / rationale / evidence / metrics
- 样式对齐 `web/style.md` Operate 工具页；不做 DAG / 多 Tab

### 文档

- Phase 4 同步 `docs/TECH.md`、`docs/PRD.md`；不改 `docs/Trace.md`

## 4. 非目标

- LangSmith / 自建 Trace 平台 / 新增 Docker 可观测栈
- 三受众 Explain / Validator / Judge；独立 Token 看板、告警熔断
- CoT 原文展示（只记结构化摘要）
- 操作审计（PRD-OPERATIONS 另期）
- Master / plan / booking 全路径埋点（下一期）
- `/api/agent/trace` 强制合并、`/debug` 改造（继续旁路）
- 对话页「查看决策链」入口（可选增强，不做验收项）

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 粒度 | 每轮 assistant 消息一条 `decision_run`；`mode` ∈ `chat` / `knowledge` |
| run 状态 | `running` → `success` / `failed`；开始即落库（独立 session），正常轮绑 `message_id`，失败轮可空 |
| span 结构 | `seq` 线性递增；`node_type` ∈ `route` / `retrieve` / `generate`；无 `parent_span_id` 树 |
| route/reason | `decision={"action":...}` + 短 `rationale`（模型未给理由写「未给出理由」） |
| retrieve | 工具名、query、候选/入选 chunk id（excerpt 截断）；web 命中记 `type:"web"` |
| generate | 一句结论摘要（答案全文已在 message）+ 可选 `elapsed_ms` / `tokens` |
| 隔离 | Recorder 全程 try/except 包裹；任何故障不影响主回答（不落库或 status=failed） |
| 鉴权 | 列表/详情/反查均按 Session 用户过滤；他人 run 返回 404 |

## 6. 输入与输出

- 输入：Chat 请求、knowledge Agent 请求（现有 `/api/chat*`、`/api/agent*`）
- 输出：`decision_run` / `decision_span` 行；3 个查询 API；决策审计前端页

## 7. 涉及模块

- 新：`app/audit/__init__.py`、`app/audit/recorder.py`、`routers/decisions.py`、迁移、`web/src/views/DecisionAuditView.vue`
- 改：`models.py`、`schemas.py`、`main.py`（include router）、`app/rag/chat.py`（返回 assistant message id + 埋点）、`routers/chat.py`（注入 recorder）、`routers/master.py`（knowledge 路径埋点 + persist 回传 message id）、`app/agent/graph.py`（三节点从 configurable 取 recorder）、`web/src/router.ts`、`web/src/api.ts`
- 不动：`master.py` 埋点、plan/booking 子图、`/api/agent/trace`、`/debug`

## 8. 验收标准

| ID | 标准 |
| --- | --- |
| AC-01 | Chat 问一轮 → DB 有 `decision_run`(mode=chat, status=success, 绑 message_id) + retrieve/generate spans |
| AC-02 | knowledge Agent 问一轮 → run + route/retrieve/generate spans，多圈时 span 按序递增 |
| AC-03 | `GET /api/messages/{assistant_msg_id}/decision` 反查到该 run |
| AC-04 | 监控页列表可打开详情，能看到路由 action 与证据 chunk id |
| AC-05 | Recorder 抛异常时主回答不受影响（单测模拟 recorder 故障） |
| AC-06 | 未登录 401；他人 run/消息 404 |
| AC-07 | 前端路由可进入列表与详情；typecheck 通过 |

## 9. 待确认问题

1. Chat 非流式 `/api/chat` 与流式 `/api/chat/stream` 共用实现，计划一并落链（Trace 表只列了 stream）——默认两者都接，可接受？
2. run 起始即落库（status=running，独立 DB session），完成后更新状态并写 spans——比「完成后一次性写」多一次写入但可观测失败轮，默认按此实现？
3. 列表分页默认 `limit=50&offset=0` + `mode/status/conversation_id/start/end` 过滤——够用？
