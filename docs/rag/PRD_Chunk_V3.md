# 局部邻居扩窗 + 双条件过滤（V3）

**状态：** 已落地（同组合并修订）  
**改：** `search_chunks` 组装（`search.py`）  
**关联：** [`PRD.md`](../PRD.md) §3.2；前置 V0/V1

---

## 0. 拍板

| 项 | 结论 |
| --- | --- |
| 替换 | 去掉同父去重→parent 全文 / V0 center-out |
| 策略 | 同组命中先合并：seeds ∪ ±1 去重 → 双条件（仅非 seed）→ 按 `chunk_index` 拼 **1** 条 context |
| 同父多命中 | 同 `parent_id`（或无 parent 时同 `(doc, heading)`）**合成 1 条 hit** |
| 兄弟键 | 有 `parent_id`→同父；无→`(doc, heading)`；无 parent 且 heading 空不扩 |
| 双条件 | 见 §1；**seed 锚点**不参与过滤（已过全局 0.5）；邻居相对**最近 seed**算锚点相似 |
| 预算 | `SECTION_EXPAND_MAX_CHARS=4000`，整块、不截断；seeds 优先纳入 |
| 字段 | `neighbor_chunk_ids`（组级 ±1 非 seed 候选）、`expanded_chunk_ids`（双条件过线，⊆ neighbor） |
| 代表锚点 | `chunk_id` / `score` / `original_content` = 组内 **score 最高** 的 seed |
| debug | `search_debug` 不组装 |
| 审计 | `retrieve` span 映射两字段 + dropped + 可选双分 |

---

## 1. 邻居进 content 条件（核心）

```text
n ∈ 组级 ±1（且 n ∉ seeds）进入 expanded / content，当且仅当：
  1) cosine(nearest_seed, n) ≥ EXPAND_ANCHOR_MIN   # 与最近命中块连续
  2) score(query, n)  ≥ EXPAND_QUERY_MIN           # 与问题别太差
       score = rerank(query, n)   # 有 Key：邻居批量再调一次 Rerank
             = cosine(query, n)   # 无 Key 降级
```

| 配置 | 默认起步 | 说明 |
| --- | --- | --- |
| `EXPAND_ANCHOR_MIN` | **0.6** | 最近 seed–邻居余弦 |
| `EXPAND_QUERY_MIN` | **0.3** | **低于**全局 `RELEVANCE_MIN_SCORE=0.5`，否则邻居易全灭 |
| 全局 `RELEVANCE_MIN_SCORE` | 0.5 | 只约束命中锚点（seeds） |

说明：未命中邻居没有「原 Rerank 分」；query 侧是 **二次** 打分。邻居可跨组去重后一批 Rerank。

---

## 2. 流水线

```text
Recall → RRF → Rerank → RELEVANCE_MIN_SCORE(0.5)
  → 按 parent_id（或 doc+heading）分组：
       seeds = 组内命中
       candidates = seeds ∪ 各 seed 的 ±1（id 去重）
       neighbor = candidates \ seeds
       双条件过滤 neighbor → expanded
       content = seeds ∪ expanded（按 chunk_index，≤4000；seeds 必留）
       发出 1 条 hit（代表锚点 = max score seed）
  → 按 score 排序返回
```

---

## 3. 示例

```text
XX 项目总结: A(命中) B C D E F(命中) G
```

| 组 | seeds | neighbor | expanded | content（示意） |
| --- | --- | --- | --- | --- |
| 同父 | `{A,F}` | `{B,E,G}` | B/E/G 各自过双条件 | 如 `A+B+…+F+…` 按 index；**1 条 hit** |

C、D ∉ neighbor。相邻双命中（如 A、B）时互为 seed，不会各扩一次变成两条相同 context。

---

## 4. SearchHit

| 字段 | 含义 |
| --- | --- |
| `chunk_id` | 组内最高分 seed（代表锚点） |
| `original_content` | 代表锚点原文 |
| `content` | seeds ∪ expanded |
| `neighbor_chunk_ids` | 组级 ±1 非 seed 候选 |
| `expanded_chunk_ids` | 双条件过线邻居 |

---

## 5. 审计 / 引用 / Merge

- citations / `evidence_refs`：两字段；`dropped = neighbor - expanded`
- 可选写入 `anchor_sim` / `query_score` 便于排查
- `assembly`：`child_only` \| `neighbor_expand`
- `merge_evidence`：**按 `chunk_id` 去重**（检索侧已同组合并，Merge 仍防跨 Qi 重复）

---

## 6. 验收

1. 命中 A、F（同父）→ **1** 条 hit；C/D ∉ `neighbor_chunk_ids`  
2. 只过锚点相似、query 分不够 → 不进 expanded  
3. 只过 query、与最近 seed 不连续 → 不进 expanded  
4. heading 空且无 parent → 两列表 `[]`  
5. 有 Key 时邻居走批量 Rerank；无 Key 走余弦  
6. 相邻双命中 → **1** 条 content，不出现两条相同拼接  

---

## 7. 落点

`search.py`、`config`（`EXPAND_ANCHOR_MIN` / `EXPAND_QUERY_MIN`）、`audit/evidence.py`、Chat / `node_retrieve_qi`、`evidence_merge`；落地改 `TECH.md`。

**非目标：** 同父全量子块 Rerank；parent 全文默认；新 node_type；复用「原 Rerank 分」给未命中邻居。
