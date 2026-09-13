## ReAct V1 设计决策

### 1. 架构边界

* `graph.py` 保留标准 ReAct 拓扑：`agent ⇄ tools`。
* 不改造成 `knowledge_flow` 固定 DAG。
* 不新增 `decompose` / `rewrite` / `sufficiency` LangGraph Node。
* ReAct 通过结构化 State + Tool 后处理反馈增强多轮检索能力。

### 2. State

* `knowledge_flow.py` 使用独立 `KnowledgeState`。
* `graph.py` 使用独立 `ReactState`。
* 不再继续扩大两者共用的 `AgentState`。
* 共享底层领域模型和服务：`SearchHit`、Evidence、Citation、RRF、Rerank 等。
* `ReactState` 新增/维护：

  * `query_type`
  * `sub_questions[]`
  * `evidence[]`
  * `knowledge_gaps[]`
  * `searched_queries[]`
  * `sufficiency`（最近一轮评估摘要，可选）
* `sub_questions[]` 项建议含：`id` / `question` / `aspects?` / `status` / `rewrite_count` / `evidence_ids` / `sufficiency?`
* 不引入 `current_qi_index`、`retrieve_phase`、`next_flow` 等 DAG 调度字段。
* 每轮用户请求（`initial_state`）重置本轮 `evidence` / `sub_questions` / `knowledge_gaps` / `searched_queries` / `sufficiency`；历史 messages 不作本轮 Evidence。

### 3. Decompose

* 采用 A：ReAct 图启动前执行一次轻量 State 初始化。
* 复用 `analyze_query` / `decompose_query`。
* simple：生成 1 个 Qi，使用原问题。
* complex：生成结构化 `sub_questions[]`，至少包含稳定 ID、question、status、rewrite_count、evidence_ids。
* 不在每轮 `node_agent` 中重复执行 Decompose。
* 不要求所有问题都强制生成多个 Qi。

### 4. Qi-aware Evidence

* Tool 执行后，将检索结果写入 Evidence Pool。
* Evidence 尽量关联 `qi_id`；无法可靠归属时允许 `unassigned/general`。
* 归属优先级：显式 `qi_id` > active Qi 启发（唯一未充分 Qi）> Query 与 Qi 可靠匹配 > 未归属。
* Evidence 用于中间检索状态与 Sufficiency；`citations` 继续负责最终答案引用。
* 复用现有 Evidence / Citation Merge，避免重复实现。

### 5. Sufficiency（规则预检 + LLM）

> 取代原「Sufficiency V0.5：每 Qi min_hits=2 即充分」方案。  
> `knowledge_flow` 仍使用 `sufficiency_v0 = len(hits)>0`，本决策**仅约束 ReAct**。

#### 5.1 定位

* Evidence Sufficiency：判断**当前轮证据是否足以支撑回答**，不承诺答案正确性。
* `len(hits)>0` 只能表示有召回，**不得**直接认定为充分。
* 流程放在 Tool 结果后处理中，**不**新增 Sufficiency Node：

  `ToolNode → Evidence 入池/归属 → 规则预检 →（有效时）LLM Sufficiency → 更新 ReactState → Observation 反馈 → Agent 自主决策`

#### 5.2 规则预检（门槛，不是充分）

只判断是否具备进入 LLM 评估的条件：

* hits / evidence 是否为空；
* content 是否为空；
* 去重后是否仍有有效证据；
* 必要基础字段是否完整（如 id、content）。

结果：

* `NO_VALID_EVIDENCE`：直接 insufficient，**不调用** Sufficiency LLM；
* `HAS_VALID_EVIDENCE`：进入 LLM Sufficiency。

实现入口：`sufficiency.precheck_evidence`。

#### 5.3 LLM Evidence Sufficiency

* 独立模块（如 `evidence_sufficiency.py`），逻辑不堆在 `graph.py` 节点内。
* 输入至少：用户问题、当前 Qi（若有）、aspects（若有）、本轮有效 Evidence、必要上下文。
* 优先 Pydantic Structured Output（`with_structured_output`），失败再 JSON + 模型校验。
* 结构化输出至少包含：

