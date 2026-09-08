# 同节上下文扩窗（Parent-Child V0）

**需求名称：** 检索同节扩窗  
**版本：** V0  
**状态：** 已拍板，待开发  
**所属模块：** 知域 → 检索（`search_chunks`）  
**关联：** [`PRD.md`](PRD.md) §3.2；进阶方案见 [`PRD_Chunk_V1.md`](PRD_Chunk_V1.md)

---

## 0. 已拍板决策摘要

| 主题 | 结论 |
| --- | --- |
| 目标 | 缓解「同节内定义/场景被切到相邻 child、只命中一块导致回答不完整」 |
| 改动范围 | **仅**生产路径 `search_chunks` 返回前扩窗；不改切块、不改表、不改 `search_debug` |
| 扩窗键 | `(document_id, heading)`；`heading` 为空则不扩窗 |
| 返回条数 | 仍 ≤ Top-K；同节多命中去重后可能更少；**不是** TopK×邻块列表变长 |
| 去重 | 用扩窗前的 **rerank `score`**；保留分最高的 hit，再扩窗；扩窗后不改 `score` |
| 预算 | `SECTION_EXPAND_MAX_CHARS = 4000`；按**完整 child**累加；超则整块不加；**禁止**字符截断 |
| 累加顺序 | 先放命中块，再按 `chunk_index` 距离左右交替（center-out）；一侧加不进仍可试另一侧同距离 |
| 最终正文顺序 | 已选块按 `chunk_index` 升序、`\n\n` 拼接 |
| SearchHit | 增加 `original_content`；`content` = 扩窗后文本；`chunk_id` 仍为命中 child |
| 前端切片策略 | 不改占位 radio；本需求不是切分策略 |
| 调用方 | Chat / Agent / 搜索页 / 相关推荐 / 首页推荐凡走 `search_chunks` 均受益 |

---

## 1. 背景与问题

当前 Markdown 切块为：标题分段 → section 内再按 `chunk_size` / `overlap` 切 child，只把 child 写入 `document_chunk` 并检索。

Hybrid 检索（向量 + BM25 + RRF + Rerank）命中的是 **单个 child**。若同一技术概念的定义在第 3 块、应用在第 4 块，问法偏一边时往往只召回一块，生成上下文不完整。

V0 不引入父子表结构，在检索结果组装阶段把「同标题下的伪兄弟」拼进同一条 hit 的 `content`。

---

## 2. 需求目标

1. 命中某 child 后，尽量带上同 `heading` 下相邻 child 的正文，供 LLM / 搜索展示。
2. 引用仍指向命中 child（`chunk_id` 不变），可点回原切片。
3. 控制单条扩窗长度，避免 prompt 爆炸；整块边界清晰，不出现句中截断。

---

## 3. 非目标（V0 不做）

- 不新增 `document_chunk` 字段（无 `parent_id` / `role`）。
- 不改索引流水线、不强制 reindex。
- 不把「父子」做成导入页切片方式 radio 的第五项。
- `search_debug` 各阶段仍展示 child，**不做**扩窗（避免污染标注口径）。
- 不做 overlap 去重、不做真实 token 预算。
- 不实现 V1 父行落库（见 [`PRD_Chunk_V1.md`](PRD_Chunk_V1.md)）。

---

## 4. 现状基线

### 4.1 `search_chunks` 流水线（改前）

```text
embed → 向量 top-k → BM25 → RRF → Rerank → 相关性门槛
  → return list[SearchHit]（content = 单 child 原文）
```

实现：[`server/app/rag/search.py`](../server/app/rag/search.py)

### 4.2 `SearchHit`（改前）

`document_id` / `document_name` / `chunk_id` / `content` / `score` / `page` / `heading` / `kind`

### 4.3 表与 metadata

- 扩窗依赖列：`document_id`、`heading`、`chunk_index`、`content`
- 行内 `metadata` 当前入库为空 `{}`；V0 不依赖、不写入

---

## 5. 功能需求

### 5.1 挂载点

在 `_keep_relevant(_rerank(...))` 之后、`return` 之前调用 `_expand_same_heading(session, hits)`。

### 5.2 扩窗算法

