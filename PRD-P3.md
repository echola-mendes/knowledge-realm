# P3（第一批）——知识智能化、版本与更新、可观测收尾

**状态：** P3 第一批已批准开始（提出人 2026-08-30）。  
**基线：** P0 / P1.1–P1.4 / P2 已收口；调试页已有 Agent Trace、Hybrid Search 评估、Pipeline 节点耗时（`timings`）。

## 1. 版本目标

第一批解决三类问题：

1. **知识运营**：让库"自己说话"——冲突检测、缺口分析、自动整理（报告型，选库跑一次出报告）
2. **知识保鲜**：版本管理（元数据）、增量更新、URL 文档自动更新
3. **可观测收尾**：Token 统计（替换占位符）、RAG Answer Quality 评估

**不做的**（本批明确排除）：去重增强（跨库/近似/管理界面）、Metadata 增强（自定义字段/元数据筛选）、Multi-Agent、Agent 执行效果评分、`search_graph` 与力导向可视化、复杂知识图谱推理。

---

## 2. 统一约束

- 冲突检测 / 缺口分析 / 自动整理 / 答案质量评估只用 **LangChain**（同摘要/自动标签/文档对比先例），**不进 Agent 图**、不新增 Graph 节点
- 报告型功能（冲突/缺口/整理）**不落库**：跑一次出一次，前端展示，可重复跑
- 分析输入用文档**摘要**而非全文；库内文档 >30 篇时截断并在报告注明
- 增量更新只在**一张** `document_chunk` 表内做差量，不建第二套向量集合
- 无定时任务框架（仍 BackgroundTasks）；「自动更新」靠页面入口触发
- 身份只来自 Session；所有新端点走 `current_user` + 库归属校验

---

## 3. 知识洞察（冲突检测 / 缺口分析 / 自动整理）

前端：新增 `/insights` 路由 + 侧栏「知识洞察」入口。页面结构：知识库选择器 + 三个操作区 + 报告卡片；样式按 `web/style.md`。

### 3.1 知识冲突检测

- 输入：库内文档清单（filename + summary，≤30 篇）
- Chain 输出 JSON：`conflicts: [{documents: [name...], point, detail, suggestion}]`
- 报告含义：不同文档对同一事实表述矛盾（如退款周期 7 天 vs 15 天）；**只出报告，不自动改数据**

### 3.2 知识缺口分析

- 输入：同上文档清单 + `retrieval_label` 中 relevance ≤1 的 `query_norm`（作为低命中佐证，无则省略）
- Chain 输出 JSON：`covered_topics: []`、`gaps: [{topic, evidence, suggestion}]`

### 3.3 自动知识整理

- 行为两部分：
  - **自动补标签**（直接应用）：对无标签文档复用 P1 自动标签 Chain 打标签（上限每篇 3 个、必须已有标签体系内或新建，沿用 P1 规则）
  - **整理报告**（只建议不执行）：疑似重复（同名/同 checksum 跨库提示）、空摘要、命名不规范
- 端点支持 `apply_tags: bool = true`；返回 `{applied: [...], report: {...}}`

---

## 4. 版本与更新

### 4.1 知识版本管理（元数据级）

- `document.version` INT 默认 1；新表 `document_version(id, document_id FK CASCADE, version, checksum, byte_size, created_at)`，UNIQUE(document_id, version)
- **内容变更**（新 checksum ≠ 旧 checksum）→ version+1 并写版本行；同 checksum 不变
- **不存**历史正文快照，**不可回滚**；旧版本记录仅元数据
- API：`GET /documents/{id}/versions`；`DocumentOut.version`
- UI：文档列表「版本」列显示 vN；版本历史在阅读页/切片页入口查看

### 4.2 增量更新

- 内容变更重新索引时做 chunk 差量：新旧切片按 `(heading, content)` 对齐——未变更的**复用现有 embedding**，只重嵌变更/新增，删除多余的
- 全新文档 / 手动全量 reindex 行为不变

### 4.3 知识库自动更新（URL）

- `POST /documents/{id}/refresh`：仅 `kind=url`；重新 trafilatura 抓取 → checksum 对比 → 未变更返回"已是最新"；变更走 §4.2 增量 + §4.1 版本+1
- `POST /knowledge-bases/{id}/refresh-urls`：批量刷新库内全部 url 文档（BackgroundTasks 逐个）
- UI：文档列表 url 行操作列「更新」；无定时轮询，靠入口触发

---

## 5. 主动知识推荐

- `GET /api/recommendations`：聚合来源 = 用户收藏文档 + 最近提问（Agent/Chat）命中的 citations 文档 → 经 `search_chunks`/related 扩展相似文档 → 去重、排除已收藏/已引用本体 → 取 5
- 无数据时返回空数组，前端显示空态文案
- UI：首页（HomeView）「推荐阅读」卡片区，点击进阅读页

---

## 6. 可观测收尾

### 6.1 Token 统计

- `llm.py chat()` 透出 usage（prompt/completion/total tokens），调用方可选接收；`/api/chat` 主链行为不变
- Embedding 记录批量 token 用量（日志级；导入完成可在 error_message 之外记消耗，不新增产品 UI）
- Agent Trace SSE：`step`（reason/generate）与 `final` 事件带 token 字段；调试页「总 Token」卡片显示真实值

### 6.2 RAG Answer Quality 评估

- `POST /api/retrieval-debug/answer-quality`：入参 `query, answer, contexts[]`；LLM-as-judge Chain 输出 `faithfulness / relevance / completeness`（1–5）+ `issues[]`
- 调试页：trace 完成后可点「评估回答」，展示三维分数与问题列表；属于调试能力，不进生产问答链

---

## 7. P3 第一批范围汇总

- 知识洞察：冲突检测、缺口分析、自动整理（/insights 页）
- 版本与更新：版本管理（元数据）、增量更新、URL 自动更新
- 主动推荐：首页推荐卡片
- 可观测：Token 统计、RAG Answer Quality 评估

**暂不实现**：去重增强、Metadata 增强、Multi-Agent、Agent 执行效果评分、`search_graph` / 力导向可视化、复杂图谱推理、知识库定时轮询。

---

## 8. 验收标准

- [ ] /insights 页可选库跑冲突/缺口/整理；报告含文档名定位；>30 篇截断有提示
- [ ] 整理的自动补标签真实写入 `document_tag`，报告项不自动执行
- [ ] 同文档内容变更 → `document.version` 递增且 `document_version` 新增一行；同 checksum 不递增
- [ ] 增量更新后未变更切片的 embedding 未重新计算（可用调用计数/耗时验证）
- [ ] url 文档 refresh：未变更提示最新；变更后版本+1、切片差量更新
- [ ] `GET /api/recommendations` 返回 ≤5 条、不含已收藏本体；首页展示，空态友好
- [ ] Agent Trace 事件含 token 字段，调试页「总 Token」显示真实值；`/api/chat` 响应结构不变
- [ ] 答案质量端点返回三维分数与 issues；调试页可触发
- [ ] 全部新端点未登录 401、跨用户 404；`test_p1_graph` 等既有测试不回归
