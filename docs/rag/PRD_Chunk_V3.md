# 局部邻居扩窗 + 双条件过滤（V3）

**状态：** 已拍板，待开发  
**改：** `search_chunks` 组装（`search.py`）  
**关联：** [`PRD.md`](../PRD.md) §3.2；前置 V0/V1

---

## 0. 拍板

| 项 | 结论 |
| --- | --- |
| 替换 | 去掉同父去重→parent 全文 / V0 center-out |
| 策略 | **每条命中独立** ±1；邻居须过 **双条件** 才进 content |
| 同父多命中 | 几条命中就几条 hit，**不合成 1 条** |
| 兄弟键 | 有 `parent_id`→同父；无→`(doc, heading)`；heading 空不扩 |
| 双条件 | 见 §1；锚点不参与过滤（已过全局 0.5） |
| 预算 | `SECTION_EXPAND_MAX_CHARS=4000`，整块、不截断 |
| 字段 | `neighbor_chunk_ids`（±1 候选）、`expanded_chunk_ids`（双条件过线，⊆ neighbor） |
| 重叠 | 两 hit 邻域重叠各管各的 |
| debug | `search_debug` 不组装 |
| 审计 | `retrieve` span 映射两字段 + dropped + 可选双分 |

---

## 1. 邻居进 content 条件（核心）

```text
n ∈ ±1 进入 expanded / content，当且仅当：
  1) cosine(anchor, n) ≥ EXPAND_ANCHOR_MIN     # 与命中块连续（embedding）
  2) score(query, n)  ≥ EXPAND_QUERY_MIN      # 与问题别太差
       score = rerank(query, n)   # 有 Key：邻居批量再调一次 Rerank
             = cosine(query, n)   # 无 Key 降级
```

| 配置 | 默认起步 | 说明 |
| --- | --- | --- |
| `EXPAND_ANCHOR_MIN` | **0.6** | 锚点–邻居余弦 |
| `EXPAND_QUERY_MIN` | **0.3** | **低于**全局 `RELEVANCE_MIN_SCORE=0.5`，否则邻居易全灭 |
| 全局 `RELEVANCE_MIN_SCORE` | 0.5 | 只约束命中锚点 |

说明：未命中邻居没有「原 Rerank 分」；query 侧是 **二次** 打分。邻居可跨 hit 去重后一批 Rerank。

---

## 2. 流水线

```text
Recall → RRF → Rerank → RELEVANCE_MIN_SCORE(0.5)
  → 每条 hit：
       ±1 → neighbor_chunk_ids
       算 cosine(anchor,·)；批量 score(query,·)
       双条件都过 → expanded_chunk_ids
       content = 锚点 ∪ expanded（按 chunk_index，≤4000）
  → 按 score 排序返回
```

---

## 3. 示例

```text
XX 项目总结: A(命中) B C D E F(命中) G
```

| Hit | neighbor | expanded | content |
| --- | --- | --- | --- |
| A | `[B]` | 仅当 B 过双条件 | A 或 A+B |
| F | `[E,G]` | E/G 各自独立过双条件 | 如仅 F，或 E+F+G 等 |

C、D ∉ neighbor。B 只挂在 A 上；不因「二次必 &lt;0.5」预设全灭——以双条件实算为准。

---

## 4. SearchHit

| 字段 | 含义 |
| --- | --- |
| `chunk_id` | 本条命中锚点 |
| `original_content` | 锚点原文 |
| `content` | 锚点 ∪ expanded |
| `neighbor_chunk_ids` | ±1 候选 |
| `expanded_chunk_ids` | 双条件过线邻居 |

---

## 5. 审计 / 引用 / Merge

- citations / `evidence_refs`：两字段；`dropped = neighbor - expanded`
- 可选写入 `anchor_sim` / `query_score` 便于排查
- `assembly`：`child_only` \| `neighbor_expand`
- `merge_evidence`：**按 `chunk_id` 去重**（勿再按 `parent_id` 压成 1 条）

---

## 6. 验收

1. 命中 A、F → **2** 条 hit；C/D ∉ neighbor  
2. 只过锚点相似、query 分不够 → 不进 expanded  
3. 只过 query、与锚点不连续 → 不进 expanded  
4. heading 空 → 两列表 `[]`  
5. 有 Key 时邻居走批量 Rerank；无 Key 走余弦  

---

## 7. 落点

`search.py`、`config`（`EXPAND_ANCHOR_MIN` / `EXPAND_QUERY_MIN`）、`audit/evidence.py`、Chat / `node_retrieve_qi`、`evidence_merge`；落地改 `TECH.md`。

**非目标：** 同父全量子块 Rerank；parent 全文默认；新 node_type；跨 hit 去重；复用「原 Rerank 分」给未命中邻居。
