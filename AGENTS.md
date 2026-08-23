# AGENTS.md

本仓库是 **知域**：个人本机知识库 Web（V1 = P0：导入、标签、收藏、向量余弦检索、LangChain RAG 问答）。

长期事实以 `memory-bank/` 为准，不以闲聊记忆为准。`PRD.md` 仍保留；实现细节以 `memory-bank/design-document.md` 为准。

## 写代码前

1. 读完 `memory-bank/architecture.md`（若几乎为空，再读设计文档里的数据流）。  
2. 读完 `memory-bank/design-document.md`。  
3. 读 `memory-bank/tech-stack.md`。  
4. 若已有 `memory-bank/implementation-plan.md` 与 `memory-bank/progress.md`：只做当前未验证的那一步，不要跳步。

## 技术硬约束（不要自行改栈）

- 后端 FastAPI；前端 Vue 3 + TypeScript + Vite。  
- 编排 **LangChain 单链**。禁止 LangGraph、LlamaIndex、MinerU。  
- 向量：本机 PostgreSQL + pgvector；**一张** `document_chunk` 表；余弦相似度。不要再建模一套向量集合。  
- LLM / Embedding：DashScope 兼容接口。PyPI 包 `openai` / `langchain-openai` 只是客户端，**不需要 OpenAI 账号**；Key 用 DashScope。  
- 解析：pymupdf、python-docx、trafilatura（公开 URL）。无 OCR。  
- 任务：BackgroundTasks。无 Redis/Celery/Docker（本期）。  
- 无登录；绑定本机。

## 范围

只做设计文档 V1/P0。不要做 Agent、图谱、智能摘要、自动标签、全文检索方案 B，除非提出人改设计文档。

## 文档维护

- 里程碑完成后更新 `memory-bank/architecture.md`（真实文件路径与职责）。  
- 每完成并经用户确认的计划步骤，追加 `memory-bank/progress.md`。  
- 改需求先改 `design-document.md`（及必要时 `PRD.md`），再改代码。

## 重要提示

- 写任何代码前必须完整阅读 memory-bank/@architecture.md
- 写任何代码前必须完整阅读 memory-bank/@design-document.md
- 每完成一个重大功能或里程碑后，必须更新 memory-bank/@architecture.md
