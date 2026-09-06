# 知域 — AI 决策审计需求文档（PRD-DECISIONS）

**版本：** V1.0  
**模块：** 知域 → 监控 → 决策审计  
**状态：** 待开发（P0：占位页已接入；数据与 API 待实现）  
**关联：** 操作审计见 [`PRD-OPERATIONS.md`](PRD-OPERATIONS.md)；产品总览见 [`PRD.md`](PRD.md) §3.7、§4.4。

---

## 1. 需求背景

对话页 Chat / Agent / Multi Agent / Report 对用户呈现为黑盒：只能看到最终答案与引用，无法追溯「为何选某工具、依据哪些资料、如何推出结论」。现有 `/api/agent/trace` 与调试页 Agent Trace 为**旁路、不落库、不绑会话**，无法对真实对话复盘，也无法面向业务/审计给出可辩护的解释。

本模块建设**可扩展的 AI 决策审计能力**：为每次 assistant 回复生成结构化决策链，支持对话内查看、监控页台账检索、按业务单据一键拉全链，并为后续多 Agent 扩展预留统一埋点协议（新 Agent 只加埋点，不重写审计系统）。

---

## 2. 目标与非目标

### 2.1 目标

- 每次 AI 回答绑定一条 **DecisionRun**（决策链根）与若干 **DecisionSpan**（决策节点）。
- 每个决策节点记录：决策场景、候选选项、选型依据、最终结论、关联证据。
- 对话页 assistant 消息可「查看决策链」；监控 → 决策审计提供列表与详情。
- **可扩展**：新 Multi Agent / 子图通过 `DecisionRecorder` 埋点接入，不新增审计表或 API。
- 异步生成 **三受众解释**（dev / business / user），经校验后展示；不暴露模型原始 CoT。
- 可解释模块故障时可降级：保留原始 span + raw 日志，高风险场景转人工复核（与 booking HITL 对齐）。

### 2.2 非目标（本期不做）

- 不替代 `/debug` 检索评测与 Hybrid Search 实验能力（可共用数据源，入口分离）。
- 不把模型原生「思考过程」直接展示给用户。
- 不做 RBAC；身份仍仅来自 Session，`user_id` 隔离。
- 操作审计（文档导入、向量化等）见 PRD-OPERATIONS，本文不实现。

---

## 3. 产品入口

### 3.1 监控二级菜单（与操作审计并列）

```text
侧栏「监控」
  ├── 决策审计   /monitoring/decisions    ← 本文
  └── 操作审计   /monitoring/operations   ← PRD-OPERATIONS
```

### 3.2 对话内入口（P1）

- 每条 assistant 消息旁「查看决策链」→ 打开该 `message_id` 对应 DecisionRun 详情（抽屉或跳转监控详情）。

### 3.3 与调试页关系

| 能力 | 调试页 `/debug` | 决策审计 |
| --- | --- | --- |
| Agent Trace 旁路实验 | ✅ | 生产路径自动落库 |
| 绑 conversation / message | ❌ | ✅ |
| Master 多 Agent 全路径 | ❌ | ✅（P1 起） |
| 面向业务解释 | ❌ | ✅（P2） |

实现完成后，`/api/agent/trace` 应复用同一 `DecisionRecorder`，避免双轨。

---

## 4. 核心原则

### 4.1 可信依据 = 埋点执行路径，不是 CoT 独白

- **Ground truth**：代码实际执行的 span 序列（route → decide → retrieve → generate）。
- **待校验声明**：模型 JSON 中的 `rationale`、事后 Explain 文案。
- 二者不一致 → 标记 `logic_mismatch`，dev 可见；user 视图用 span 重生成或降级为「见引用来源」。

### 4.2 记「决策事件」，不记「某个 Agent 实现细节」

- 统一 `DecisionSpan` schema；扩展通过开放 `node_type` 与前端展示插件注册。
- 新 Agent 仅在图节点调用 `recorder.span(...)`，不新建审计子系统。

### 4.3 与操作审计的数据关系

- **推荐 Phase 1**：独立表 `decision_run` / `decision_span`（本文），操作审计用 `audit_event`（PRD-OPERATIONS）。
- **可选统一**：`audit_event.category = 'ai_decision'` 且 `ref_id = decision_run.id`；监控列表可 UNION 展示，详情仍各走专用 API。
- **实现顺序**：先完成 PRD-DECISIONS（P0–P2），PRD-OPERATIONS 复用相同「trace_id + span 树」展示组件时可共享前端组件，不必共享同一张宽表。

---

## 5. 覆盖范围（对话模式）

