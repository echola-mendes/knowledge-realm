# AGENTS.md

本仓库是 **知域**：个人本机知识库 Web

## 技术硬约束（不要自行改栈）

- 后端 FastAPI；前端 Vue 3 + TypeScript + Vite。
- 编排：**P0** LangChain 单链，禁止把 `/api/chat` 改成 LangGraph。**P1 Agent** 允许 LangGraph，且必须通过 Tool 调用现有
  pgvector 检索。摘要/自动标签/文档对比只用 Chain。禁止 LlamaIndex、MinerU。
- 向量：本机 PostgreSQL + pgvector；**一张** `document_chunk` 表；余弦相似度。不要再建模一套向量集合。
- LLM / Embedding：DashScope 兼容接口。PyPI 包 `openai` / `langchain-openai` 只是客户端，**不需要 OpenAI 账号**；Key 用
  DashScope。
- 解析：pymupdf、python-docx、trafilatura（公开 URL）。无 OCR。
- 任务：BackgroundTasks。无 Redis/Celery。应用本身无 Docker；**P2 允许本机 Elasticsearch（或仅跑 ES 的 Docker）做 BM25**。
- 绑定本机 `127.0.0.1`。基础 Session 登录；身份只来自 Session，禁止用请求参数指定 `user_id`。不做 RBAC/OAuth/JWT。

## 范围

## 文档维护

## 重要提示

- 架构及文件变动情写入TECH.md
- 子需求整理更新至PRD.md
- 前端页面修改的样式、字体、风格都需要参照style.md
