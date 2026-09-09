# 局部邻居扩窗 + Expansion Rerank（Parent-Child V3）

**需求名称：** 命中子块邻域扩窗与相关性过滤  
**版本：** V3  
**状态：** 已拍板，待开发  
**所属模块：** 知域 → 检索（`search_chunks` 组装阶段）  
**关联：** [`PRD.md`](../PRD.md) §3.2；前置 [`PRD_Chunk_V0.md`](PRD_Chunk_V0.md) / [`PRD_Chunk_V1.md`](PRD_Chunk_V1.md)

---

## 0. 已拍板决策摘要

| 主题 | 结论 |
| --- | --- |
| 目标 | 缓解 V1「整段 parent / 远距离 center-out」把同节无关子块（如中间的 B）塞进 context |
| 策略 | **方法 2**：局部 Neighbor Expansion（±1）→ Expansion Rerank（优先）→ 去掉低相关兄弟块 |
| 不做 | 同父下**全部**子块再 Rerank 后过滤（方法 1）；不恢复「整段 parent 全文」为默认 |
| 分组键 | 有 `parent_id` → 按 `parent_id`；无 parent → 按 `(document_id, heading)`（`heading` 空则不扩窗，仅单块） |
| 同组命中 | **不再**只留一个赢家；多锚点都保留 |
| 邻居重复 | 按 `chunk_id` **并集去重**后再拼 |
| 同组输出 | 合成 **1 条** `SearchHit`（正文=并集拼接；`chunk_id` / `score` 取同组锚点中 rerank 最高者） |
| 扩窗范围 | 每个锚点在同组兄弟中的 **±1** 邻居（按 `chunk_index`） |
| 过滤对象 | **仅邻居**；锚点已过全局 `RELEVANCE_MIN_SCORE`，默认保留 |
| Expansion 打分 | 优先 `rerank(query, neighbor)`；无 Rerank Key 时降级余弦 `similarity(query, neighbor)` |
| 门槛 | Rerank：复用 `RELEVANCE_MIN_SCORE`（默认 **0.5**）；余弦：`EXPAND_MIN_SIM`（默认 **0.3**，可调） |
| 预算 | 沿用 `SECTION_EXPAND_MAX_CHARS = 4000`；整块累加，禁止字符截断 |
| 挂载点 | **统一**替换 `_assemble_parent_context` 两条路径：有 parent 与无 parent（原 V0 `_expand_same_heading`）都走本套策略；废弃「无 parent 仍 center-out 整节」 |
| 审计埋点 | 决策审计 `retrieve` span **必须**能复盘组装：锚点/邻居候选/过线/丢弃/去重/预算裁切；复用现有 `DecisionRecorder`，不新开 node_type |
| `search_debug` | **不**做邻域组装（与 V0/V1 一致，保持 child 标注口径） |

---

## 1. 背景与问题

### 1.1 现网组装（V1）

```text
Recall → RRF → Rerank → RELEVANCE_MIN_SCORE
  → 同 parent_id 去重（只留最高分 child）
  → parent 全文 ≤ 4000？是 → content=parent 全文
  → 否 → 赢家周围 center-out 拼子块
```

### 1.2 典型噪声

父块【XX 项目总结】下子块：A 背景、B 风险、C 收益。检索只命中 A、C。

- V1 同父去重后取赢家，再塞 **整段 parent** → B 与其它无关子块一并进入 context。
- 多锚点「位置扩窗并集」若预算大、子块相邻，仍可能扩成 ABC，**不能**单靠位置解决「不要无关 B」。

### 1.3 目标取向

偏 **少噪声**：只补与 query 相关的局部邻居，不无脑拉整节。

---

## 2. 需求目标

1. 命中 child 后，仅尝试纳入同组 **±1** 邻居，且邻居须过相关性门槛。
2. 同组多个命中（A、C）均作为锚点参与扩窗，互不因分组键提前丢掉。
3. 无 `parent_id` 时与有 parent **同一套** ±1 + Expansion Filter（分组键改为同 `heading`），不再降级为 V0 center-out。
4. 邻居在多锚点间重复出现时，正文只保留一份。
5. 引用仍可追溯：合成 hit 的 `chunk_id` 为同组锚点中分数最高的 child；`original_content` 为该 child 原文。
6. Chat / Agent / 搜索等凡走 `search_chunks` 的路径统一受益；不改表、不改切块。
7. 监控 → 决策审计可复盘「为何带上/丢掉某邻居」，埋点故障不影响主回答。

---

## 3. 非目标（V3 不做）

