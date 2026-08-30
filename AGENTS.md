# AGENTS.md

本仓库是 **知域**：个人本机知识库 Web。**P0 / P1.1–P1.4 / P2 已完成**。**P3 第一批进行中**：范围 `PRD-P3.md`，实施见 `implementation-plan.md` 的 P3 段（冲突检测/缺口分析/自动整理、版本管理/增量更新/URL 自动更新、主动推荐、Token 统计、RAG 答案质量评估）。不要开始 `search_graph` Tool，不要开始力导向/ vis.js / D3 可视化；不要做去重增强、Metadata 增强、Multi-Agent（本批明确排除）；新阶段须先改计划。

长期事实以 `memory-bank/` 为准，不以闲聊记忆为准。`PRD.md` 仍保留；实现细节以 `memory-bank/design-document.md` 为准。

## 技术硬约束（不要自行改栈）

- 后端 FastAPI；前端 Vue 3 + TypeScript + Vite。  
- 编排：**P0** LangChain 单链，禁止把 `/api/chat` 改成 LangGraph。**P1 Agent** 允许 LangGraph，且必须通过 Tool 调用现有 pgvector 检索。摘要/自动标签/文档对比只用 Chain。禁止 LlamaIndex、MinerU。  
- 向量：本机 PostgreSQL + pgvector；**一张** `document_chunk` 表；余弦相似度。不要再建模一套向量集合。  
- LLM / Embedding：DashScope 兼容接口。PyPI 包 `openai` / `langchain-openai` 只是客户端，**不需要 OpenAI 账号**；Key 用 DashScope。  
- 解析：pymupdf、python-docx、trafilatura（公开 URL）。无 OCR。  
- 任务：BackgroundTasks。无 Redis/Celery。应用本身无 Docker；**P2 允许本机 Elasticsearch（或仅跑 ES 的 Docker）做 BM25**。  
- 绑定本机 `127.0.0.1`。基础 Session 登录；身份只来自 Session，禁止用请求参数指定 `user_id`。不做 RBAC/OAuth/JWT。

## 范围

只做当前计划步骤。P0 / P1.1–P1.4 / P2（PRD-P2 §7）已收口。**P3 第一批已批准（2026-08-30），范围 `PRD-P3.md`，当前步骤见 `implementation-plan.md` P3 段「当前」。** 未在 `implementation-plan.md` 列出的功能不要做。改需求先改 `design-document.md`（及 `PRD.md` / `PRD-P2.md` / `PRD-P3.md`）。

## 文档维护

- 里程碑完成后更新 `memory-bank/architecture.md`（真实文件路径与职责）。  
- 每完成并经用户确认的计划步骤，追加 `memory-bank/progress.md`。  
- 改需求先改 `design-document.md`（及必要时 `PRD.md` / `PRD-P2.md` / `PRD-P3.md`），再改代码。P2 Agent：Checkpoint 不是记忆；`reason` 统一路由，见设计文档第 4.7 节。P3：洞察报告不落库；增量更新单表差量；见设计文档 §4.8–4.10。

## 重要提示

- 每完成一个重大功能或里程碑后，必须更新 memory-bank/@architecture.md
