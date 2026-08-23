# 知域

个人本机知识库：导入文档、向量检索、RAG 问答。仓库：[gitee.com/echola/knowledge](https://gitee.com/echola/knowledge)

V1 只做 PRD **P0**。规格以 `memory-bank/design-document.md` 为准，进度见 `memory-bank/progress.md`。

## 当前进度

后端已做到 **步骤 11**（解析 → 切块 → Embedding 入库，文档状态 `ready`）。下一步是重新处理 / 删除文档，以及 Vue 前端（尚未写应用代码）。

已有：知识库 CRUD、默认知识库、上传 pdf/docx/md/txt、解析、切块、索引。  
未做：笔记/URL 导入、搜索与问答 API、标签收藏、Web UI。

## 技术栈

- 后端：FastAPI + SQLAlchemy + Alembic，任务用 BackgroundTasks  
- 库：本机 PostgreSQL + pgvector（**不要 Docker 再起一套库**），库名 `echola_kb`  
- 解析：PyMuPDF、python-docx、直读 md/txt；无 OCR、无 MinerU  
- 切块：LangChain（禁止用 LangGraph / LlamaIndex）  
- LLM / Embedding：DashScope 兼容接口，PyPI `openai` 只当客户端，**不需要 OpenAI 账号**  
- 前端（计划）：Vue 3 + TypeScript + Vite，目录 `web/`  
- 无登录，监听本机回环

## 本机准备

1. PostgreSQL 已运行，创建库并启用扩展：

```sql
CREATE DATABASE echola_kb;
\c echola_kb
CREATE EXTENSION IF NOT EXISTS vector;
```

2. 复制环境变量（**不要提交 `.env`**）：

```bash
cp .env.example .env
```

`DATABASE_URL` 必须是 `用户名:密码`，例如：

`postgresql+psycopg://postgres:你的密码@127.0.0.1:5432/echola_kb`

Key 在[阿里云百炼](https://bailian.console.aliyun.com/)申请，填入 `LLM_API_KEY`（Embedding 可共用）。

3. Python 3.12 虚拟环境（不用 conda）：

```bash
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. 迁移并启动：

```bash
cd server
env -u DATABASE_URL .venv/bin/alembic upgrade head
env -u DATABASE_URL .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

健康检查：`GET http://127.0.0.1:8000/health`

测试：

```bash
cd server
env -u DATABASE_URL .venv/bin/pytest -q
```

langchain 1.x 可能顺带安装 langgraph 包，**应用禁止 import / 使用**。

## Embedding

默认 `EMBEDDING_MODEL=text-embedding-v3`，维数 `1024`。走云端 DashScope，不用本机 Embedding 权重。

额度用尽或 v3 不可用时：**不要指望自动换模**。把 `.env` 改为 `text-embedding-v4` 后重启；同维再对文档重新索引。改 `EMBEDDING_DIM` 必须重建向量列并全量 reindex。

## 文档

| 文件 | 内容 |
|---|---|
| `PRD.md` | 产品需求（V1 = P0） |
| `memory-bank/design-document.md` | 实现规格 |
| `memory-bank/tech-stack.md` | 选型 |
| `memory-bank/implementation-plan.md` | 分步计划 |
| `memory-bank/architecture.md` | 代码路径 |
| `AGENTS.md` | 给实现用的硬约束 |

改需求先改设计文档，再改代码。
