# AGENTS.md

本仓库是 **知域**：个人本机知识库 Web。**P0 / P1.1–P1.4 已完成**。P2 范围 `PRD-P2.md`，实施见 `implementation-plan.md` 文末 P2 步骤。不要开始 `search_graph` Tool，不要开始力导向/ vis.js / D3 可视化；新阶段须先改计划。

长期事实以 `memory-bank/` 为准，不以闲聊记忆为准。`PRD.md` 仍保留；实现细节以 `memory-bank/design-document.md` 为准。

## 写代码前

1. 读完 `memory-bank/architecture.md`（若几乎为空，再读设计文档里的数据流）。  
2. 读完 `memory-bank/design-document.md`。  
3. 读 `memory-bank/tech-stack.md`。  
4. 若已有 `memory-bank/implementation-plan.md` 与 `memory-bank/progress.md`：只做当前未验证的那一步，不要跳步。

## 技术硬约束（不要自行改栈）

- 后端 FastAPI；前端 Vue 3 + TypeScript + Vite。  
- 编排：**P0** LangChain 单链，禁止把 `/api/chat` 改成 LangGraph。**P1 Agent** 允许 LangGraph，且必须通过 Tool 调用现有 pgvector 检索。摘要/自动标签/文档对比只用 Chain。禁止 LlamaIndex、MinerU。  
- 向量：本机 PostgreSQL + pgvector；**一张** `document_chunk` 表；余弦相似度。不要再建模一套向量集合。  
- LLM / Embedding：DashScope 兼容接口。PyPI 包 `openai` / `langchain-openai` 只是客户端，**不需要 OpenAI 账号**；Key 用 DashScope。  
- 解析：pymupdf、python-docx、trafilatura（公开 URL）。无 OCR。  
- 任务：BackgroundTasks。无 Redis/Celery。应用本身无 Docker；**P2 允许本机 Elasticsearch（或仅跑 ES 的 Docker）做 BM25**。  
- 无登录；绑定本机。

## 范围

只做当前计划步骤。P0 / P1.1–P1.4 已收口。**P2-RAG-3 代码已写，待提出人确认阈值与验收。** 未在 `implementation-plan.md` 列出的功能不要做。改需求先改 `design-document.md`（及 `PRD.md` / `PRD-P2.md`）。

## 文档维护

- 里程碑完成后更新 `memory-bank/architecture.md`（真实文件路径与职责）。  
- 每完成并经用户确认的计划步骤，追加 `memory-bank/progress.md`。  
- 改需求先改 `design-document.md`（及必要时 `PRD.md` / `PRD-P2.md`），再改代码。P2 Agent：Checkpoint 不是记忆；`reason` 统一路由，见设计文档第 4.7 节。

## 重要提示

- 写任何代码前必须完整阅读 memory-bank/@architecture.md
- 写任何代码前必须完整阅读 memory-bank/@design-document.md
- 每完成一个重大功能或里程碑后，必须更新 memory-bank/@architecture.md
