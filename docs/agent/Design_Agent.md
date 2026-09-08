# Agent 优化设计文档

> 范围：对话页 **「Agent」**（`task=knowledge` → `graph.py`）。  
> 不改 Multi Agent / Master；不改 `/api/chat`；不重做 RAG 内核。

---

## 1. 目标

将当前 Agent 从「同一 query 下最多搜几枪、证据平铺追加、靠 `max_loops` 硬停」升级为：

```text
User Query
    │
    ▼
Query Analysis（仍在 knowledge Agent 内）
    │
    ├── Simple ──► search_chunks ──► Merge ──► Answer
    │
    └── Complex
            │
      Decomposition → Q1..Qn（串行即可）
            │
      每个 Qi ──► search_chunks(Qi)   ← RRF/Rerank/V1 扩窗在 Tool 内
            │
      Evidence Pool
            │
      Evidence Sufficiency（按 Qi）
           /                \
       全部 enough      存在 insufficient
           │                    │
           │              Rewrite 该 Qi（禁止重搜已够的 Q）
           │                    │
           │              search_chunks(Qi')
           │                    │
           │              再 Sufficiency（该 Qi）
           │                    │
           └──────────┬─────────┘
                      ▼
               Evidence Merge
                      │
               Final Answer
                /          \
          Citations    Knowledge Gap（可并存）
```

核心原则：

> **Agent 负责决策与编排；`search_chunks` 负责完整检索链路（含 RRF / Rerank / Parent-Child 组装）。**

---

## 2. 职责边界

### Agent 负责

- Simple / Complex 判定（Agent 内短路，**不**改走 `/api/chat`）
- Complex 分解为子问题 Qi
- 按 Qi 调用检索 Tool
- Evidence Sufficiency（相关 ≠ 足够）
- 仅对不足 Qi 做 Query Rewrite + 再检索
- Evidence Merge（去重 / 关联 / 预算）
- Knowledge Gap + 最终回答与 Citation

### `search_chunks` 负责（保持现有，不在 Agent 重做）

```text
Vector + BM25 → RRF → Rerank → Context Expansion（V0/V1）→ hits
```

### 本阶段明确不纳入本设计改造

- `web_search` / `search_graph`：保留现网能力，**不进** Decomposition / Sufficiency 主流程
- Multi Agent（Master / plan / booking）
- Chunking 策略改造（Fixed / Recursive / Semantic）

---

## 3. 预算与 Loop 语义（必读）

此前 `MAX_LOOPS=3` 与「最多 5 个子问题」若都算 Tool 次数会打架。本设计约定：

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `MAX_SUB_QUESTIONS` | **上限 5** | Complex 硬截断；Decomposition **引导尽量 ≤3**，很复杂才到 4～5 |
| `MAX_INITIAL_RETRIEVES` | `= len(sub_questions)` | 每个 Qi **初始**各召回 1 次；**不计入** `MAX_LOOPS` |
| `MAX_LOOPS` | **3** | 仅统计 **补充检索**（Rewrite 后的 `search_chunks`）次数 |
| `MAX_REWRITE_PER_Q` | **2** | 单个 Qi 最多 Rewrite+重搜次数 |
| `MAX_EVIDENCE` | **10** | Merge 后进入生成的证据条数上限（替代含糊的「citation 砍尾 20」） |
| `search_chunks` `k` | **5**（可保持） | 单次 Tool 返回条数 |

停止条件：

```text
正常停：所有 Qi = SUFFICIENT（或 Simple 已答）
强制停：补充检索 loop_count >= MAX_LOOPS
        或某 Qi 的 rewrite_count >= MAX_REWRITE_PER_Q
仍不足 → 带 Knowledge Gap 作答（不得用模型常识硬补无证据部分）
```

Qi 越多初始检索越多（延迟/费用上升）；靠「引导 ≤3 + 硬上限 5」与 `MAX_LOOPS` 双约束。

---

## 4. Query Analysis（Simple / Complex）