对门槛过滤后的 `hits`：

1. **去重**：按 `(document_id, heading)` 分组；`heading` 为空的 hit 跳过扩窗，仅设 `original_content = content`（或等值）。
2. 每组保留 **score 最大** 的一条作为 source hit。
3. 批量查询该 `document_id` 下 `heading` 相同的所有切片，按 `chunk_index` 排序。
4. **center-out 选型**：
   - 先纳入命中块（若命中块长度已 > 4000，仍保留全文，不再加邻块）。
   - 再按距离 1, 2, … 交替尝试左邻、右邻；某一侧整段加入会超预算则**不加该侧该距离**，仍可试另一侧同距离；两侧在该距离都无法再加则停止向更远扩展。
5. 将已选块按 `chunk_index` 升序用 `\n\n` 拼成 `content`。
6. 写出：
   - `original_content` = 命中块原文
   - `content` = 拼接结果
   - `chunk_id` / `score` / 其它字段不变

### 5.3 预算常量

```text
SECTION_EXPAND_MAX_CHARS = 4000
```

- 用字符数，不用 tokenizer。
- 只判断「下一块全文加上去是否超过」；从不对已选文本做 `[:N]`。

### 5.4 调用方行为

继续只读 `content` / `chunk_id` / `score` 即可：

| 调用方 | 路径 |
| --- | --- |
| Chat | `app/rag/chat.py` |
| Agent | `app/agent/tools.py` → `search_knowledge` |
| 搜索 API | `app/routers/search.py` |
| 相关文档 | `app/routers/documents.py` |
| 推荐 | `app/recommendations.py` |

搜索页 / 推荐会看到更长 `content`：V0 **接受**统一行为。

### 5.5 overlap

同节拼接时，因切块 overlap，相邻块边界文字可能重复。V0 **接受**，不做去重。

---

## 6. SearchHit 契约（改后）

| 字段 | 含义 |
| --- | --- |
| `chunk_id` | 扩窗前得分最高的 source child（引用/跳转） |
| `score` | 扩窗前 rerank 分（去重依据；扩窗后不变） |
| `original_content` | 扩窗前该 child 原文；未扩窗时等于扩窗前 `content` |
| `content` | 给 LLM / 展示的文本（扩窗后整节或未扩时的原块） |
| 其余 | `document_id` / `document_name` / `page` / `heading` / `kind` 不变 |

不新增 `source_chunk_id`（与 `chunk_id` 重复）。

---

## 7. 验收标准

1. 同 heading 下 C0/C1/C2，只命中 C1 → 返回 1 条；`content` 在预算内含 C0+C1+C2（或 center-out 能装下的子集）；`original_content` 为 C1；`chunk_id` 为 C1。
2. Top-K 同时命中同节 C0（低分）与 C1（高分）→ 只保留 1 条（C1），无重复整节。
3. `heading is None` → `content` 与扩窗前一致（不扩）。
4. 邻块再加会超 4000 → 不加该邻块，已选块无字符截断；命中块必在 `content` 中。
5. `search_debug` final 仍为 child 口径，与标注一致。
6. 现有 Chat / 搜索 / Agent 单测在 mock 下不因新字段崩溃（`original_content` 可选默认或测试补齐）。

---

## 8. 测试要点

- 单元：`_expand_same_heading` — 整节拼接、同节去重、heading 空、超预算整块停、center-out 保证含命中块、`original_content`。
- 回归：`search_chunks` 在无 heading / 单块文档行为与改前一致（除多字段）。

---

## 9. 文档与实现落点

| 项 | 说明 |
| --- | --- |
| 实现 | `server/app/rag/search.py` |
| 技术说明 | 同步更新 [`TECH.md`](TECH.md) 检索段一句 |
| 主 PRD | [`PRD.md`](PRD.md) §3.2 增加本需求链接 |

---

## 10. 与 V1 的边界

V0 用 `(document_id, heading)` **运行时**拼伪父上下文。  
V1 在索引时写入 parent/child 关系（`parent_id`），检索用父全文或同父兄弟；见 [`PRD_Chunk_V1.md`](PRD_Chunk_V1.md)。