- 不做方法 1：同父全量子块 Rerank + 阈值过滤（可作为后续增强，另开需求）。
- 不把默认组装改回「parent 全文」。
- 不改 `document_chunk` schema、不强制 reindex。
- 不做 overlap 文本去重、不做真实 tokenizer token 预算。
- 不把 Expansion 双重门槛写成「Rerank>0.5 **且** Similarity>0.3」。
- 不新增 `decision_span.node_type`（不用单独 `assemble` 节点）；不把 parent/邻居全文塞进 `evidence_refs`。
- `search_debug` 各阶段仍为 child 口径，不展示组装后 context。

---

## 4. 现状基线

实现：[`server/app/rag/search.py`](../../server/app/rag/search.py)

| 阶段 | 行为 |
| --- | --- |
| Recall | 向量 + BM25，仅 `role=child` |
| RRF | 融合后 top-k |
| Rerank | 改写 `hit.score` |
| Filter | `score >= RELEVANCE_MIN_SCORE`（默认 0.5；未重排时为余弦分） |
| Assemble | `_assemble_parent_context` → 有 parent 走 `_assemble_with_parent` |

相关常量：`SECTION_EXPAND_MAX_CHARS`、`RELEVANCE_MIN_SCORE`、向量弱相关 `SCORE_THRESHOLD`（0.30，**不是**本需求的 Expansion 门槛，仅作余弦降级默认参考）。

---

## 5. 功能需求

### 5.1 目标流水线（有 / 无 `parent_id` 统一）

```text
Recall
  → RRF
  → Rerank
  → RELEVANCE_MIN_SCORE
  → 按分组键分桶（parent_id 或 (doc, heading)）
  → Neighbor Expansion（每锚点同组 ±1）
  → Expansion Rerank / Similarity Filter（只筛邻居）
  → 按 chunk_id 并集去重
  → 按 chunk_index 升序拼接（≤ SECTION_EXPAND_MAX_CHARS）
  → 同组合成 1 条 SearchHit
  → context
```

### 5.2 算法（统一；仅分组键不同）

对门槛后的 `hits`：

1. **分流与分组**（组内**不去重丢掉锚点**）：
   - `parent_id is not None` → 键 = `parent_id`；兄弟 = 同 `parent_id` 且 `role=child`。
   - `parent_id is None` 且 `heading` 非空 → 键 = `(document_id, heading)`；兄弟 = 同 doc+heading 且 `role=child`。
   - `parent_id is None` 且 `heading` 空 → **不扩窗**：`original_content = content`，原样保留为一条 hit。
2. 批量加载各组兄弟，按 `chunk_index` 排序。
3. **锚点集** `anchors` = 本组命中的 child id 集合。
4. **邻居候选**：对每个锚点取同组内 `chunk_index` 相邻的左 1、右 1（若存在且非锚点）；全组合并后按 `chunk_id` 去重。
5. **Expansion 打分**（批量）：
   - 若 Rerank 可用：`score_documents(query, neighbor_contents)`；
   - 否则：用已有 embedding 算 query 与 neighbor 的余弦（或等价距离转相似度）。
6. **过滤**：邻居 `score >=` 对应门槛才纳入；锚点无条件纳入（已过全局门槛）。
7. **选型与预算**：将 `anchors ∪ kept_neighbors` 按 `chunk_index` 排序；须保证**所有锚点正文都在**，再按整块累加邻居；超 `SECTION_EXPAND_MAX_CHARS` 则不再加后续块；**禁止**对块内做字符截断。若单锚点自身已超预算，仍保留该锚点全文。
8. **写出一条** `SearchHit`：
   - `content` = `\n\n`.join(已选块)
   - 代表锚点 = 组内 `score` 最高的命中 hit
   - `chunk_id` / `score` / `document_*` / `heading` / `page` / `kind` / `parent_id` 取代表锚点
   - `original_content` = 代表锚点扩窗前原文
9. 各组结果与「heading 空、未扩窗」的 passthrough 合并，按 `score` 降序返回。

实现上建议抽公共函数（如 `_assemble_neighbor_context`），有/无 parent 只差「如何取兄弟列表」，避免两套逻辑分叉。

### 5.3 门槛与配置

| 配置 | 默认 | 含义 |
| --- | --- | --- |
| `RELEVANCE_MIN_SCORE` | 0.5 | 全局 Rerank 后过滤；Expansion Rerank **复用**此值 |
| `EXPAND_MIN_SIM` | 0.3 | 仅 Expansion **余弦降级**时使用（新建环境变量，可调） |
| `SECTION_EXPAND_MAX_CHARS` | 4000 | 单条组装字符预算 |
| 邻域半径 | 固定 ±1 | V3 不做可配置半径 |

