# 当前子需求：父子切块落库（Parent-Child V1）

> 需求来源：`docs/PRD_Chunk_V1.md`（只读）  
> 前置：V0 同节扩窗已落地（`search_chunks` + `_expand_same_heading`）；本需求改为索引时显式写 parent/child

## 1. 目标

索引阶段在同一张 `document_chunk` 表写入 parent（section 全文）与 child（可检索小块）；检索仍只命中 child，生成上下文默认用 parent 全文（预算不足时整块回退拼接）；未 reindex / 无 parent 的文档降级到现有 V0 或单 child。

## 2. 背景

V0 用 `(document_id, heading)` 运行时拼兄弟，验证「同节上下文」思路，但不改表。V1 要解决：同 heading 跨度过大、无稳定父全文、增量对齐困难——在索引时落 parent 行，检索过滤 child，命中后取 parent。

## 3. 功能范围

- 模型 / 迁移：`document_chunk` 增加 `role`（`child`|`parent`）、`parent_id`（nullable FK → 本表）；`embedding` 允许 parent 为空（或不参与检索）
- 切块 / 索引：`split_markdown` / `index_*` 两段式显式写 parent + child；表格保护 / FAQ 逻辑保持
- 检索：向量 / BM25 / RRF / Rerank 仅 child；组装默认 `content = parent.content`，`original_content` = 命中 child；同父多命中按 score 去重只装一次 parent
- Parent 超预算：按完整子块 center-out + 字符预算回退（复用 V0 思路），禁止字符串中途切断
- 无 parent / 旧数据：降级为 V0 同 heading 扩窗
- 文档：Phase 4 同步 `docs/TECH.md`、`docs/PRD.md` §3.2

## 4. 非目标

- 不上 Neo4j / 第二套向量表；不引入 LlamaIndex ParentDocumentRetriever
- 不做语义切块策略本身；不做完整「自定义切片策略」后端
- 不把「父子」做成导入页切片方式的第五个 radio
- 不改导入页 UI（切 child ≠ 上下文组装；组装维度后置）
- 不强制 `search_debug` 展示组装后上下文（另议）
- 不对外 API 强制暴露 `parent_id`（`SearchHit` 继续用现有字段即可）
- Parent：`embedding` 可空、不写向量、不进 ES；检索过滤 `role=child`

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 表约束 | 仍一张 `document_chunk`；parent/child 同行表，用 `role` + `parent_id` 区分 |
| 检索单位 | 仅 `role=child`（或 `embedding IS NOT NULL`）参与向量 / BM25 / RRF / Rerank |
| 生成上下文 | 默认 parent 全文；无 parent / 旧数据 → V0 `_expand_same_heading` |
| Parent 边界 | Markdown / 结构化文优先 `#`/`##`/`###` section |
| 短 section | 长度 ≤ `chunk_size` 且不再切分：只写一行，`role=child`，`parent_id=null`（无空父行） |
| 兄弟关系 | 同 `parent_id` + `ORDER BY chunk_index`；不存 sibling id 列表 |
| 同父去重 | 多 child 命中保留最高分，parent 只组装一次 |
| 字段契约 | `chunk_id`/`score` 仍为命中 child；`content` 为组装后；`original_content` 为 child 原文 |
| 迁移 | 存量须 **重新向量化** 才有父子；未 reindex 行为须有测例 |
| 增量索引 | 对齐键扩展含 `role`/parent 结构，避免父行漂移 |

## 6. 输入与输出

- 索引输入：现有解析后的 Markdown/结构化正文 + chunk_size/overlap  
- 索引输出：parent 行（content=section 全文，embedding 可空）+ child 行（embed + ES，`parent_id` 指向 parent）  
- 检索输入：与现网一致的 query / Top-K  
- 检索输出：仍为 `list[SearchHit]`；调用方（Chat / Agent / 搜索）不感知表结构

## 7. 涉及模块

- 改：`server/app/models.py` + Alembic 迁移
- 改：`server/app/ingest/chunk.py`、`server/app/ingest/index.py`
- 改：`server/app/rag/search.py`（组装逻辑；保留 V0 作降级）
- 测：索引落库、检索过滤 parent、组装/去重/降级
- 文档：`docs/TECH.md`、`docs/PRD.md` §3.2（Phase 4）
- 不动（本需求首期）：导入页 radio、Agent/Chat 调用方（只消费 SearchHit）

## 8. 验收标准

| ID | 标准 |
| --- | --- |
| AC-01 | 新导入带标题 Markdown：库中有 parent + 多个 child，且 `child.parent_id` 正确 |
| AC-02 | 向量 SQL / ES 检索不含 parent 行（或 parent 无有效检索向量） |
| AC-03 | 命中 child → `content` 为对应 parent 全文（或预算内整块回退）；`chunk_id`/`original_content` 为 child |
| AC-04 | 同父多命中去重，prompt 侧 parent 只出现一次 |
| AC-05 | 未 reindex 旧文档走明确降级策略，有测例 |
| AC-06 | Chat / Agent / 搜索路径仍只消费 `SearchHit`，无需改表结构感知 |

## 9. 待确认问题

无（确认①已拍板）：
1. V0 收益已确认，授权 V1 全量（模型+索引+检索）
2. 短 section：`role=child`，`parent_id=null`
3. 无 parent / 旧数据：降级 V0 扩窗
4. Parent：`embedding` 可空、不写向量、不进 ES；检索按 `role=child` 过滤
5. 不改导入页 UI；后端默认「有 parent 则用 parent 组装」（导入页切的是 child，与组装维度无关，后者后置）
