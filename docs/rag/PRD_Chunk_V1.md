# Parent-Child 切块与检索（V1）

**需求名称：** 父子切块落库  
**版本：** V1（规划）  
**状态：** 规划中；依赖 [`PRD_Chunk_V0.md`](PRD_Chunk_V0.md) 验证收益后再立项  
**所属模块：** 知域 → 切块 / 索引 / 检索  
**关联：** [`PRD.md`](PRD.md) §3.2；前置缓解方案见 V0

---

## 0. 已拍板方向摘要

| 主题 | 结论 |
| --- | --- |
| 相对 V0 | V0 是检索时按 heading 拼伪父上下文；V1 是**索引时**建立父子并落库 |
| 表约束 | 仍遵守「一张 `document_chunk`」；parent / child 同行表，用 `role` + `parent_id` 区分 |
| 检索单位 | **仅 child** 参与向量 / BM25 / RRF / Rerank |
| 生成上下文 | 命中 child 后取 **parent 全文**（优先），或同 `parent_id` 下兄弟按预算组装 |
| 切分策略 UI | 「怎么切 child」与「命中后用 parent」分两维；父子不是 fixed/recursive/semantic 的第五个 radio |
| Parent 边界 | Markdown / 结构化文优先用 `#` / `##` / `###` section 作 parent |
| 迁移 | 上线后需对存量文档 **重新向量化** 才具备父子关系 |

---

## 1. 背景与目标

V0 用现有 `heading` 列在 `search_chunks` 末尾扩窗，无需改表，可快速验证「同节上下文」是否提升回答完整度。

若 V0 有效但仍有问题（例如同 heading 跨度过大、无标题文档无法扩、希望 parent 单独存全文避免每次拼兄弟），则上 V1：

1. 索引阶段显式写入 parent 与 child。
2. 检索仍准（小块），生成上下文完整（父块）。
3. 为后续「自定义切片策略 + 上下文组装策略」预留数据模型。

---

## 2. 与 V0 对比

| | V0 | V1 |
| --- | --- | --- |
| 改表 | 否 | 是（同表加字段） |
| Parent 存储 | 无 | `role=parent` 行，content = section 全文 |
| 兄弟关系 | `(document_id, heading)` 现查 | 同 `parent_id` 查询；**不**存 sibling id 列表 |
| 扩窗 / 组装 | center-out 拼兄弟 | 默认用 parent.content；可选再按预算裁兄弟 |
| 切块代码 | 不动 | `split_markdown` / `index_*` 写两层 |
| reindex | 不需要 | 需要 |
| `search_debug` | 不扩窗 | 可增加「组装后上下文」展示（另议） |

---

## 3. 非目标（V1 首期）

- 不上 Neo4j 或第二套向量表。
- 不把 LlamaIndex ParentDocumentRetriever 整包引入。
- 不做「语义切块」本身（那是 child 切分策略另一条需求）。
- 不强制所有文档类型都有高质量 parent（无标题长文可降级为 V0 行为或仅 child）。
- 不在本需求内做完整「自定义切片策略」后端（导入页 radio 仍可后置接入）。

---

## 4. 数据模型（拟）

在现有 [`document_chunk`](../server/app/models.py) 上增量（示意，实现时以 Alembic 为准）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `role` | string | `child` \| `parent`；默认历史数据视为 `child` |
| `parent_id` | UUID nullable FK → `document_chunk.id` | child 指向 parent；parent 为 null |
| `embedding` | vector | **parent 可空或不参与检索**；child 必填 |

约束与查询：

- 向量 / ES BM25 **过滤** `role = child`（或 `embedding IS NOT NULL`）。
- 同父兄弟：`WHERE parent_id = :pid ORDER BY chunk_index`。
- 不维护 `prev_id` / `next_id` / `sibling_ids` 数组。

可选：`metadata` JSON 写入 `level` / `table` / `faq`（今日 API 现算的 `chunk_meta`）；非 V1 阻塞项。

