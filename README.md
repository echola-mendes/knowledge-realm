# 知域

个人本机知识库：导入文档、向量检索、RAG 问答。

代码仓库名：`knowledge_realm`  
远程：https://gitee.com/echola/knowledge

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic
- 数据库：PostgreSQL + pgvector，库名 `echola_kb`
- 解析：PyMuPDF、python-docx、Markdown / 纯文本
- 切块：LangChain
- LLM / Embedding：阿里云 DashScope 兼容接口
- 前端：Vue 3 + TypeScript + Vite（`web/`）

## 运行

本机 PostgreSQL 创建库并启用扩展：

```sql
CREATE DATABASE echola_kb;
\c echola_kb
CREATE EXTENSION IF NOT EXISTS vector;
```

```bash
cp .env.example .env
```

填写 `DATABASE_URL`（格式 `postgresql+psycopg://用户名:密码@127.0.0.1:5432/echola_kb`）和百炼 API Key：https://bailian.console.aliyun.com/

```bash
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

健康检查：`GET http://127.0.0.1:8000/health`

前端（开发，`/api` 代理到 8000）：

```bash
cd web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`

```bash
cd server
pytest -q
```

`.env` 不要提交到 git。默认 Embedding 为 `text-embedding-v3`，维数 1024。

## 文档

| 文件 | 内容 |
|---|---|
| `PRD.md` | 产品需求（V1 = P0） |
| `memory-bank/design-document.md` | 实现规格 |
| `memory-bank/tech-stack.md` | 选型 |
| `memory-bank/implementation-plan.md` | 分步计划 |
| `memory-bank/architecture.md` | 代码路径 |
| `AGENTS.md` | 给实现用的硬约束 |
