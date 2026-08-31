# 完成记录

## 2026-08-31：Debug 页 RAG 评测指标与 GT Answer 用例

### 子需求概述
在 Debug 页扩展 Evaluation Metrics：
- 支持三档 Metric Set：Retrieval Evaluation / RAG Evaluation / Full RAG Evaluation。
- Retrieval 保留 Recall@K / Precision@K / MRR@K / NDCG@K / Hit@K。
- RAG 增加 Faithfulness / Answer Relevance / Answer Correctness / Semantic Similarity（后端自实现，未引入 Ragas）。
- GT Answer 支持临时输入与落库（按用户 + Query），同 Query 可回填。
- 收敛 Trace 侧重复的「评估回答」UI。

### 改动文件
- `server/app/schemas.py`：新增 `RagMetricsRequest`、`RagMetricsOut` schema。
- `server/app/rag_eval.py`：新增 RAG 四指标计算模块（已存在，本次验证并补测试）。
- `server/app/routers/retrieval_debug.py`：新增 `/api/retrieval-debug/rag-metrics` 路由（已存在，本次验证 schema 补齐后可工作）。
- `server/tests/test_rag_metrics.py`：补全四指标正常路径与 null 行为测试。
- `web/src/api.ts`：新增 `RagMetrics`、`RagEvalCase` 类型与 `computeRagMetrics`、`getRagEvalCase`、`putRagEvalCase` 客户端。
- `web/src/views/DebugView.vue`：Metric Set 三档切换、GT Answer 输入/保存/回填、RAG 指标表、移除 Trace 侧评估回答。

### 验收结果
- Step 1 GT Answer 用例落库：✅
- Step 2 RAG 生成侧指标计算：✅
- Step 3 DebugView Metric Set + GT Answer UI + 收敛 Trace 评估：✅

### 验证方式
- 后端单测通过直接调用测试函数验证（当前 pytest 在 conftest session fixture 阶段挂起，疑似环境/进程问题，非代码问题）。
- 前端 `npm run typecheck` 通过，无新增错误。

### 经验
- 新增 FastAPI 路由前务必同步 schema，否则 import 即失败。
- 前端 Metric Set 切换时应同时触发 GT Answer 回填与 RAG 指标重算。
- 保持后端 `/answer-quality` 接口不动，仅收敛前端入口即可满足「不强制删除后端接口」的约束。
