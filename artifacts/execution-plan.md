# Execution Plan：检索同节扩窗（Parent-Child V0）

> 依据：`artifacts/prd-sub.md` / `docs/PRD_Chunk_V0.md`。  
> 栈：FastAPI；改动仅 `server/app/rag/search.py` + 单测；不改切块/表/`search_debug`。  
> 从顶部取第一个未全 ✅ 的 Step 执行。

---

## Step 1：SearchHit + `_expand_same_heading`

### 目标

落地扩窗数据结构与纯算法，可独立单测。

### 方案

1. `SearchHit` 增加 `original_content: str = ""`（默认空，避免调用方构造崩溃）
2. 常量 `SECTION_EXPAND_MAX_CHARS = 4000`
3. 实现 `_expand_same_heading(session, hits) -> list[SearchHit]`：
   - `heading` 为 `None`/`""`：不扩窗，`original_content = content`，保留原 hit
   - 按 `(document_id, heading)` 分组，组内留 `score` 最大；输出按保留 hit 的 `score` 降序
   - 批量查同 `document_id` + 同 `heading` 的 `DocumentChunk`，按 `chunk_index` 排序
   - center-out 选型（命中块必留；整块预算；一侧失败仍试另一侧；两侧同距都加不进则停）
   - `content` = 已选块按 `chunk_index` 升序 `\n\n` 拼接；`chunk_id`/`score`/其余字段不变
4. 单测文件（如 `server/tests/test_expand_same_heading.py`）：用 mock session / 内存行覆盖 AC-01～04

### 验收

- [ ] `_expand_same_heading` 单测：整节拼接、同节去重、空 heading、超预算整块停、命中块必含、`original_content`
- [ ] `SearchHit` 可不传 `original_content` 构造（默认值）

---

## Step 2：挂载 `search_chunks`，隔离 `search_debug`

### 目标

生产检索路径启用扩窗；debug 路径保持 child 口径。

### 方案

1. `search_chunks`：`return _expand_same_heading(session, _keep_relevant(_rerank(query, hits)))`
2. `_hit_from_row` 等构造处可不显式设 `original_content`（扩窗函数统一补齐）
3. 确认 `search_debug` 不调用 `_expand_same_heading`
4. 回归：`test_search.py` 等现有 search 单测；无 heading / 单块行为除多字段外与改前一致

### 验收

- [ ] `search_chunks` 源码在 rerank+门槛之后调用 `_expand_same_heading`
- [ ] `search_debug` 路径无扩窗调用（路径/grep 验证）
- [ ] 现有 `server/tests/test_search.py` 通过

---

## Step 3：调用方兼容与文档

### 目标

Chat / Agent / 搜索相关 mock 测试不因新字段崩溃；文档同步。

### 方案

1. 跑与 `SearchHit` / `search_chunks` 相关的既有测试（chat / agent / search）；若构造 `SearchHit` 处缺字段则依赖默认值或最小补齐
2. `docs/TECH.md` 检索段补一句同节扩窗；`docs/PRD.md` §3.2 链到 `PRD_Chunk_V0.md`
3. 不改 AGENTS 栈；architecture 无长期结构变化不更新

### 验收

- [ ] 相关既有单测通过（无因 `original_content` 新增失败）
- [ ] TECH.md / PRD.md §3.2 已更新
- [ ] execution-plan 全部 [✅]