- 实现：现有 Agent 图内一个节点（结构化 LLM 或轻量规则），**不**新建独立 Agent。
- Simple：单事实 / 单概念，不分解 → 一次 `search_chunks` → Merge → Answer。
- Complex：多实体对比、多知识点并列、多问句 → Decomposition。
- Decomposition 失败：降级为 Simple（原 query 检索一次）。

---

## 5. Query Decomposition

仅 Complex。示例：

```text
Kafka 和 RabbitMQ 在消息模型、消费模式、顺序保证上有什么区别？
→ Q1 消息模型  Q2 消费模式  Q3 顺序保证
```

要求：

- 与原问相关、可独立检索、少重复
- Prompt 引导 **尽量 ≤3**；输出超过 **5** 则截断
- 串行调用即可（并行是优化，非必须）
- 每个 Qi 维护：`status` / `rewrite_count` / `evidence_ids`

---

## 6. Evidence Sufficiency

> **Relevance ≠ Evidence Sufficiency。**  
> 不得仅用 `score > threshold` 当作「够不够答」的最终定义（V1 LLM 阶段尤其如此）。

分两期：

### V0（本需求第一期）— 纯规则

对该 Qi 的 `search_chunks` 返回值：

```text
len(hits) > 0  → SUFFICIENT
len(hits) == 0 → INSUFFICIENT
```

- 只看 **有没有 SearchHit**，不看 Rerank 分是否过线  
- 已知局限：有偏题 hit 也会判「够」；留给 V1  

### V1（后续）— LLM Sufficiency

- 对每个待判定 Qi：结构化输出 `SUFFICIENT | INSUFFICIENT` + 短理由  
- 输入：该 Qi + 关联 evidence 预览（建议最多 **6 条 × 约 500 字**，带 score）  
- **判定失败**（超时 / 解析失败等，≠ loop 用尽）：降级回 V0 规则（有 hit→够，无 hit→不够）  
- `loop` 用尽仍不够：走 Knowledge Gap，与「判定失败降级」无关  

不足时（V0/V1 共用后续动作）：

```text
只 Rewrite 不足的 Qi → search_chunks(Qi') → 再 Sufficiency(该 Qi)
禁止：重搜已 SUFFICIENT 的 Q；重复完全相同的 query
```

记录 `searched_queries`；完全相同则跳过 Tool。

---

## 7. Query Rewrite

- 仅针对 `INSUFFICIENT` 的 Qi
- 不改变用户意图；优先补全缺失实体 / 术语
- 受 `MAX_REWRITE_PER_Q` 与全局 `MAX_LOOPS`（补充检索）约束

---

## 8. Evidence Merge

**无论 enough / insufficient，作答前都要 Merge。**

```text
Evidence Pool
 → Dedup
 → 按 score 保留更优
 → 保留 related_questions
 → Context Budget（≤ MAX_EVIDENCE）
 → 供 Final Answer
```

去重键（兼容 V1）：

1. 有 `parent_id`：按 **`parent_id`** 去重（同父多 child 命中只留一条，保留最高分，合并 `related_questions`）
2. 否则：按 **`chunk_id`**（或 `document_id + chunk_id`）

Citation 仍指向命中 **child**（或现有 citation 字段约定）；生成可用组装后的 `content`。

---

## 9. Knowledge Gap

补充检索额度用尽后仍有 `INSUFFICIENT` Qi：

- 回答中区分：**有证据部分** vs **知识库缺口**
- 不得用模型外部常识补全缺口要点
- Citation 只能来自实际 Evidence
- Gap 与 Answer **可同屏并存**（部分答出 + 列出缺失 Qi）

---

## 10. State（精简）

```text
query
query_type                 # simple | complex
sub_questions[]            # id, question, status, rewrite_count, evidence_ids
evidence[]                 # id, document_id, chunk_id, parent_id?, score, content, related_questions
searched_queries[]
loop_count                 # 仅补充检索次数
max_loops
knowledge_gaps[]
final_answer
```

禁止把每轮完整 Tool 原始结果无限堆积；以 `evidence` + 关联 id 为准。

---

## 11. 决策审计（已有埋点，必须跟着改）

现网：