```json
{
  "sufficient": true,
  "covered_aspects": [],
  "missing_aspects": [],
  "gaps": [],
  "reason": ""
}
```

* 写回：`ReactState.sufficiency`、对应 Qi 的 `status` / `sufficiency`、`knowledge_gaps`。
* Observation 反馈简洁摘要（ToolMessage 内 `sufficiency` / `sufficiency_text`），辅助 Agent 决策，**不**强制 Workflow 跳转。

#### 5.4 Agent 决策（仍自主）

* `sufficient=true`：可整理证据作答；**不**因此绕过 tool / rewrite 预算。
* `sufficient=false` 且仍有预算：针对 `missing_aspects` / `gaps` 继续检索或改写 Query。
* `sufficient=false` 且预算耗尽：允许回答，但须保留并明确说明 `knowledge_gaps`，禁止伪装充分。

#### 5.5 与旧 V0.5 / knowledge_flow 的关系

| 路径 | 判定 | 说明 |
|---|---|---|
| knowledge_flow | `sufficiency_v0` | 仍 `len(hits)>0`，不改 |
| ReAct（本决策） | 预检 + LLM | 预检≠充分；充分性由 LLM 结构化给出 |
| 已废弃 | 纯规则「每 Qi ≥2 条即 SUFFICIENT」 | 不再作为 ReAct 充分性标准 |

### 6. Rewrite

* Rewrite 仍由 ReAct Agent 自主决定和生成，不新增 Node。
* Tool 后反馈对应 Qi 的 status、missing_aspects、knowledge_gaps。
* Agent 可根据反馈决定继续检索、改写 Query、切换工具或结束。
* 每 Qi rewrite 次数与全局 tool budget 双限。
* 不要求每个 Qi 固定执行 Rewrite。

### 7. 验收

针对：

> Kafka Rebalance 时为什么消费会停？怎么排查？

至少验证：

* 初始化阶段生成原因 / 机制 / 排查等至少 2 个 Qi；
* Evidence Pool 中证据可关联 Qi；
* 无有效证据时不调 Sufficiency LLM，并判定 insufficient；
* 有有效证据时 LLM 输出 structured `sufficient` / aspects / gaps / reason；
* 某 Qi 不足时有对应 `missing_aspects` / `gaps`，且 Agent Observation 可见；
* 补搜 Query 针对缺口，而非无依据重复同义搜索；
* 达到预算后仍能输出未覆盖缺口，不静默伪装为已充分；
* 同 conversation 新一轮请求不因历史消息跳过必要检索；
* 拓扑仍为 `agent ⇄ tools`，没有新增固定 Workflow Node；
* `knowledge_flow.py` 核心 sufficiency 规则不变。

### 8. 相对本决策的实现进度（续做参考）

| 能力 | 状态 | 说明 |
|---|---|---|
| State / 一次 Decompose | 已落地 | `ReactState` + `initial_state` 启动前 analyze/decompose |
| Qi-aware Evidence + 归属 | 已落地 | `react_evidence` + `node_tools` 后处理 |
| 规则预检 + LLM Sufficiency + Observation | 已落地 | `precheck_evidence` + `evidence_sufficiency` |
| Prompt / 历史隔离 / 预算尽暴露 gaps | 已落地 | `_system_prompt` + 每 run 重置 |
| 锚点场景端到端单测（Kafka 复合问） | **待补强** | 建议作为续做重点：mock analyze/decompose/tools/LLM，断言 Qi≥2、归属、gaps、补搜、预算尽缺口 |
| Rewrite 策略打磨 | **按需** | 计数与上限已有；Agent 是否稳定按 gaps 改写依赖 prompt/测例加固 |

续做「之前的 V1 需求」时：以本文 §1–7 为准；**不要**再按旧「min_hits=2 即充分」实现 Sufficiency。