说明：Rerank 分与余弦分**刻度不同**，不可混用同一数字比较；实现上分支选择一种分数再比门槛。

### 5.4 决策审计埋点（监控复盘）

现网已有：Chat / 知识 Agent 的 `retrieve` span 写入 `context_assembly` 计数与每条 `evidence_refs[].assembly`（见 `app/audit/evidence.py`）。V3 **必须扩展**该路径，使监控页能区分「锚点 vs 扩入邻居 vs 被过滤邻居」。

#### 5.4.1 原则

- **挂在现有 `retrieve` span**（`node_type=retrieve`），不新增 span 类型。
- 覆盖路径：Chat（`run_chat`）、知识 Agent（`node_retrieve_qi`）；其它凡写 retrieve + `search_chunks` 的入口一并跟上。
- Recorder 异常：**吞掉，不影响主回答**（与 Trace.md 一致）。
- `evidence_refs` 仍用 id + 短 excerpt（≤120）；**禁止**塞 parent 全文或整段组装正文。

#### 5.4.2 `assembly` 枚举（替换/扩展现网）

| 值 | 含义 |
| --- | --- |
| `child_only` | 未扩窗（heading 空，或无邻居过线） |
| `neighbor_expand` | V3：锚点 ∪ 过线 ±1 邻居（有/无 parent 统一） |
| `parent` / `heading_expand` | **仅兼容旧数据**；新组装不再写入 |

#### 5.4.3 `retrieve.decision` 增补

在现有 `context_assembly` 计数之外，增加 `neighbor_assembly`（或等价结构）摘要，例如：

```json
{
  "tool": "search_knowledge",
  "query": "...",
  "k": 5,
  "context_assembly": { "child_only": 1, "neighbor_expand": 2 },
  "neighbor_assembly": {
    "groups": 2,
    "anchors": 3,
    "neighbors_considered": 4,
    "neighbors_kept": 1,
    "neighbors_dropped": 3,
    "deduped_chunks": 1,
    "budget_skipped": 0,
    "score_mode": "rerank"
  }
}
```

| 字段 | 含义 |
| --- | --- |
| `groups` | 组装分组数（`parent_id` 或 `(doc, heading)`） |
| `anchors` | 锚点 child 数 |
| `neighbors_considered` | 进入 Expansion 打分的邻居数（去重后） |
| `neighbors_kept` / `neighbors_dropped` | 过线 / 未过线 |
| `deduped_chunks` | 因多锚点并集去掉的重复次数 |
| `budget_skipped` | 因字符预算整块未加入的块数 |
| `score_mode` | `rerank` \| `cosine` \| `none`（无邻居可打分时） |

实现可将组装函数返回 `(hits, stats)`，或把 stats 挂在模块级/调用方可读的轻量结构上；**不要**为审计再跑一遍扩窗。

#### 5.4.4 每条 `evidence_refs` 增补（组装后 hit）

在现有 `search_hit_evidence_ref` 字段上扩展（无则省略）：

| 字段 | 含义 |
| --- | --- |
| `assembly` | 见 §5.4.2 |
| `anchor_chunk_ids` | 本组锚点 id 列表 |
| `kept_chunk_ids` | 最终拼进 `content` 的 child id（含锚点） |
| `dropped_neighbor_ids` | 候选邻居中未过线的 id |
| `expand_scores` | 可选：`[{chunk_id, score}]`，仅邻居；便于核对门槛 |

`excerpt` 仍截断组装后 `content`；`original_excerpt` 仍代表锚点原文前 120 字。

#### 5.4.5 `metrics`

`elapsed_ms` / `hits` 保留；可选增加 `expand_elapsed_ms`（仅组装+邻居打分耗时），便于和召回耗时分开看。

#### 5.4.6 前端

监控 → 决策审计详情：展开 retrieve 节点即可看到上述 JSON；**本期不要求**单独做「组装可视化」UI。列表页无需改。

### 5.5 Agent Evidence Merge

有 `parent_id` 时 `merge_evidence` 仍可按 `parent_id` 去重（组装后同组本就一条时幂等）。无 parent 路径无 `parent_id`，merge 按 `chunk_id`；V3 **不要求**改 Agent merge 语义。merge span 的 `evidence_refs` 继续短 excerpt，不重复塞扩窗明细（明细以 retrieve span 为准）。

### 5.6 调用方

与 V0/V1 相同：只消费 `SearchHit.content` / `chunk_id` / `score` 即可。

| 调用方 | 路径 |
| --- | --- |
| Chat | `app/rag/chat.py` |
| Agent | `app/agent/tools.py` → `search_knowledge` |
| 搜索 API | `app/routers/search.py` |
| 相关文档 / 推荐 | `documents` / `recommendations` |