- 对话页 **Chat** → `decision_run.mode = chat`
- 对话页 **Agent**（`task=knowledge`）→ `decision_run.mode = knowledge`（列表文案「知识 Agent」）
- 监控 → 决策审计列表即这些 run；详情为有序 `decision_span`

当前 knowledge 路径大致埋：

```text
route（reason）→ retrieve（run_tool）→ … → generate
```

`node_type` 现用：`route` / `retrieve` / `generate`（表结构不变）。  
载荷用现有字段：`decision` / `rationale` / `evidence_refs` / `metrics`（JSONB）。

### 11.1 目标（可溯源）

> **每一个编排节点都必须留下可对照的输入与输出**，出问题时能从审计详情倒查是哪一步坏的。  
> **跟着能力代码一起埋，禁止后补。**

统一约定（写进每条 span）：

| 字段 | 用途 |
| --- | --- |
| `decision.step` | 步骤名：`analyze` / `decompose` / `retrieve_qi` / `sufficiency` / `rewrite` / `merge` / `gap` / `generate` |
| `decision.input` | **本节点输入**（结构化，见下表） |
| `decision.output` | **本节点输出**（结构化，见下表） |
| `rationale` | 一句话人话理由（可选但推荐） |
| `evidence_refs` | 本步关联的命中摘要（retrieve / sufficiency / merge 必填） |
| `metrics` | 计数、耗时、token 等 |

`evidence_refs` 单条至少含：`chunk_id`、`document_id`、`document_name`、`score`、`qi_id?`、`parent_id?`、`excerpt`（截断，如 120～200 字）。  
**不要求**把 parent 全文塞进审计（防爆库）；全文在 Evidence Pool / 生成侧，审计用 id + excerpt 溯源即可。

### 11.2 各节点必埋（是，都会埋）

| 步骤 | node_type | `input` 至少 | `output` 至少 | evidence_refs |
| --- | --- | --- | --- | --- |
| Query Analysis | `route` | 原 `query` | `query_type` | — |
| Decomposition | `route` | 原 `query` | `sub_questions[{id,question}]` | — |
| **Q1/Q2/… 检索**（每个 Qi 一条 span） | `retrieve` | `qi_id`, `query`（该次检索词） | `hit_count`, `hit_ids[]` | **本 Qi 全部 hit 摘要** |
| **Sufficiency V0**（每 Qi 一条，或一条含全部 Qi） | `route` | `qi_id`, `hit_count` | `status=SUFFICIENT\|INSUFFICIENT`, `rule=len(hits)>0` | 该 Qi 当前 evidence 摘要 |
| Rewrite | `route` | `qi_id`, `from_query`, 不足原因 | `to_query` | — |
| Rewrite 后检索 | `retrieve` | 同检索 | 同检索 | 新 hit 摘要 |
| **Evidence Pool → Merge** | `route` | Merge 前：`count`, `by_qi{qi→ids}` | Merge 后：`count`, `ids[]`, `dropped[]`, `related_questions` 变化 | **合并后**证据摘要 |
| Knowledge Gap | `route` | 仍 `INSUFFICIENT` 的 Qi 列表 | `gaps[]` | — |
| Final Answer | `generate` | 送入 LLM 的 evidence id 列表 | `answer` 摘要（如前 120 字） | 最终引用 ids |

你点名的这些**都会进审计**：

- 每个 Qi 的检索输出（是否有数据、命中哪些）
- Sufficiency 是否够、依据（V0：有无 hit）
- Evidence Pool → Merge 前后对比
- Gap / 最终生成

详情页应能串成：

```text
analyze → decompose
  → retrieve(Q1) → sufficiency(Q1)
  → retrieve(Q2) → sufficiency(Q2)
  → …
  → rewrite(Q3)? → retrieve(Q3')? → sufficiency(Q3')?
  → merge（含 pool 入/出）
  → gap?
  → generate
```

### 11.3 其它约束

