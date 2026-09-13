# Execution Plan

> 子需求：ReAct 改写软约束 + SSE/审计 enrich  
> 栈约束：见 `AGENTS.md`；拓扑仅 `agent ⇄ tools`；不改 `knowledge_flow.py` 功能性逻辑  
> 已确认：改写软约束 A；SSE/审计只 enrich 既有字段；Master knowledge 不接审计  
> 全局硬约束：不硬拦 Tool；不调 `rewrite_query`；禁止新增 Node / 事件类型 / node_type

---

## Step 1：Observation + Prompt 软约束

### 目标
向 Agent 暴露改写额度与已搜 query，并用 prompt 引导缺口驱动改写。

### 方案
- `evidence_sufficiency.format_sufficiency_observation` / `react_evidence._patch_tool_message`：写入 searched_queries、rewrite_count、rewrite_remaining；超限 instruction 改为保留 gaps。
- `graph._system_prompt`：强化缺口改写、禁精确重复 searched_queries、勿泛化重搜、达上限停鼓励补搜。
- 单测扩 `test_react_evidence`（或薄锚点测）：Observation 含额度；超限语义可见。

### 验收
- [✅] Observation 含 rewrite 次数与剩余额度
- [✅] 超限路径 instruction/gaps 含预算尽语义
- [✅] `_system_prompt` 含缺口改写与禁精确重复指引

---

## Step 2：SSE `tool_result.reason` enrich

### 目标
在 sufficiency 后推送带短摘要的 `tool_result.reason`（≤40）。

### 方案
- `node_tools`：先 `process_react_tool_round`，再写 SSE。
- `_safe_tool_result_reason`：命中数 + 充分/不足/缺什么短句，硬截断 40。
- 扩 `test_react_sse.py`。

### 验收
- [✅] 无独立 `reason`/`sufficiency` 事件类型
- [✅] `tool_result.reason` 含 sufficiency 语义且 `len<=40`

---

## Step 3：审计 `tool_result.decision` enrich + Trace

### 目标
span decision 可复盘 sufficiency；Master 仍不接审计。

### 方案
- post-process 后 `add_span("tool_result", decision={tool, …, sufficient, qi_id, missing, covered, gaps短})`；禁止 `decision.step=sufficiency|rewrite`。
- `docs/Trace.md` + `artifacts/architecture.md` 一句；扩 `test_react_a1_audit`；保留 Master 无 recorder 测。

### 验收
- [✅] react `tool_result` span decision 含 sufficient / qi_id / missing
- [✅] node_type 无新增；Master knowledge 仍无 decision_recorder
- [✅] Trace/architecture 已记 enrich 口径

---

## Step 4：改写软约束行为单测 + 回归

### 目标
钉死软约束可观测行为并回归相关子集。

### 方案
- 扩锚点/证据测：补搜非精确重复且对准 gaps；Observation 额度；超限保留 gaps。
- 跑：`test_react_sse`、`test_react_a1_audit`、`test_react_evidence`、`test_react_v1_anchor`、`test_react_tool_budget`（可缩）。

### 验收
- [✅] 软约束相关单测通过
- [✅] 上述回归子集通过
- [✅] 无 `knowledge_flow.py` 功能性 diff（本轮未改 KF）