| 对话模式 | task / 路径 | 决策链范围 |
| --- | --- | --- |
| Chat | `/api/chat/stream` | retrieve（search_chunks）+ generate；无 reason 循环 |
| Agent（知识） | `task=knowledge` → `graph.py` | reason ↔ run_tool → generate |
| Multi Agent | `task=agent` → `master.py` | intent 路由 + 子图（knowledge/chat/plan/booking） |
| Report | `task=report` → Master → knowledge 子图 | 同上 + report 生成与 `report_url` 绑定 |

---

## 6. 数据模型

### 6.1 `decision_run`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | trace_id |
| `message_id` | UUID FK | assistant 消息，可空（流式失败时） |
| `conversation_id` | UUID FK | 会话 |
| `user_id` | UUID FK | 隔离 |
| `mode` | enum | chat / knowledge / agent / report |
| `task` | string | agent / report / knowledge 等 |
| `biz_type` | string | message / conversation / report / plan / booking / … |
| `biz_id` | UUID/string | 业务单据 ID |
| `query` | text | 用户当轮提问 |
| `status` | enum | running / success / failed / degraded |
| `chain_complete` | bool | 是否有 finalize 且关键 span 齐全 |
| `explain_status` | enum | pending / ok / failed / skipped |
| `raw_log` | JSONB | 降级时原始 LLM/检索摘要（脱敏） |
| `created_at` | timestamptz | |

索引：`(user_id, created_at)`、`(conversation_id)`、`(biz_type, biz_id)`、`(message_id)`。

### 6.2 `decision_span`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | |
| `run_id` | UUID FK | |
| `parent_span_id` | UUID | 串 Master → 子图 |
| `seq` | int | 顺序 |
| `node_type` | string | 见 §6.3 |
| `scene` | text | 决策场景 |
| `candidates` | JSONB | 候选选项列表 |
| `decision` | JSONB | 最终选择 |
| `rationale` | text | 选型依据（结构化 JSON 内亦可） |
| `conclusion` | text | 该步产出摘要 |
| `evidence_refs` | JSONB | `[{type, id, excerpt, score}]` |
| `context_snapshot` | JSONB | kb_id、history_len、allow_web 等 |
| `metrics` | JSONB | elapsed_ms、tokens |
| `raw_dev` | JSONB | 仅 dev 视图 |
| `created_at` | timestamptz | |

### 6.3 `node_type`（开放枚举）

**通用（所有 Agent 复用）：**

`route` | `decide` | `retrieve` | `generate` | `hitl` | `finalize`

**扩展（按 Agent 注册，不改表）：**

`plan_search` | `plan_compare` | `booking_confirm` | …

前端：通用节点默认卡片；扩展节点可注册 Vue 展示组件。

### 6.4 `decision_explanation`（P2）

| 字段 | 说明 |
| --- | --- |
| `run_id` | FK |
| `audience` | dev / business / user |
| `content` | 生成文案 |
| `validated` | bool |
| `validation_detail` | JSONB |

### 6.5 `biz_type` 绑定

| biz_type | 实体 | 场景 |
| --- | --- | --- |
| `message` | Message.id | 默认 |
| `conversation` | Conversation.id | 整会话 |
| `report` | MinIO key / report_url | Report |
| `plan` | PlanRecord.id | 行程 |
| `booking` | BookingRecord.id | 预订 HITL |

---

## 7. 埋点协议（DecisionRecorder）

### 7.1 注入方式

所有 LangGraph 图（`graph.py`、`master.py`、`plan_agent.py`、`booking_agent.py` 及未来子图）从 `RunnableConfig.configurable` 读取：

```python
recorder: DecisionRecorder | None = configurable.get("decision_recorder")
```

`/api/agent/stream`、`/api/chat/stream` 在 invoke 前创建 `DecisionRun`，传入 recorder；`/api/agent/trace` 复用同一实现。

### 7.2 Recorder 接口（示意）

```python
class DecisionRecorder:
    def start_run(...) -> UUID: ...
    def start_span(node_type, scene, parent_id=None, **kwargs) -> UUID: ...
    def end_span(span_id, decision, rationale, evidence_refs, metrics): ...
    def mark_degraded(reason: str): ...
```

### 7.3 Prompt 扩展（decide / route）

`reason_decide`、`classify_intent` 等节点 JSON 输出增加：

```json
{
  "action": "rag",
  "query": "...",
  "rationale": "问题涉及制度条款，需查知识库",
  "alternatives_considered": ["direct", "web"]
}
```