---

## 6. SearchHit 契约

| 字段 | V3 含义 |
| --- | --- |
| `chunk_id` | 同组锚点中 rerank 分最高的 child（引用跳转） |
| `score` | 代表锚点的全局 rerank 分（组装后不改） |
| `original_content` | 代表锚点原文 |
| `content` | 锚点 ∪ 过线邻居，去重后按序拼接 |
| `parent_id` | 有则保留；无 parent 路径为 `None` |
| 其余 | 与现网一致 |

不新增对外字段（调试若需「组装来源 chunk 列表」可另议，不阻塞 V3）。

---

## 7. 验收标准

1. 同组 A、B、C；只命中 A、C；B 与 A/C 均不相邻 → `content` **不含** B（有 parent 与无 parent+同 heading 各测一条）。
2. 同组只命中 A；左邻相关（Expansion≥门槛）、右邻无关 → `content` 含 A+左邻，不含右邻。
3. 同组命中 A、C 且某邻居同时是 A+1 与 C−1 → 该邻居在 `content` 中**只出现一次**。
4. 同组命中 A、C → 返回 **1 条** hit，不是 2 条重复节选；`chunk_id` 为 A/C 中分高者。
5. 有 Rerank Key 时邻居走 Rerank 门槛 0.5；无 Key 时走余弦与 `EXPAND_MIN_SIM`。
6. `search_debug` final 仍为未组装 child。
7. 无 `parent_id` 且 `heading` 空 → 不扩窗，`content` 为单 child。
8. 无 `parent_id` 有 heading：**不再**出现 V0 式「同节 center-out 无过滤」把远距离无关块拼进来。
9. Chat / 知识 Agent 一轮问答后，对应 `decision_run` 的 `retrieve` span 含 `neighbor_assembly` 计数；邻居被丢弃时可在 `dropped_neighbor_ids`（或汇总字段）中看到。
10. 人为让 Recorder 失败时，主回答仍成功（与现网审计约定一致）。

---

## 8. 测试要点

- 单元：邻域收集、锚点保留、邻居过滤、chunk_id 去重、同组合成一条、预算整块停、代表 `chunk_id`/`original_content`。
- 单元：有 `parent_id` 与无 parent（同 heading）两条分组路径行为一致（策略相同）。
- 单元：Rerank 可用 / 不可用两条打分降级路径；heading 空不扩窗。
- 单元：`search_hit_evidence_ref` / `context_assembly_summary`（或后继）对 `neighbor_expand` 与 `neighbor_assembly` 字段正确。
- 回归：`search_chunks` mock 下 Chat / Agent 不因组装变更崩溃；retrieve span 仍可写入。

---

## 9. 与 V0 / V1 / 方法 1 的边界

| | V0 | V1（现网） | V3（本需求） | 方法 1（未做） |
| --- | --- | --- | --- | --- |
| 关系键 | `(doc, heading)` | `parent_id`（无则降级 V0） | **`parent_id` 或 `(doc, heading)`，策略同一套** | `parent_id` |
| 同组多命中 | 去重留赢家 | 去重留赢家 | **多锚点保留** | 多命中后对全组子块打分 |
| 扩什么 | center-out 同节 | parent 全文或 center-out | **仅 ±1** | 同组全部 child |
| 相关性 | 无 | 无 | **邻居再打分过滤** | 全量子块过滤 |

---

## 10. 文档与实现落点

| 项 | 说明 |
| --- | --- |
| 实现 | `server/app/rag/search.py`（统一邻域组装）；`config.py` 增加 `EXPAND_MIN_SIM` |
| 审计 | `app/audit/evidence.py` 扩展 assembly / summary；Chat `run_chat`、知识 Agent `node_retrieve_qi` 的 retrieve span 写入 `neighbor_assembly` |
| Rerank | 复用 `app/rag/rerank.py` 的 `score_documents` |
| 技术说明 | 落地后更新 [`TECH.md`](../TECH.md) 检索段 + 审计一句 |
| 主 PRD | [`PRD.md`](../PRD.md) §3.2.3；审计约定见 [`Trace.md`](../Trace.md) |

---

## 11. 里程碑建议

1. 抽公共邻域组装；有 parent 与无 parent（同 heading）一并落地；单测覆盖 §7。
2. 扩展决策审计 retrieve 埋点（§5.4）；Chat + 知识 Agent 各验一条决策详情。
3. 用检索调试 / 标注集对比 V1/V0：长节多子块噪声是否下降、回答是否过度变残。
4. 若漏召回明显：再评估方法 1（同组全量 Rerank，且 child 数 ≤ N 才启用）作为 V4。
