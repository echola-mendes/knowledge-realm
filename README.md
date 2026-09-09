# 知域

个人知识库 Web：沉淀资料、语义检索、RAG 问答，并支持 Agent 研究、出行规划与 AI 资讯。

代码仓库名：`knowledge_realm`  
身份只来自 Session，数据按用户隔离。

## 快速部署（Docker，推荐）

**前提**：已安装 [Docker](https://docs.docker.com/get-docker/) 与 Docker Compose。

```bash
git clone git@github.com:echola-mendes/knowledge_realm.git
cd knowledge_realm
cp .env.docker.example .env
# 编辑 .env：填写 LLM_API_KEY、SESSION_SECRET（≥32 字符）、INITIAL_PASSWORD
./scripts/deploy.sh
```

浏览器打开 `http://localhost:8080`（端口可在 `.env` 的 `HTTP_PORT` 修改）。

```bash
docker compose logs -f api worker   # 日志
docker compose down                 # 停止
docker compose up -d --build        # 更新后重建
```

Compose 拉起 Postgres（pgvector）+ Redis + API + Worker + Nginx；数据库迁移在 API 启动时自动执行。

## 功能概览

| 模块 | 能力 |
|---|---|
| 知识库与文档 | 多知识库；PDF / Word / Markdown / TXT / URL / 手写笔记；处理状态、收藏、标签、重新处理 |
| 检索 | 向量语义搜索；可选混合检索（BM25 + 重排）；按库 / 标签 / 类型筛选 |
| AI 问答 | RAG 流式回答与来源引用；多轮对话 |
| 知识增强 | 自动摘要与标签；实体关系；相关文档；多文档对比 |
| Agent | Chat（单链 RAG）/ 知识 Agent / Multi Agent / 研究报告；工具调用与会话记忆 |
| 出行 | Multi Agent 内行程规划与预订（HITL）；工具页「我的行程单」 |
| AI 资讯 | 今日热榜与详情；定时任务刷新 RSS 排行 |
| 知识洞察 | 冲突检测、缺口分析、自动整理（报告型） |
| 版本与刷新 | 文档版本；URL 手动 / 批量刷新与增量索引 |
| 其它 | 首页推荐；侧栏菜单管理；调试页（检索 / Agent 轨迹 / Token）；监控占位（决策审计 / 操作审计） |

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic；P0 Chat 用 LangChain 单链；Agent 用 LangGraph
- 数据库：PostgreSQL + pgvector（库名 `knowledge`），一张 `document_chunk` 表
- 解析：PyMuPDF、python-docx、trafilatura（公开 URL）；无 OCR
- LLM / Embedding：阿里云 DashScope 兼容接口（`openai` / `langchain-openai` 仅作客户端）
- 任务：短任务 BackgroundTasks；定时任务 APScheduler + Redis + arq Worker
- 可选：Elasticsearch（BM25）；MinIO（行程方案页）
- 前端：Vue 3 + TypeScript + Vite（`web/`）
- 部署：Docker Compose（推荐）或本机 venv + npm

## 本机开发（不用 Docker）

### 1. 数据库

本机 PostgreSQL 建库并启用扩展：

```sql
CREATE DATABASE knowledge;
\c knowledge
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. 环境变量

```bash
cp .env.example .env
```

必填：`DATABASE_URL`（`postgresql+psycopg://用户名:密码@127.0.0.1:5432/knowledge`）、DashScope API Key（[百炼控制台](https://bailian.console.aliyun.com/)）、`SESSION_SECRET`、`INITIAL_PASSWORD`。

定时任务还需本机 Redis（默认 `REDIS_URL=redis://127.0.0.1:6379/0`）。混合检索可选配 `ELASTICSEARCH_URL`；行程方案上传可选配 MinIO。

### 3. 后端

```bash
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

健康检查：`GET http://127.0.0.1:8000/health`

定时任务 Worker（独立进程，消费资讯刷新等）：

```bash
cd server
source .venv/bin/activate
python -m app.worker.worker
```

### 4. 前端

```bash
cd web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`（开发时 `/api` 代理到 8000）。

### 5. 测试

```bash
cd server
pytest -q
```

`.env` 不要提交。默认 Embedding：`text-embedding-v3`，维数 1024。

## 文档

| 文件 | 内容 |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | 产品需求（已实现与规划） |
| [`docs/TECH.md`](docs/TECH.md) | 技术栈与实现说明 |
| [`AGENTS.md`](AGENTS.md) | 给实现用的硬约束 |
| [`docs/PRD-NEWS.md`](docs/PRD-NEWS.md) | AI 资讯 |
| [`docs/PRD-Job.md`](docs/PRD-Job.md) | 定时任务 |
| [`docs/Trace.md`](docs/Trace.md) | 决策审计（规划 / 进行中） |
| [`web/style.md`](web/style.md) | 前端样式规范 |