`rationale` 为**决策摘要**，不是对用户展示的 CoT。

### 7.4 retrieve span 内容

- 工具名：`search_knowledge` / `search_graph` / `web_search`
- 入参：`search_query`
- 候选：top-k 片段 id + score（与 `search_debug` 字段对齐，可截断）
- 入选：写入 `citations` 的 chunk_id 列表

---

## 8. 解释生成与校验（P2）

### 8.1 三受众 Explain Chain

| 受众 | 内容 |
| --- | --- |
| dev | 全量 span、raw_dev、检索分数、token |
| business | 路径摘要、关键依据、结论、风险标签 |
| user | 自然语言理由 + 来源文档名；无技术细节 |

异步生成（`BackgroundTasks` 或 arq），不阻塞首字流式。

### 8.2 校验机制

1. **结构一致（必做）**：Explain 每步可映射到 `span_id`；证据 id 存在于 retrieve span。
2. **语义一致（可选）**：LLM Judge 对比 Explain 与 span；低分不展示 user 视图。
3. **Claim 支撑**：论断 ↔ evidence；`unsupported` 不得进入 user 解释。

### 8.3 降级

| 等级 | 条件 | 行为 |
| --- | --- | --- |
| L1 | Explain/Validator 故障 | 保留 span + raw_log；user 仅 citations |
| L2 | Recorder 故障 | 原始请求/响应日志 |
| L3 | 校验率暴跌或 L1+L2 | 暂停高风险自主决策；booking 强制 HITL |

环境变量示例：`DECISION_EXPLAIN_REQUIRED=true`。

---

## 9. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/decisions` | 列表；筛选 conversation_id、biz_type、biz_id、mode、status、时间 |
| GET | `/api/decisions/{run_id}` | 完整 run + spans + explanations |
| GET | `/api/decisions/{run_id}/graph` | 图结构（节点+边）供可视化 |
| GET | `/api/messages/{id}/decision` | 对话页快捷入口 |

鉴权：Session；`user_id` 隔离；`raw_dev` 仅 debug 开关开启时返回。

生产流：`agent_stream` / `chat_stream` 落库后 `message.decision_run_id`（或 join 表）可反查。

---

## 10. 前端

### 10.1 监控 → 决策审计列表

列：时间、会话摘要、模式、问题摘要、链完整、解释校验、耗时、操作（详情）。

筛选：关键词、模式、结果、时间范围。

### 10.2 详情页

- 决策路径图（DAG）：关键转折点高亮。
- Tab：结果 / 决策链 / 工具与证据 / 解释（dev|business|user）。
- 证据点击跳转文档切片或引用侧栏。

样式遵循 `web/style.md`（工具型 Operate 界面，对齐调试页/基础页）。

### 10.3 对话页（P1）

assistant 消息「查看决策链」→ 详情或抽屉。

---

## 11. 监控指标（P3）

| 指标 | 说明 |
| --- | --- |
| 决策链完整率 | 含 finalize 且 decide 有 rationale 的 run 占比 |
| 解释生成成功率 | Explain 完成占比 |
| 解释一致性率 | 校验通过占比 |
| 审计追溯耗时 | GET by biz_id P99 |
| 降级触发次数 | degraded 计数 |

异常告警：阈值可配置；对接监控页汇总（与 PRD-OPERATIONS 指标区并列）。

---

## 12. 实施分期

| 阶段 | 交付 | 验收 |
| --- | --- | --- |
| **P0** | 表迁移；`DecisionRecorder`；接入 `graph.py` + `chat`；`agent_stream` 落库；监控占位页 → 决策审计列表（可先 mock/空态） | 知识 Agent 一问一链；message 可反查 |
| **P1** | 接入 `master.py` 全路径；对话页「查看决策链」；废弃 trace 双轨 | Multi Agent / Report 可串联 |
| **P2** | Explain 三视图 + Validator；claim–evidence | user 视图可展示合理解释 |
| **P3** | 指标、告警、降级熔断 | booking 故障时强制 HITL |

---

## 13. 技术约束（AGENTS.md）

- 后端 FastAPI；决策链编排仍用现有 LangGraph，不把 `/api/chat` 改成 LangGraph。
- P1 Agent 必须经 Tool 调 pgvector；Explain/校验用 Chain，不用 LangGraph。
- 短任务 Explain 可用 BackgroundTasks；批量 replay 可用 arq。
- 绑定 `127.0.0.1`；身份仅 Session。

---

## 14. 版本说明

- **V1.0**：本文档；监控二级菜单「决策审计」占位；P0 起实现数据层与埋点。
