# 当前子需求：局部邻居扩窗 + 双条件过滤（Chunk V3）

> 需求来源：`docs/rag/PRD_Chunk_V3.md`（只读）  
> 前置：V0 同节扩窗、V1 Parent-Child；本需求**替换**检索组装策略，不改切块落库  
> 修订：同父 / 同 heading 多命中 **合并为 1 条 hit**（seeds ∪ ±1 去重 → 双条件 → 按 index 拼接）

## 1. 目标

将 `search_chunks` 返回前的上下文组装，从「同父去重 → parent 全文 / V0 center-out / 每 hit 独立扩窗」改为：**同组命中合并**，组内 seeds ∪ ±1 去重后仅对非 seed 邻居做双条件过滤，按 `chunk_index` 拼成一条 `content`；并同步审计 / Merge / 引用字段。

## 2. 背景

V1 同父合成一条、V0 按 heading 扩窗会吞掉多命中粒度或扩入弱相关兄弟块。V3 初版「每 hit 独立 ±1」在相邻双命中时会拼出两条相同 context。修订后在 Rerank + `RELEVANCE_MIN_SCORE(0.5)` 之后按组合并，避免重复 context，同时仍用双条件克制扩窗。

## 3. 功能范围

- `search.py`：`_neighbor_expand` 按组合并；双条件仅打非 seed；代表锚点取组内最高分
- `SearchHit`：`neighbor_chunk_ids`、`expanded_chunk_ids`；`chunk_id` / `original_content` = 最高分 seed；`content` = seeds ∪ expanded
- 配置：`EXPAND_ANCHOR_MIN`（默认 0.6）、`EXPAND_QUERY_MIN`（默认 0.3）；预算 `SECTION_EXPAND_MAX_CHARS=4000`
- query 侧打分：有 Rerank Key → 邻居去重后批量 Rerank；无 Key → `cosine(query, n)`
- 审计 / Chat / Merge / `search_debug`：与现网一致（debug 不组装；Merge 仍按 `chunk_id`）
- 文档：`docs/TECH.md`、`docs/PRD.md`、`docs/rag/PRD_Chunk_V3.md`

## 4. 非目标

- 同父全量子块再 Rerank
- parent 全文作为默认组装
- 新 node_type / 改切块落库 schema
- 复用「原 Rerank 分」给未命中邻居
- 改 `/api/chat` 编排为 LangGraph；改 Embedding / Rerank 供应商

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 触发点 | Recall → RRF → Rerank → `RELEVANCE_MIN_SCORE=0.5` 之后分组组装 |
| 分组键 | 有 `parent_id` → 同父；无 → `(document_id, heading)`；**仅无 parent 且 heading 空 → 各 hit 独立且不扩** |
| seeds | 组内命中 chunk；已过全局门槛，不参与双条件 |
| ±1 | 各 seed 的 `chunk_index` 相邻块并入候选，去掉已是 seed 的 id → `neighbor_chunk_ids` |
| 双条件 | `cosine(nearest_seed,n) ≥ EXPAND_ANCHOR_MIN` **且** `score(query,n) ≥ EXPAND_QUERY_MIN` |
| score(query,n) | 有 Key：批量 Rerank；无 Key：query–chunk 余弦 |
| 同组多命中 | N 条命中 → **1** 条 hit；`score` = max(seeds) |
| content | seeds ∪ expanded，按 `chunk_index`；总长 ≤4000，seeds 优先、整块不截断 |
| Merge | 去重键 `chunk_id`（防跨 Qi 重复） |

## 6. 验收标准

1. 同节命中 A、F → **1** 条 hit；C/D ∉ `neighbor_chunk_ids`
2. 仅锚点相似过线、query 分不够 → 不进 `expanded_chunk_ids`
3. 仅 query 过线、与最近 seed 不连续 → 不进 `expanded_chunk_ids`
4. 无 `parent_id` 且 `heading` 空 → 两列表均为 `[]`；有 `parent_id` 时 heading 空仍可同父 ±1
5. 有 Rerank Key 时邻居走批量 Rerank；无 Key 走余弦
6. 相邻双命中 → 1 条 content，不出现两条相同拼接
7. `search_debug` 路径不触发邻居组装
