# 当前子需求

## 1. 目标

在 Debug 页 Evaluation Metrics 中扩展 Metric Set：在现有 Retrieval Evaluation 之外增加 RAG Evaluation（生成侧指标），并支持 Full RAG Evaluation；切换 Metric Set 时同步更新指标表、说明文案与所需 Ground Truth。

## 2. 背景

- 现有：`DebugView` 客户端计算 Recall@K / Precision@K / MRR@K / NDCG@K / Hit@K；Metric Set 下拉仅为静态「Default Metric Set」。
- 现有：Agent Trace 有独立「评估回答」→ `/api/retrieval-debug/answer-quality`（LLM judge 1–5），与 Metrics 表重复；**确认收敛：去掉 Trace 侧重复评估 UI，只保留 Metrics 表指标**。
- 现有 Ground Truth：切片级 `retrieval_label`（≥2 相关）；无 Ground Truth Answer。

## 3. 功能范围

1. Metric Set 下拉三档：Retrieval Evaluation / RAG Evaluation / Full RAG Evaluation。
2. 各档指标：
   - Retrieval：Recall@K、Precision@K、MRR@K、NDCG@K、Hit@K
   - RAG：Faithfulness、Answer Relevance、Answer Correctness、Semantic Similarity
   - Full：Retrieval ∪ RAG
3. 切换 Metric Set 时同步：指标说明、所需 GT 提示、表格内容与列结构（RAG 侧无 @K 列）。
4. 实现四项生成侧指标（见业务规则）；数据源为 Agent Trace 最终回复 + citations。
5. GT Answer：默认临时输入用于本次评测；用户点击「保存为评测用例」后才按「用户 + Trace Query」落库；加载已有用例时可回填。
6. 收敛 Trace「评估回答」三 pill / 按钮，避免与 Metrics 重复。
7. 不引入 LlamaIndex / Ragas 强依赖；不改 `/api/chat` 为 LangGraph。

## 4. 非目标

- 不引入 Ragas 作为强依赖（借鉴算法，自实现 + DashScope LLM/Embedding）
- 不做批量离线评测跑批、不做评测**结果分数**历史归档（仅 GT Answer 用例可落库）
- 不改检索管线本身
- 不强制删除后端 `/answer-quality` 接口（可保留；前端不再作为主入口）

## 5. 业务规则

| 指标 | 含义 | 需要切片 GT | 需要 GT Answer | 需要 Trace Answer (+ Context) |
|---|---|---|---|---|
| Recall/Precision/MRR/NDCG/Hit@K | 检索排序质量 | 是（≥2 相关） | 否 | 否 |
| Faithfulness | 答案事实能否被 context 支撑；Ragas 式 0–1（拆陈述→逐条支撑→比例） | 否 | 否 | 是（答案+context） |
| Answer Relevance | 答案是否回答问题；答案反向生成若干问题，再与原 Question 语义相似 | 否 | 否 | 是（答案） |
| Answer Correctness | 事实对比 + 语义相似（相对 GT Answer） | 否 | 是 | 是（答案） |
| Semantic Similarity | Actual Answer vs GT Answer 语义相似度 | 否 | 是 | 是（答案） |

- Full RAG Evaluation = Retrieval ∪ RAG（已确认）。
- GT Answer：未点「保存为评测用例」则仅内存/本次评测使用，不落库。

## 6. 输入与输出

**输入：** Trace Query、Trace 最终 Answer、citations 作 Context、切片 GT（检索指标）、GT Answer（临时或已保存用例）。

**输出：** Metrics 表对应分值；缺前置数据时「—」并提示缺什么。

## 7. 涉及模块

- `web/src/views/DebugView.vue`：Metric Set、说明、GT Answer 临时输入/保存、收敛 Trace 评估 UI、指标表
- `web/src/api.ts`：RAG 评测 API、GT Answer 用例读写
- `server/app/routers/retrieval_debug.py`（或邻近模块）：评测计算、GT Answer 持久化
- 复用现有 DashScope LLM / Embedding；可新建轻量评测模块，不强制改 `quality.py` 语义

## 8. 验收标准

1. 三档 Metric Set 可切换；默认 Retrieval Evaluation
2. Retrieval / RAG / Full 展示指标与说明、GT 需求提示正确
3. Faithfulness 为 Ragas 式 0–1；Answer Relevance 为「答案→反向问题→相似度」；Correctness 为事实对比+语义相似
4. 无 Trace Answer 时相关 RAG 指标为「—」；无 GT Answer 时 Correctness / Similarity 为「—」
5. GT Answer 默认可输入并参与本次评测；仅点「保存为评测用例」后落库；同用户+同 Query 可回填
6. Trace 区不再展示与 Metrics 重复的「评估回答」三 pill 主流程
7. 样式遵循现有 Debug 页与 `style.md`

## 9. 待确认问题

（确认①已全部拍板，无未决项。）
