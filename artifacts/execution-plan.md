# Execution Plan

> 子需求：知识 Agent 编排优化（Sufficiency V0）  
> 栈约束：LangGraph 仅 knowledge/Master；检索只经现有 Tool → `search_chunks`；审计继续 `DecisionRecorder`

## Step 1：Evidence Sufficiency V0 + 审计载荷约定

### 目标
落地 V0 充足性纯规则，并固定 knowledge span 的 `decision.step` / `input` / `output` / `evidence_refs` 写法（可单测，不依赖完整新图）。

### 方案
- 在 `server/app/agent/`（或紧邻小模块）实现 `sufficiency_v0(hits) → SUFFICIENT|INSUFFICIENT`：`len(hits)>0` 即够。
- 扩展/复用 `app/audit/evidence.py`：`evidence_refs` 单条含 `chunk_id`/`document_id`/`document_name`/`score`/`qi_id?`/`parent_id?`/`excerpt`（沿用现有 `search_hit_evidence_ref`，按需加 `qi_id`）。
- 约定 `add_span` 的 `decision` 形状：`{step, input, output}`；`sufficiency` 的 `output` 含 `status` + `rule=len(hits)>0`。
- 不改 `/api/chat`；本 Step 可不改图拓扑，或仅在现有 retrieve 后加可选 sufficiency span 试点——优先纯函数 + 单测，图内全面接线放到后续 Step。

### 验收
- [✅] 单测：空 hits → INSUFFICIENT；非空 → SUFFICIENT（与 score 无关）
- [✅] 单测：`decision` 含 `step`/`input`/`output`；`evidence_refs` 含 excerpt 与 id 字段

---

## Step 2：Evidence Pool Merge + 入出对比 span

### 目标
作答前统一 Merge：去重、预算、`related_questions`；审计可见 Merge 前后。

### 方案
- 实现 `merge_evidence(pool) → merged`：去重键优先 `parent_id`，否则 `chunk_id`；同键留最高分并合并 `related_questions`；截断至 `MAX_EVIDENCE=10`。
- State 侧引入 `evidence[]`（及 id 关联），替代无限平铺 `citations` 作为生成输入源（对外 citation 仍可由 merged evidence 映射）。
- Merge 节点/`route` span：`step=merge`；`input` 含 count、`by_qi`；`output` 含 count、`ids`、`dropped`；`evidence_refs` 为合并后摘要。

### 验收
- [✅] 单测：同 `parent_id` / 同 `chunk_id` 多条 → 一条 + `related_questions` 合并（AC-08）
- [✅] 单测：超过 10 条按 score 保留 Top-N
- [✅] 单测：merge span 的 input/output 含前后 count 与 dropped

---

## Step 3：Query Decomposition + 按 Qi 初始检索

### 目标
Complex 路径：分解 Qi（引导 ≤3、硬截断 5），每 Qi 初始各 `search_chunks` 1 次（不计入 `MAX_LOOPS`）；每 Qi 一条 retrieve span + sufficiency span。

### 方案
- 扩展 `AgentState`：`query_type`、`sub_questions[]`、`evidence[]`、`searched_queries[]`、`knowledge_gaps[]` 等（对齐 design §10）；`loop_count` 语义改为仅补充检索（本 Step 先置 0，Rewrite 在 Step 4）。
- 图节点：`decompose`（LLM 结构化输出 Qi）→ 串行 `retrieve_qi`（调用现有 `search_knowledge`/`search_chunks` Tool）→ `sufficiency`（V0）。
- Decomposition 失败：降级为单 Qi=原 query（与 Simple 等价行为可在本 Step 暂用）。
- 审计：`step=decompose`（route）；每 Qi `step=retrieve_qi`（retrieve）+ `step=sufficiency`（route）。
- `web_search`/`search_graph` 不进本主流程；现网 allow_web 等旁路若保留须在计划外最小兼容，禁止塞进 Decomposition。

### 验收
- [✅] 单测或图测：>5 个子问题被截断为 5
- [✅] 图/契约测：N 个 Qi → N 次初始检索；`loop_count` 仍为 0（AC-02 核心）
- [✅] 审计：每 Qi 可见 retrieve 的 input/output 与 hit 摘要 + sufficiency 的 status/hit_count

