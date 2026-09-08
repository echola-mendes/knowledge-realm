# 当前子需求：知识 Agent 编排优化（Sufficiency V0）

> 需求来源：`docs/Design_Agent.md`（只读）  
> 范围：对话页「Agent」（`task=knowledge` → `graph.py`）；不改 Multi Agent / Master、`/api/chat`、RAG 内核

## 1. 目标

将 knowledge Agent 从「同一 query 多枪平铺检索 + `max_loops` 硬停」升级为：Query Analysis →（Simple 单次检索 | Complex 分解 Qi 串行检索）→ Evidence Sufficiency（V0 规则）→ 仅对不足 Qi Rewrite 再检 → Evidence Merge → Final Answer（可并存 Knowledge Gap）；编排决策与审计 span 同步埋点（每节点 `input`/`output`）。

## 2. 背景

现网 `MAX_LOOPS` 与弱标签子任务混算 Tool 次数，证据靠平铺追加、缺「相关≠足够」判定与缺口表达。检索质量（RRF/Rerank/Parent-Child）已在 `search_chunks` 内；本需求只改 Agent 决策与编排，不在 Agent 内重做检索链路。

## 3. 功能范围

- Query Analysis：Agent 图内 Simple / Complex 判定；Simple 不分解、一次 `search_chunks`；Decomposition 失败降级 Simple
- Decomposition：Complex 拆 Qi（引导尽量 ≤3，硬截断 5）；每 Qi 维护 `status` / `rewrite_count` / `evidence_ids`；串行检索
- Evidence Sufficiency **V0**：`len(hits)>0` → SUFFICIENT，否则 INSUFFICIENT；不得用 score 阈值作最终定义
- Query Rewrite：仅 INSUFFICIENT Qi；受 `MAX_REWRITE_PER_Q=2` 与全局补充检索 `MAX_LOOPS=3` 约束；完全相同 query 跳过 Tool（`searched_queries`）
- Evidence Merge：作答前必做；去重键优先 `parent_id` 否则 `chunk_id`；预算 `MAX_EVIDENCE=10`；保留 `related_questions`
- Knowledge Gap：补充额度用尽仍不足 → 有证据部分作答 + 列出缺口 Qi；禁止用模型常识补缺口；Citation 仅来自 Evidence
- State：精简为 design §10 字段；禁止无限堆积完整 Tool 原始结果
- 决策审计：继续 `DecisionRecorder`；保留 `route`/`retrieve`/`generate`；用 `decision.step` + `input`/`output` + 必要 `evidence_refs`；能力与埋点同步；详情页可读串链；chat 模式口径不变
- 预算语义：`MAX_INITIAL_RETRIEVES = len(sub_questions)` 不计入 `MAX_LOOPS`；`MAX_LOOPS` 仅计 Rewrite 后补充检索

## 4. 非目标

- Multi-Agent / 新 Planner·Reviewer；HyDE；Graph RAG 改造
- Agent 内自建 RRF / Rerank / 第二套向量查询
- 重构 `/api/chat`、`/api/chat/stream`；Simple 不强行改走 Chat API
- 本需求强制 Semantic Chunking / 切块策略改造
- `web_search` / `search_graph` 纳入 Decomposition / Sufficiency 主流程（现网能力可保留，不进主流程）
- LLM Sufficiency（V1，另立）；无限 Loop；另起审计表或后补埋点
- 破坏 chat 模式审计语义

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 职责 | Agent 决策编排；`search_chunks` 负责完整检索（含 RRF/Rerank/V0·V1 扩窗） |
| Simple | 单事实/单概念 → 1 次检索 → Merge → Answer |
| Complex | 多实体/多知识点/多问句 → Decomposition → 每 Qi 初始各检索 1 次 |
| Sufficiency V0 | 只看有无 SearchHit；有偏题 hit 也判够（已知局限，留给 V1） |
| 补充检索 | 只 Rewrite 不足 Qi；禁止重搜已 SUFFICIENT；相同 query 不二次 Tool |
| 停止 | 全部 SUFFICIENT；或 `loop_count >= MAX_LOOPS`；或某 Qi `rewrite_count >= MAX_REWRITE_PER_Q` → 带 Gap 作答 |
| Merge | enough/insufficient 作答前都 Merge；同父多命中留最高分并合并 related_questions |
| Gap | 与 Answer 可同屏；无证据要点不得常识硬补 |
| 审计 | 每编排节点同步 span；故障不影响主回答；`evidence_refs` 用 id+excerpt（不塞 parent 全文） |

## 6. 输入与输出

- 输入：用户 query（knowledge Agent 对话路径，现有 API/前端入口）
- 输出：最终回答 + Citations（来自 Evidence）+ 可选 Knowledge Gap；审计详情可串：analyze → decompose → retrieve(Qi) → sufficiency → rewrite? → merge → gap? → generate

## 7. 涉及模块

- 改：`server/app/agent/graph.py`（及同包 state / 节点逻辑）
- 改：`server/app/audit/`（span 载荷约定：`decision.step` / `input` / `output` / `evidence_refs`）
- 改：决策审计详情前端（`DecisionAuditView` 等）— Trace 收口可读性
- 测：编排规则（Simple/Complex、Sufficiency V0、Rewrite 约束、Merge 去重、Gap、重复 query 跳过）+ 审计 span 契约
- 不动：`/api/chat`、RAG `search_chunks` 内核、Multi Agent、chunking、chat 审计语义
- 文档：Phase 4 同步 `docs/TECH.md`、`docs/PRD.md`（若存在对应章节）

## 8. 验收标准

| ID | 标准 |
| --- | --- |
| AC-01 | Simple → 不分解；`search_chunks` = 1；正常作答 |
| AC-02 | Complex → 引导 ≤3、硬上限 5；各 Qi 独立检索；统一回答 |
| AC-03 | 某 Qi 无 hit → INSUFFICIENT → 只 Rewrite 该 Qi |
| AC-04 | 某 Qi 有 hit → SUFFICIENT → 不重搜该 Qi |
| AC-05 | 全部有 hit → 不因 `loop_count < MAX_LOOPS` 空转 |
| AC-06 | 始终无 hit → 补充检索达 `MAX_LOOPS` → Answer + Knowledge Gap |
| AC-07 | 重复 query → 不二次调用 Tool |
| AC-08 | 同 parent / 同 chunk 多 Qi 命中 → Merge 后一条 + `related_questions` |
| AC-09 | `/api/chat` 不变；`search_debug` 仍以 child 召回为评估口径 |
| AC-10 | 决策审计：每 Qi 检索 input/output + hit 摘要；Sufficiency 可见是否够及 hit_count；Merge 可见去重前后；可定位出错节点；chat 模式不受影响 |

## 9. 待确认问题

无（需求文档 §16 已拍板）：

1. `MAX_SUB_QUESTIONS`：引导 ≤3，硬上限 5  
2. Sufficiency 第一期 = V0 规则 `len(hits)>0`；LLM Sufficiency 另立  
3. 审计每节点同步埋 input/output（及命中摘要）；不改 chat 审计语义  

实施顺序按 design §14 的 1→7 作为本子需求范围（不含 §14.8 LLM Sufficiency）。
