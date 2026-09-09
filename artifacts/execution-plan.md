# Execution Plan

> 子需求：局部邻居扩窗 + 双条件过滤（Chunk V3）  
> 栈约束：FastAPI + 单表 `document_chunk`；组装只在 `search_chunks`；不改切块落库；DashScope Rerank/Embedding  
> 已确认：heading 空仅约束「无 parent」；旧 V0/V1 组装函数删除

## Step 1：配置 + SearchHit + 邻居双条件组装（替换旧路径）

### 目标
在 `search_chunks` 门槛后落地 V3 组装；删除旧 parent/V0 组装；配置双阈值。

### 方案
- `config.Settings` 增加 `expand_anchor_min`（默认 0.6）、`expand_query_min`（默认 0.3）；环境变量 `EXPAND_ANCHOR_MIN` / `EXPAND_QUERY_MIN`。
- `SearchHit` 增加 `neighbor_chunk_ids: list[uuid.UUID]`、`expanded_chunk_ids: list[uuid.UUID]`（默认空列表）。
- `_neighbor_expand`：按 `parent_id`（或无 parent 时 `doc+heading`）分组；组内 seeds ∪ 各 seed ±1 去重；非 seed 用 `cosine(nearest_seed, n)` ∧ query 分双条件；按 `chunk_index` 拼 **1** 条 `content`；代表锚点 = max score seed。无 parent 且 heading 空 → 不扩。
- `search_chunks` 末尾调用 `_neighbor_expand(...)`；旧 parent/V0 组装已删。
- `search_debug` 不调用组装。

### 验收
- [✅] 单测：同父序列 A…F，命中 A、F → **1** 条 hit；C/D ∉ `neighbor_chunk_ids`（PRD§6.1 修订）
- [✅] 单测：相邻双命中 → 1 条 content，不重复
- [✅] 单测：仅锚点相似过 / 仅 query 过 → 均不进 `expanded_chunk_ids`（§6.2–3）
- [✅] 单测：无 parent + heading 空 → 两列表 `[]`；有 parent + heading 空仍可 ±1（确认① B）
- [✅] 单测或分支测：无 Rerank Key 时走余弦；有 Key 时调用批量 Rerank 路径（可 mock）（§6.5）
- [✅] 源码断言：`search_chunks` 调用新组装；`search_debug` 源码不含邻居组装调用；旧函数名已删除

---

## Step 2：审计 evidence 字段与 assembly

### 目标
retrieve / citations 可区分候选邻域与过线邻域；`assembly` 改为 V3 取值。

### 方案
- `search_hit_evidence_ref`：写入 `neighbor_chunk_ids`、`expanded_chunk_ids`；`dropped = neighbor - expanded`；可选 `anchor_sim` / `query_score`（若 hit 或组装侧有缓存则带上，无则省略）。
- `_assembly_kind` / `context_assembly_summary`：取值 `child_only` | `neighbor_expand`（去掉依赖 parent/heading_expand 作为默认语义；兼容旧测改断言）。
- Chat / `node_retrieve_qi` 已用 `search_hit_evidence_ref` 则无需改编排；抽检调用链仍能拿到新字段。

### 验收
- [✅] 单测：`search_hit_evidence_ref` 含两 id 列表与 dropped；有扩窗时 `assembly=neighbor_expand`，无则为 `child_only`
- [✅] `context_assembly_summary` 计数键与新 assembly 一致
- [✅] 既有 audit 相关测通过（更新过时断言）

---

## Step 3：`merge_evidence` 按 chunk_id 去重

### 目标
作答前 Merge 不再按 `parent_id` 压成 1 条，与 V3「同父多命中」一致。

### 方案
- `_dedup_key` 改为仅 `chunk_id`（或等价 id）；更新 docstring。
- 调整 `test_evidence_merge`：同 parent 不同 chunk → 两条都保留；同 chunk 仍去重并合并 `related_questions`。

### 验收
- [✅] 单测：同 `parent_id`、不同 `chunk_id` → Merge 后仍为 2 条（prd-sub §8.6）
- [✅] 单测：同 `chunk_id` 仍去重并合并 related_questions / 留高分
- [✅] `server/tests/test_evidence_merge.py`（及相关 sufficiency 若依赖旧语义）通过

---

## Step 4：文档与测试收口

### 目标
TECH 描述与现网一致；旧扩窗测文件改为 V3 或删除后由 Step1 新测覆盖。

### 方案
- `docs/TECH.md`：检索组装改为「门槛后每 hit ±1 + 双条件」；注明不再默认 parent 全文 / V0 center-out。
- 将 `test_expand_same_heading.py` 重写/替换为邻居扩窗测（若 Step1 已新建文件则删除旧文件避免双套）。
- Phase 4 再同步 `docs/PRD.md`（本 Step 不强制改 PRD.md）。

### 验收
- [✅] `docs/TECH.md` 已描述 V3 组装与两字段
- [✅] 仓库无仍断言 `_assemble_parent_context` / parent 全文默认路径的过时测
- [✅] 对本需求相关测文件跑通：`test_neighbor*`（或等价）+ `test_audit_evidence` + `test_evidence_merge`
