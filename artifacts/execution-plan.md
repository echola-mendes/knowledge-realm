# Execution Plan：AI 决策审计（Trace.md V1.1）

> 依据：`artifacts/prd-sub.md`。从顶部取第一个未全 ✅ 的 Step 执行。  
> 栈：FastAPI / Vue3；模型入 `models.py`，审计代码落 `app/audit/`；禁止 LangSmith。  
> **执行约定：** 用户已确认连续执行——每 Step 验收全 `[✅]` 后直接进入下一 Step，全量回归放末步。

---

## Step 1：数据模型与迁移

### 目标

落地 `decision_run` / `decision_span` 两表。

### 方案

1. `models.py`：`DecisionRun`（id/message_id 可空/conversation_id/user_id/mode/query/status/created_at，索引 `(user_id, created_at)`、`message_id`、`conversation_id`）；`DecisionSpan`（id/run_id FK/seq/node_type/decision JSONB/rationale/evidence_refs JSONB/metrics JSONB/created_at，索引 `(run_id, seq)`）
2. Alembic 迁移（延续 `20260904_0023_news` 序号）

### 验收

- [✅] 迁移可 upgrade / downgrade
- [✅] 两表与索引存在；`message_id` 可空、其余关键列 NOT NULL

---

## Step 2：DecisionRecorder

### 目标

`app/audit/recorder.py` 提供故障隔离的埋点组件。

### 方案

1. `DecisionRecorder(session_factory)`：`start_run(user_id, conversation_id, mode, query) -> run_id`（独立 session 立即落 `running` 行）；`add_span(node_type, decision, rationale, evidence_refs, metrics)`（内存缓冲，seq 自增）；`finish_run(status, message_id=None)`（独立事务写 spans + 更新 run；message_id 可空）
2. 所有公开方法内部 try/except 吞异常（记 `logger.warning`），绝不向调用方抛错
3. `app/audit/__init__.py` 导出

### 验收

- [✅] 单测：start→add→finish 后 run+spans 落库且 seq 有序
- [✅] 单测：DB 故障（如坏 run_id/会话关闭）时 recorder 不抛异常

---

## Step 3：Chat 埋点接入

### 目标

`/api/chat` 与 `/api/chat/stream` 每轮落一条链（retrieve + generate）。

### 方案

1. `run_chat` 增加可选 `recorder` 参数：检索后 add_span(`retrieve`：tool=`search_knowledge`、query、chunk 证据)；generate 后 add_span(`generate`：答案摘要 + elapsed)；落库 assistant Message 后 `finish_run("success", message_id=…)`；Key 缺失/异常路径 `finish_run("failed")` 后原样抛错；recorder 为 None 时零开销
2. `routers/chat.py` `_http_chat` 创建 recorder 并传入（mode=`chat`）
3. span 全程 try/except 由 recorder 兜底，不影响回答

### 验收

- [✅] Chat 测试轮后 DB 有 run(status=success, 绑 assistant message_id) + 2 spans
- [✅] 模拟 recorder 抛错，主回答仍 200（单测）
- [✅] 既有 chat 测试全绿（recorder 缺省路径不变）

---

## Step 4：知识 Agent 埋点接入

### 目标

`task=knowledge` 每轮落一条链（route/retrieve/generate，多圈多组）。

### 方案

1. `graph.py`：`node_reason` / `node_generate` 增加可选 `config: RunnableConfig` 参数，与 `node_run_tool` 一样从 `configurable.get("decision_recorder")` 取；reason → `route` span（action=search/web/generate/graph + rationale，无则「未给出理由」+ usage）；run_tool → `retrieve` span（tool 名、query、citations/web_hits 证据截断）；generate → `generate` span（答案摘要 + tokens）
2. `routers/master.py`：`_invoke_knowledge_graph` 的 configurable 注入 recorder(mode=`knowledge`)；`_agent_persist` 捕获 assistant Message id 回传（内部 key，不进 schema）；成功后 `finish_run("success", message_id)`，异常路径 failed
3. 不动 master/plan/booking 路径与 `/api/agent/trace`

### 验收

- [✅] knowledge 测试轮后 run + route/retrieve/generate spans 按序落库
- [✅] 多圈场景 span seq 单调递增（单测）
- [✅] 既有 agent 测试全绿

---

## Step 5：查询 API

### 目标

3 个只读接口，Session 鉴权、本人数据。

### 方案

1. `schemas.py`：DecisionRunOut / DecisionSpanOut / DecisionRunDetail
2. `routers/decisions.py`：`GET /api/decisions`（limit/offset + mode/status/conversation_id/start/end 过滤）、`GET /api/decisions/{run_id}`（run+有序 spans）、`GET /api/messages/{id}/decision`（按 assistant 消息反查）；均按 `user_id` 过滤，他人资源 404；`main.py` include

### 验收

- [✅] 契约测试：未登录 401；他人 run/消息 404；列表过滤与分页生效；详情 spans 有序
- [✅] message 反查返回 run + spans

---

## Step 6：前端决策审计页

### 目标

`/monitoring/decisions` 从占位页替换为列表 + 详情。

### 方案

1. `web/src/api.ts`：listDecisions / getDecision / getMessageDecision 客户端
2. `web/src/views/DecisionAuditView.vue`：列表（时间/模式/问题摘要/状态）+ 过滤 + 行点击进详情（路由 `/monitoring/decisions/:id`）；详情自上而下线性节点卡片，展开 decision/rationale/evidence/metrics
3. `router.ts` 替换占位组件；样式对齐 `web/style.md` 与现有 Operate 页

### 验收

- [✅] 路由可进入列表与详情（路径验证）
- [✅] `npm run typecheck` 通过

---

## Step 7：回归与文档同步

### 目标

全量回归绿；文档同步。

### 方案

1. 全量 pytest（对照预存 flaky 失败集）
2. `docs/TECH.md`（新表/模块/API 条目）、`docs/PRD.md` §3.7/§4.4 状态同步；AGENTS 栈未变不动
3. memory/architecture 按 Phase 4 归档

### 验收

- [✅] 全量 pytest 无新增失败（对照基线：275 通过，2 个失败为预存 flaky，与搬迁前基线一致）
- [✅] TECH.md / PRD.md 已更新
- [✅] execution-plan 全部 [✅]

---
