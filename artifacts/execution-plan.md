# Execution Plan

## Step 1：GT Answer 评测用例落库

### 目标
支持按「用户 + Trace Query」读写 Ground Truth Answer；未点保存不写库。

### 方案
- 新增表/模型（建议 `rag_eval_case`）：`user_id`、`query_norm`、`gt_answer`、可选 `knowledge_base_id`、时间戳；唯一约束 `(user_id, query_norm[, kb])`，模式对齐 `RetrievalLabel`。
- schemas：Put / Out；router：`GET/PUT /api/retrieval-debug/eval-cases`（或同前缀邻近路径）；`query_norm` 复用现有规范化逻辑。
- 身份仅 Session；不接受请求参数 `user_id`。
- `create_all` / 现有启动建表路径自动纳入新模型。

### 验收
- [✅] 单测：登录用户 PUT 后 GET 同 query 回填；另一用户不可读
- [✅] 单测：未 PUT 时 GET 为空/404 约定明确且前端可处理

---

## Step 2：RAG 生成侧指标计算（后端）

### 目标
实现 Faithfulness / Answer Relevance / Answer Correctness / Semantic Similarity（0–1），自实现、不引入 Ragas 包。

### 方案
- 新模块（建议 `server/app/rag_eval.py`），复用 DashScope：`llm`（ChatOpenAI）+ `embed_texts`。
- **Faithfulness**：答案拆陈述 → 逐条相对 contexts 判支撑 → `supported/total`；无陈述则约定分值（如 1.0 或 —，实现时固定并测）。
- **Answer Relevance**：由答案反向生成 N 个问题 → 与原 Question 做 embedding 余弦均值。
- **Semantic Similarity**：Actual Answer 与 GT Answer embedding 余弦。
- **Answer Correctness**：事实对比（相对 GT 的 TP/FP/FN 或等价 LLM 结构化判定）与语义相似加权合成 0–1。
- API：`POST /api/retrieval-debug/rag-metrics`，入参 `query, answer, contexts, gt_answer?`；缺 gt 时 correctness/similarity 为 null；缺 answer/contexts 时对应项 null。
- 保留现有 `/answer-quality` 接口不删（前端不再主用）。

### 验收
- [✅] 单测：mock LLM/embed，覆盖四指标正常路径与缺 gt/缺 context 的 null 行为
- [✅] 单测：Answer Relevance 路径体现「答案→生成问题→相似度」（mock 断言调用顺序/入参形态即可）

---

## Step 3：DebugView Metric Set + GT Answer UI + 收敛 Trace 评估

### 目标
三档 Metric Set 切换同步说明/GT 提示/表格；RAG 指标接 Trace；GT Answer 临时评测与可选保存；去掉 Trace 重复评估 UI。

### 方案
- `DebugView.vue`：
  - Metric Set：`Retrieval Evaluation` | `RAG Evaluation` | `Full RAG Evaluation`（默认 Retrieval）
  - 切换时更新说明文案与所需 GT；Retrieval 保留 @K 表；RAG 单列分值表；Full 两段合显
  - GT Answer 输入框（临时）；「保存为评测用例」调 PUT；切换/加载 Trace Query 时 GET 回填（有则填，无则空，不覆盖用户未保存编辑需有简单策略：有已保存则回填）
  - 「计算 RAG 指标」或随 Trace 完成可评时调用 `rag-metrics`（数据源：`traceFinal.answer` + citations）
  - 移除 Trace「评估回答」按钮与三 pill 展示
- `api.ts`：eval-case 与 rag-metrics 客户端
- 样式沿用 Debug 页现有 class / `style.md`，不做无关美化

### 验收
- [✅] 路径验证：三档切换后表格行与说明文案符合 prd-sub（Retrieval 五指标 / RAG 四指标 / Full 合集）
- [✅] 路径验证：无 Trace Answer 时 RAG 相关为「—」；无 GT Answer 时 Correctness/Similarity 为「—」
- [✅] 路径验证：不点保存则仅前端临时值参与评测；点保存后同 Query 再进可回填
- [✅] 路径验证：Trace 区无「评估回答」三 pill 主流程
- [✅] `api.ts` 类型与后端 schema 字段一致（抽查）