---

## 5. 索引行为（拟）

沿用现有两段式切块，显式落两层：

```text
Markdown
  → ① 按标题得到 section（= Parent 候选）
  → ② section 内 size+overlap → Children
  → 写入 parent 行（无 embed 或跳过检索索引）
  → 写入 child 行（embed + ES），parent_id = parent.id
```

规则：

- section 长度 ≤ `chunk_size` 且不再切分：可只写一行，`role=child` 且 `parent_id` 自指或 null（实现时二选一写清），避免无意义空父。
- 表格保护 / FAQ 绑定逻辑保持；超大表格整段作 parent 的策略与现 `split_markdown` 一致。
- 增量索引：对齐键需扩展为含 `role` / parent 结构，避免只比 child 正文导致父行漂移。

---

## 6. 检索与组装（拟）

1. `search_chunks` 前半与现网一致，但候选仅 child。
2. Rerank + 门槛之后：
   - **默认**：`content = parent.content`（若有 `parent_id`）；`original_content =` 命中 child 原文；`chunk_id` 仍为命中 child；`score` 不变。
   - 无 parent（旧数据 / 无标题）：降级为 V0 同 heading 扩窗或保持单 child。
3. 同 parent 多 child 命中：按 `score` 去重，只组装一次 parent。
4. Parent 全文超过预算时：允许对 parent 做**按完整子块**回退拼接（复用 V0 center-out + 字符预算），仍禁止对字符串中途切断。

`SearchHit` 可继续用 V0 字段；不强制加 `parent_id` 到对外 API（需要时可后续加）。

---

## 7. 产品与配置

建议配置两维（可与导入页后续接入）：

| 维度 | 选项（示例） | 说明 |
| --- | --- | --- |
| 切片方式（child） | fixed / paragraph / recursive / semantic | 与现占位对齐；后端未接前仍走默认 |
| 上下文组装 | child_only / parent | V1 开启 parent；V0 等价于「heading 扩窗」过渡 |

**不要**把「父子」单独塞进切片方式四个 radio 并列成第五项（易误解为不再按 size 切 child）。

---

## 8. 适用文档类型

| 类型 | V1 价值 |
| --- | --- |
| Markdown / 带小标题网页 / 笔记 | 高（标题 section 作 parent） |
| 结构化 PDF/Word（标题可解析） | 中高 |
| 无标题纯 TXT | 低（降级 child_only 或 V0） |
| 表格 / FAQ 主导 | 保护整单元；父子收益视结构而定 |

---

## 9. 验收标准（立项后）

1. 新导入 Markdown：库中可见 parent + 多个 child，`child.parent_id` 正确。
2. 检索 SQL / ES 不含 parent 行（或 parent 无有效检索向量）。
3. 命中 child → 返回 `content` 为对应 parent 全文（或预算内回退拼接）；引用 `chunk_id` 仍为 child。
4. 同父多命中去重，prompt 中 parent 只出现一次。
5. 未 reindex 的旧文档行为明确（降级策略有测例）。
6. Chat / Agent / 搜索路径无需感知表结构，仍只消费 `SearchHit`。

---

## 10. 里程碑建议

1. 先交付并观察 V0（[`PRD_Chunk_V0.md`](PRD_Chunk_V0.md)）。
2. 用检索调试 / 回答质量（忠实度、完整性）对比扩窗前后。
3. 确认收益与痛点（无标题、超长节、拼装成本）后再开 V1 迁移与 reindex。

---

## 11. 文档与实现落点（立项时）

| 项 | 说明 |
| --- | --- |
| 模型 / 迁移 | `models.py` + Alembic |
| 切块 / 索引 | `ingest/chunk.py`、`ingest/index.py` |
| 检索 | `rag/search.py`（可保留 V0 为降级） |
| 技术说明 | 更新 [`TECH.md`](TECH.md) |
| 主 PRD | [`PRD.md`](PRD.md) §3.2 |
