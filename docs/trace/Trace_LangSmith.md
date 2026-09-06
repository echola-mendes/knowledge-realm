# 知域 — 链路追踪下一版：接入 LangSmith（基础 Trace）

**版本：** V1.2（规划）  
**状态：** 未排期；接在 [`Trace.md`](Trace.md) / 决策审计极简版（V1.1）之后  
**前置：** V1.1 决策落库（`DecisionRecorder`）已可用  

---

## 1. 定位

两层分工，避免做成「第二个迷你 LangSmith」：

```text
                    知域 Agent 一轮回答
                           │
                ┌──────────┴──────────┐
                ↓                     ↓
       DecisionRecorder            LangSmith
                │                     │
                ↓                     ↓
          PostgreSQL               Trace（云或自托管）
                │                     │
                ↓                     ↓
         监控 → 决策审计           开发调试 UI
         业务决策 / 证据           LLM·Tool·节点·Token·延迟
```

| 层 | 回答的问题 | 存哪 |
| --- | --- | --- |
| **Decision（V1.1，保留）** | 业务上做了什么决策？绑哪条 message？用了哪些 chunk？ | 本机 Postgres |
| **LangSmith（本版）** | 系统实际执行了什么？哪步慢/报错？Token 多少？ | LangSmith |

**重合点（只认一边）：** 节点顺序、耗时、token、tool 名、LLM 原始 IO → **以 LangSmith 为准**，Decision 不再做完整技术台账。  
**不重合（必须自留）：** `message_id` 绑定、route 选型理由、`evidence_refs` / citation、监控页业务复盘。

---

## 2. 目标 / 非目标

### 2.1 目标

- 生产 Agent / Chat 路径开启 **基础 Trace**（LangChain/LangGraph 自动或轻量回调）
- 环境变量开关；**默认关**（本机开发按需开）
- `DecisionRun` 可选存 `langsmith_trace_id`（或 URL），详情页可「打开 Trace」外链
- 技术指标（token、latency、错误栈）以 LangSmith 为准，弱化自建 `/api/agent/trace` 的长期必要性

### 2.2 非目标

- 不在知域产品内嵌 LangSmith 全量 UI（不做第二套 Trace 页）
- 不自建完整 Span / LLM 调用台账 / Token 看板替代 LangSmith
- 不把 Decision 表扩成技术 Trace 仓库
- 本期不强制自托管；若用云端须满足 §4 隐私约束
- 不做 Explain / Judge（仍延期）

---

## 3. 与 V1.1 的衔接

V1.1 已约定：

- Decision 落库；`metrics` 仅**可选**写一点点耗时/token  
- 不引入 LangSmith  

V1.2 落地后调整：

| 能力 | V1.1 | V1.2 |
| --- | --- | --- |
| 业务决策 + 证据 + message | Decision 表 | **不变** |
| Token / 延迟 / LLM IO | span.metrics 轻量可选 | **LangSmith** |
| 调试旁路 `/api/agent/trace` | 保留 | 可逐步弱化；优先用 LangSmith |
| 监控页 | 决策链详情 | 详情 + 可选「查看 LangSmith Trace」链接 |

实现约束：**禁止双写全量 prompt/检索正文**到 Decision 与 LangSmith；敏感正文策略见 §4。

---

## 4. 隐私与开关

知域定位：个人本机知识库，AI 只发任务所需最少数据。

- `LANGSMITH_TRACING`（或等价）默认 `false`
- 仅调试 / 明确需要时开启；面试 demo 可临时开
- 检索 chunk 正文、用户长文：优先脱敏、截断，或不上传 inputs（按 LangSmith 客户端能力配置）
- Key 只放本机 `.env`，不进 git、不进产品 UI 配置页（除非以后单独做「开发者选项」）

自托管 LangSmith：允许作为**可选运维选择**，但不改 `AGENTS.md` 主栈（应用本身仍无 Docker）；文档注明依赖与成本，不作为默认交付。

---

## 5. 数据与 API（增量）

### 5.1 `decision_run` 增量字段

| 字段 | 说明 |
| --- | --- |
| `langsmith_run_id` | 可空；对应本次 Trace / root run id |
| `langsmith_url` | 可空；可拼链接，避免前端写死域名逻辑 |

无 LangSmith 时两字段为空，V1.1 行为不变。

### 5.2 API

- 现有 `GET /api/decisions/{run_id}` 响应带上上述字段即可  
- **不新增**「代理转发 LangSmith 内容」的 API（避免把云端数据再镜像一份）

### 5.3 前端

- 决策详情：若有 `langsmith_url`，显示外链按钮「技术 Trace」  
- 不做站内嵌入 iframe（除非后续明确需要）

---

## 6. 接入方式（示意）

- 使用官方 LangSmith / LangChain  tracing 环境变量与回调  
- 与现有 DashScope 兼容客户端并存；不改为必须 OpenAI 账号  
- 在 `agent_stream` / `chat_stream` 创建 `DecisionRun` 时，若 tracing 开启，把 root run id 写回 run 行  

伪代码方向：

```python
# 开关关：只 DecisionRecorder
# 开关开：LangChain 自动 Trace + recorder 写 langsmith_run_id
```

---

## 7. 验收

1. 开关关：行为与 V1.1 一致，无外发 Trace  
2. 开关开：LangSmith 能看到该次 Agent/Chat 的基础节点 / LLM / Tool Trace  
3. 对应 `decision_run` 能关联到 trace id（或可打开 URL）  
4. Decision 详情仍能独立展示 route / evidence，不依赖 LangSmith 在线  

---

## 8. 实施顺序建议

1. 先完成并验收 [`Trace.md`](Trace.md) V1.1  
2. 再开本版：环境变量 + 写回 `langsmith_run_id` + 详情外链  
3. 最后视情况收缩调试页旁路 Trace 的维护成本  

---

## 9. 版本关系

| 版本 | 文档 | 内容 |
| --- | --- | --- |
| V1.1 | [`Trace.md`](Trace.md)（极简决策审计） | 业务决策落库 + 监控页 |
| **V1.2** | **本文** | 接入 LangSmith 基础 Trace；Decision 保留 |
| 更后 | — | Master 全路径、对话内入口、Explain 等 |

---

## 10. 一句话

**LangSmith 做底层 Agent Observability；知域 Decision 做上层业务审计。** 技术 Trace 交给 LangSmith 后，不要在 Postgres 里再造一套。
