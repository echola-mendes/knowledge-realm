# Execution Plan：父子切块落库（Parent-Child V1）

> 依据：`artifacts/prd-sub.md` / `docs/PRD_Chunk_V1.md`。  
> 栈：FastAPI；一张 `document_chunk`；parent 无向量、不进 ES；检索仅 child；无 parent 降级 V0；不改导入页 UI。  
> 从顶部取第一个未全 ✅ 的 Step 执行。

---

## Step 1：模型与迁移

### 目标

`document_chunk` 支持 `role` / `parent_id`，parent 行 `embedding` 可空。

### 方案

1. `server/app/models.py` `DocumentChunk`：
   - `role: str`，默认 `"child"`（`child` | `parent`）
   - `parent_id: UUID | None`，FK → `document_chunk.id`，`ondelete` 与现有文档级删除一致（级联随 document 删即可；自表 FK 用 `SET NULL` 或允许随父删）
   - `embedding` 改为 `nullable=True`
2. Alembic `20260908_0025_chunk_parent_child.py`：加列 + 存量 `role='child'`；`embedding` 改可空
3. 不写业务索引逻辑

### 验收

- [✅] `alembic upgrade` / `downgrade` 可跑通（本机）
- [✅] 模型字段与迁移一致：`role` 默认 child、`parent_id` 可空、`embedding` 可空

---

## Step 2：切块产出父子结构

### 目标

`split_markdown`（或紧邻纯函数）按 section 产出 parent 候选 + children；短 section 不写空父。

### 方案

1. 扩展 `server/app/ingest/chunk.py`：保留表格保护 / FAQ；按现有 header 分段
2. 每个 section：
   - 正文长度 ≤ `chunk_size` 且不再切：仅 1 个 child，`role=child`，无 parent（对应落库 `parent_id=null`）
   - 需再切：parent = section 全文（restore 后）；children = size+overlap 切分结果
3. 数据结构用 dataclass（如 `SectionSplit`：`parent: TextChunk | None` + `children: list[TextChunk]`），避免破坏无关调用时可提供兼容包装
4. 单测扩 `server/tests/test_chunk.py`：短节无 parent、长节有 parent+多 child、表格超长整段策略与现一致

### 验收

- [✅] 短节：只有 child、无 parent 对象
- [✅] 长节：1 parent 全文 + ≥2 children，children 正文覆盖在 parent 内（或与现切分一致）
- [✅] `server/tests/test_chunk.py` 相关用例通过

---

## Step 3：索引写库 / ES / 旁路读

### 目标

全量与增量索引写入父子；仅 child embed + ES；旁路读避免父行重复正文。

### 方案

1. `index_document` / `index_document_incremental`：
   - 先写 parent（`embedding=None`），再写 child（`parent_id`、embed）
   - `chunk_index` 文档内统一递增（含 parent 行）
   - ES `upsert_chunks` **只**传 child
   - 短节：仅 child，`parent_id=null`
2. 增量对齐键扩展为含 `role` + 结构（如 parent 用 `(role, heading, content)`，child 用 `(role, heading, content)` 且与 parent 关联）；避免只比 child 正文导致父行漂移
3. `reindex_chunk`：若 `role=parent` 或 `embedding is None` → 跳过/报错明确（不向量化 parent）
4. 最小旁路：`gather_document_text`、`_chunks_for_document` 只取 `role=child`（或 `role != 'parent'`），避免摘要/切片列表重复父全文
5. 单测：`test_index.py` / `test_incremental_index.py` 覆盖父子落库与仅 child 进 ES（ES 侧可 mock）

### 验收

- [✅] 新索引 Markdown 长节：库中 parent+children，`child.parent_id` 正确；parent `embedding is None`
- [✅] ES upsert 入参不含 parent id
- [✅] 增量对齐含 role/parent 结构（有测或源码断言）
- [✅] `gather_document_text` / 文档 chunks API 路径不把 parent 当普通切片重复露出
- [✅] 相关 index / incremental 单测通过

---

## Step 4：检索过滤与 parent 组装

### 目标

检索仅 child；有 `parent_id` 则用 parent 全文（预算内）；同父去重；否则 V0 扩窗。

### 方案

1. `_vector_stmt` / `_hits_for_ids`（及 BM25/RRF 合并后的候选若再查库）：加召回保险
   - 主条件：`DocumentChunk.role == "child"`（迁移后存量默认 child）
   - 再加一道：`DocumentChunk.embedding.isnot(None)`，避免父行（无向量）误入向量召回；两条件同时生效（AND）
2. 替换或包装 `_expand_same_heading` 挂载点：新函数（如 `_assemble_parent_context`）：
   - 有 `parent_id`：批量加载 parent；同 parent 保留最高分 hit；`content=parent.content`，`original_content=child`；parent 超 `SECTION_EXPAND_MAX_CHARS` 则对该 parent 下 children 做 center-out 整块回退
   - 无 `parent_id`：走现有 `_expand_same_heading`
3. `search_chunks`：rerank+门槛后调用组装；`search_debug` 仍不组装
4. 单测：新测文件或扩 `test_expand_same_heading.py` / `test_search.py`——parent 组装、同父去重、无 parent→V0、超预算整块回退

### 验收

- [✅] 向量查询条件含 `role=child` 且 `embedding IS NOT NULL`（源码/测）
- [✅] 有 parent：`content` 为 parent 全文（或预算回退拼接）；`chunk_id`/`original_content` 为命中 child
- [✅] 同父多命中只保留一条
- [✅] 无 `parent_id`：行为等同 V0 扩窗（既有扩窗测仍过）
- [✅] `search_debug` 无组装调用
- [✅] 相关 search / expand 单测通过

---

## Step 5：文档同步

### 目标

TECH / 主 PRD 反映 V1 数据模型与检索组装；architecture 已在 Phase 2 写入长期约束则本 Step 只核对。

### 方案

1. `docs/TECH.md`：切块/检索段写清 parent-child 落库、仅 child 检索、组装与 V0 降级
2. `docs/PRD.md` §3.2：链到 `PRD_Chunk_V1.md`（保留 V0 链）
3. 不改导入页；不改 AGENTS 栈（一张表约束已存在，可一句补充 role/parent_id）

### 验收

- [✅] TECH.md 已描述 V1 父子落库与检索组装
- [✅] PRD.md §3.2 已链到 V1
- [✅] execution-plan 全部验收项为 [✅]