1. **继续** `DecisionRecorder`；故障不得影响主回答。  
2. **不**另建审计表；列表继续按 `mode` 筛选。  
3. **Chat（`mode=chat`）埋点口径不变**。  
4. 验收：Complex 一次跑完，打开「知识 Agent」详情，**不看服务日志也能判断**卡在检索空、Sufficiency、Merge 还是生成。

---

## 12. 与现网参数的关系

| 现网 | 优化后 |
| --- | --- |
| `MAX_LOOPS=3` 含所有 tool | 改为 **仅补充检索**；初始按 Qi 各 1 次 |
| `MAX_SUBTASKS=3` 弱标签 | 改为真正的 Qi + 对齐检索 |
| `MAX_CITATIONS=20` 砍尾 | 改为 Merge 后 **`MAX_EVIDENCE=10`** + parent/chunk 去重 |
| reason 预览 8×200 | Sufficiency V1 预览建议 **6×500**；V0 规则阶段可不依赖长预览 |
| citation 平铺追加 | Evidence Pool + Merge |
| 审计 span：route/retrieve/generate | **保留三类 node_type**；用 `decision.step` + **`input`/`output`** 区分步骤并溯源 |

---

## 13. 不做

```text
❌ Multi-Agent / 新 Planner·Reviewer 角色
❌ HyDE
❌ Graph RAG 改造
❌ 无限 Loop
❌ Agent 内自建 RRF / Rerank / 第二套向量查询
❌ 重构 P0 `/api/chat`、`/api/chat/stream`
❌ 本需求强制上 Semantic Chunking
❌ 把 Simple 路由强行改成必须走 Chat API
❌ 另起一套审计存储；或因 Agent 优化破坏 chat 模式审计
❌ 审计后补；或只记 step 名不记 input/output/命中摘要
```

Chunking：本需求**不改**；仅重申 `Chunking ≠ Context Expansion`。后续切分策略另立需求。

---

## 14. 实施顺序

每步可独立验收：

```text
1. Evidence Sufficiency V0 + 审计 input/output/evidence_refs
2. Evidence Merge + Pool 入出对比 span
3. Query Decomposition + 按 Qi 检索（每 Qi 一条 retrieve span）
4. Query Rewrite + 再 Sufficiency + span
5. Knowledge Gap + span
6. Simple / Complex Routing + span
7. Trace 收口（详情页展示 input/output 可读性；指标汇总）
── 本需求第一期到此 ──
8.（后续 V1）LLM Sufficiency；span.output 增加理由；判定失败降级 V0
```

---

## 15. 验收

### 第一期（Sufficiency V0）

```text
① Simple → 不分解；search_chunks = 1；正常作答
② Complex → 引导 ≤3、硬上限 5；各 Qi 独立检索；统一回答
③ 某 Qi 无 hit → INSUFFICIENT → 只 Rewrite 该 Qi
④ 某 Qi 有 hit → SUFFICIENT → 不重搜该 Qi
⑤ 全部有 hit → 不因 loop_count < MAX_LOOPS 继续空转
⑥ 始终无 hit → 补充检索达 MAX_LOOPS → Answer + Knowledge Gap
⑦ 重复 query → 不二次调用 Tool
⑧ 同 parent / 同 chunk 多 Qi 命中 → Merge 后一条 + related_questions
⑨ /api/chat 不变；search_debug 仍以 child 召回为评估口径
⑩ 决策审计：每个 Qi 可见检索 input/output 与 hit 摘要；
   Sufficiency 可见是否够及 hit_count；Merge 可见去重前后；
   可定位到出错节点；chat 模式不受影响
```

### 后续 V1（LLM Sufficiency）另立验收：相关但答不全 → INSUFFICIENT；判定失败 → 降级 V0。

---

## 16. 已拍板

1. **`MAX_SUB_QUESTIONS`**：引导默认 **≤3**，硬上限 **5**。  
2. **Sufficiency**：**第一期 V0 = 纯规则（`len(hits)>0`）**；**后续 V1 = LLM 判定**，失败降级到 V0。  
3. **决策审计**：继续 `DecisionRecorder`；**每节点同步埋 input/output（及命中摘要）**；不改 chat 审计语义；禁止后补。