---

## Step 4：Query Rewrite + 再 Sufficiency + 补充检索预算

### 目标
仅对 INSUFFICIENT Qi Rewrite 再检；全局 `MAX_LOOPS=3`、每 Qi `MAX_REWRITE_PER_Q=2`；相同 query 跳过 Tool。

### 方案
- 节点：`rewrite` → `retrieve_qi` → `sufficiency`；仅不足 Qi；禁止重搜已 SUFFICIENT。
- `searched_queries` 去重：完全相同则跳过 Tool 并记 span/rationale。
- 停止：全部够 / `loop_count >= MAX_LOOPS` / 该 Qi `rewrite_count` 达上限 → 进入 Merge（Gap 在 Step 5）。
- 全部有 hit 时不得因 loop 额度未用尽而空转（AC-05）。

### 验收
- [✅] 测：无 hit Qi 才 Rewrite；有 hit 不重搜（AC-03/04）
- [✅] 测：重复 query 不二次调用 Tool（AC-07）
- [✅] 测：全部 SUFFICIENT 后不再补充检索（AC-05）
- [✅] 审计：rewrite + 再 retrieve/sufficiency 的 input/output 齐全

---

## Step 5：Knowledge Gap + Final Answer

### 目标
额度用尽仍不足时：有证据部分作答 + 列出缺口；Citation 仅来自 Evidence；禁止常识硬补缺口。

### 方案
- `gap` 节点：收集仍 INSUFFICIENT 的 Qi → `knowledge_gaps`；span `step=gap`。
- `generate`：输入仅 Merge 后 evidence；prompt 明确区分可引用内容与缺口；`MAX_CITATIONS` 平铺砍尾改为基于 `MAX_EVIDENCE`。
- generate span：`input`=evidence ids；`output`=answer 摘要；`evidence_refs`=最终引用。

### 验收
- [✅] 测：始终无 hit 且达 `MAX_LOOPS` → 回答含 Knowledge Gap（AC-06）
- [✅] 测：有部分证据时 Gap 与 Answer 可并存；citation 不含无 evidence 项
- [✅] 审计：gap / generate span 可对照

---

## Step 6：Simple / Complex Query Analysis

### 目标
入口 Analysis：Simple 不分解、仅 1 次检索；Complex 走 Decomposition；失败降级 Simple。

### 方案
- 图入口节点 `analyze`（结构化 LLM 或轻量规则）：`query_type=simple|complex`；span `step=analyze`。
- Simple：等价单 Qi 或短路「一次 retrieve → sufficiency → merge → generate」（无 decompose）。
- Complex：进入 Step 3–5 路径。
- 替换现网 `reason → run_tool` 主循环为上述 DAG/条件边；清理 `MAX_SUBTASKS`/`MAX_CITATIONS` 旧语义依赖（调用方兼容保留必要字段）。

### 验收
- [✅] 测：Simple → 不分解；`search_chunks`（或 search_knowledge）调用次数 = 1（AC-01）
- [✅] 测：Complex → 走 decompose；Decomposition 解析失败 → 降级单次检索
- [✅] 测：现有 knowledge Agent 入口（`initial_state` / Master 调用）仍可跑通

---

## Step 7：Trace 收口（详情页 + 契约）

### 目标
审计详情不看服务日志即可定位卡在检索空 / Sufficiency / Merge / 生成；chat 模式不受影响。

### 方案
- `DecisionAuditView.vue`：展示 `decision.step`，并结构化或分区展示 `input`/`output`（在现有 `pretty(decision)` 上增强可读性即可，遵循 `docs/style.md`）。
- 契约/集成测：Complex 跑完后 spans 顺序可串成 analyze→decompose→retrieve→sufficiency→…→merge→gap?→generate（AC-10）。
- 回归：chat 路径审计口径不变；确认未改 `/api/chat`（AC-09）。

### 验收
- [✅] 前端详情可见 step，并能读到 retrieve/sufficiency/merge 的关键 input/output（路径或组件抽检）
- [✅] 测：knowledge 一次 Complex 的 span 链可定位节点；chat 相关测仍通过（AC-09/10）
- [✅] `docs/TECH.md` / `docs/PRD.md` 本 Step 不强制改（Phase 4 统一同步）