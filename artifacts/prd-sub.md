# 当前子需求：ReAct 改写软约束 + SSE/审计 enrich

> 需求来源：用户确认方案（改写 A + SSE/审计 A）  
> 前置：Evidence Sufficiency、锚点验收与缺口补搜单测已落地  
> Master knowledge 共用 graph.py 的 prompt/Observation 自动生效；**仍不接**决策审计

## 1. 目标

在保留 `agent ⇄ tools` 拓扑与 Agent 自主决策的前提下，用软约束提升缺口驱动改写质量，并把 sufficiency 短摘要 enrich 进既有 SSE `tool_result.reason` 与审计 `tool_result.decision`，形成可观测闭环。

## 2. 背景

- Sufficiency / Observation / 锚点补搜断言已有；改写仍主要靠 prompt，Observation 未系统暴露 rewrite 额度与 `searched_queries`。
- `node_tools` 当前在 `process_react_tool_round` **之前**写 SSE/审计，无法带上 sufficiency。
- SSE `reason` 仅命中条数；审计 `decision` 无 `sufficient`/`qi_id`/`missing` 等字段。

## 3. 功能范围

1. **改写软约束（必做）**
   - 强化 `_system_prompt`：不足时围绕 missing/gaps 改写；禁止精确重复 `searched_queries`；勿泛化重搜原问；rewrite 达上限后不再鼓励补搜，保留 gaps。
   - Observation 暴露：`qi_id`、`sufficient`、aspects、`gaps`、`searched_queries`、rewrite 次数/剩余额度；超限 instruction 引导保留 gaps 作答。
   - Agent 仍自主；不硬拦 Tool、不调 `rewrite_query`、不新增 Node。
2. **SSE enrich（必做）**：post-process 后写 `tool_result.reason`（命中 + 短 sufficiency，≤40）；事件类型不变。
3. **审计 enrich（必做）**：`tool_result` span `decision` 增补 `sufficient`/`qi_id`/`missing`/`covered`/短 `gaps`；不写 `decision.step=sufficiency|rewrite`；Master knowledge 仍无 recorder。
4. **文档**：Trace 记 react decision 字段；architecture 一句长期约束；前端不做专项 UI。

## 4. 非目标

- 硬性重复 Query 拦截；超限强制跳过 Tool；`rewrite_query()` 自动改写
- 独立 Sufficiency SSE 事件 / span；新 Workflow Node；新 `node_type`
- Master knowledge 接审计；ChatView / DecisionAudit UI 专项重构
- 改 `knowledge_flow.py` 功能性逻辑

## 5. 业务规则

- 充分性仍 = 预检 + LLM；本轮不重做 Sufficiency 主链路。
- 软约束不保证强制阻止模型重复调用；单测以 Observation/prompt 文本与 mock 注入行为为主。
- SSE `reason` 非 CoT、非独立事件；审计故障不得影响主回答（既有 Recorder 契约）。

## 6. 输入与输出

- 输入：既有 `task=react` 图 + mock 单测
- 输出：增强后的 Observation/prompt、enrich 后的 SSE/审计字段、通过的单测与文档同步

## 7. 涉及模块

- `server/app/agent/graph.py`、`react_evidence.py`、`evidence_sufficiency.py`
- `server/tests/test_react_*.py`（sse / a1_audit / evidence / v1_anchor 等）
- `docs/Trace.md`、`artifacts/architecture.md`（长期一句）；Phase 4 再同步 PRD/TECH/memory

## 8. 验收标准

1. Observation 含 rewrite 次数/剩余额度；超限路径不再鼓励无限补搜且 gaps 保留
2. Prompt 含缺口改写 / 禁精确重复 searched / 上限后停补搜指引
3. SSE 事件类型不变；`tool_result.reason` 含短 sufficiency 且 ≤40
4. `tool_result` span decision 可见 `sufficient`/`qi_id`/`missing` 等；无新 node_type
5. Master knowledge 路径仍无 `decision_recorder`
6. 相关回归子集通过；无 `knowledge_flow.py` 功能性改动

## 9. 待确认问题

（无 — 改写 A + SSE/审计 A + Master 不接审计已确认）
