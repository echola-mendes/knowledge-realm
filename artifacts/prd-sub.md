# 当前子需求：检索同节扩窗（Parent-Child V0）

> 需求来源：`docs/PRD_Chunk_V0.md`（只读）  
> 挂载：`search_chunks` 返回前；不改切块 / 表结构 / `search_debug`

## 1. 目标

命中单个 child 后，在字符预算内把同 `(document_id, heading)` 下相邻 child 拼进该 hit 的 `content`，缓解同节上下文被切散导致回答不完整；引用仍指向命中 child。

## 2. 背景

Markdown 切块：标题分段 → section 内再切 child，只入库 child。Hybrid 检索命中单块时，同节定义/场景常在邻块。V0 不做父子表，仅在检索结果组装阶段运行时扩窗。

## 3. 功能范围

- `SearchHit` 增加 `original_content`；`content` 改为扩窗后文本（未扩时等于原 child）
- 在 `_keep_relevant(_rerank(...))` 之后、`return` 之前调用 `_expand_same_heading(session, hits)`
- 实现与单测主要落在 `server/app/rag/search.py`（及对应测试）
- 文档：Phase 4 同步 `docs/TECH.md` 检索段一句；`docs/PRD.md` §3.2 链到本需求

凡走 `search_chunks` 的调用方（Chat / Agent / 搜索页 / 相关推荐 / 首页推荐）统一受益，调用方代码原则上不改（只读 `content` / `chunk_id` / `score`）。

## 4. 非目标

- 不新增 `document_chunk` 字段（无 `parent_id` / `role`）
- 不改索引流水线、不强制 reindex
- 不做导入页切片策略 radio 第五项
- `search_debug` 各阶段不做扩窗
- 不做 overlap 去重、不做真实 token 预算
- 不实现 V1 父行落库（`PRD_Chunk_V1.md`）

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 扩窗键 | `(document_id, heading)`；`heading` 为 `None` 或 `""` 则不扩窗，仅设 `original_content` |
| 输出顺序 | 去重后按保留 hit 的 `score` 降序 |
| 返回条数 | 仍 ≤ Top-K；同节多命中去重后可更少；**不是** TopK×邻块变长 |
| 去重 | 同组保留 rerank `score` 最高的一条，再扩窗；扩窗后不改 `score` |
| 预算 | `SECTION_EXPAND_MAX_CHARS = 4000`；按完整 child 累加；超则整块不加；禁止字符截断 |
| 命中块超预算 | 命中块长度已 > 4000 仍保留全文，不再加邻块 |
| 选型顺序 | 先放命中块，再按 `chunk_index` 距离 1,2,… 左右交替（center-out）；一侧加不进仍可试另一侧同距离；两侧该距离都加不进则停止向外 |
| 正文顺序 | 已选块按 `chunk_index` 升序、`\n\n` 拼接 |
| 字段 | `chunk_id` / `score` / 其它字段不变；`original_content` = 命中 child 原文；不新增 `source_chunk_id` |
| overlap | 邻块边界重复文字 V0 接受，不去重 |

## 6. 输入与输出

- 输入：门槛过滤后的 `list[SearchHit]` + DB session（查同 heading 切片）
- 输出：可能更少条数的 `list[SearchHit]`；每条含 `original_content`；可扩者 `content` 为拼接文

## 7. 涉及模块

- 改：`server/app/rag/search.py`（`SearchHit`、`_expand_same_heading`、`search_chunks` 挂载）
- 测：`_expand_same_heading` 单测 + `search_chunks` 无 heading/单块回归
- 文档：`docs/TECH.md`、`docs/PRD.md` §3.2（Phase 4）
- 不动：切块/索引、`search_debug`、前端切片 radio、表结构/迁移

## 8. 验收标准

| ID | 标准 |
| --- | --- |
| AC-01 | 同 heading 下 C0/C1/C2，只命中 C1 → 1 条；预算内 `content` 含可装下的邻块；`original_content`/`chunk_id` 为 C1 |
| AC-02 | Top-K 同节命中 C0（低分）与 C1（高分）→ 只保留 C1，无重复整节 |
| AC-03 | `heading` 为空 → 不扩；`content` 与扩窗前一致 |
| AC-04 | 邻块再加会超 4000 → 不加该邻块；已选无截断；命中块必在 `content` |
| AC-05 | `search_debug` final 仍为 child 口径 |
| AC-06 | 现有 Chat/搜索/Agent 单测在 mock 下不因新字段崩溃（字段可选默认或测试补齐） |

## 9. 待确认问题

无（确认①已采纳：空串等同 None 不扩窗；去重后按 score 降序）。
