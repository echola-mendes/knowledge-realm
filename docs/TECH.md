# 知域 — 技术栈

**原则：** 只记录本仓库技术选型与硬约束；产品行为与需求见 `PRD.md` 及子 PRD。

---

## 总览

| 层 | 选型 | 理由 | 不选 |
|---|---|---|---|
| 前端 | Vue 3 + TypeScript + Vite | 设计已定 Web；页面不多，不必上大框架 | React（避免双栈） |
| 后端 | Python 3.11+ / FastAPI / Uvicorn | 上传 + JSON + SSE 足够 | Django |
| RAG 编排 | P0：LangChain 单链。P1 Agent / Research Report：LangGraph，经 Tool 调用 P0 检索 | P0 已定单链；Agent 复用而非替换 RAG | 用图重写 `/api/chat`；LlamaIndex |
| P1 短任务 | LangChain Chain（摘要、自动标签、对比） | 一次 LLM 足够 | 把摘要/标签做成 Graph |
| 向量读写 | SQLAlchemy + SQL 余弦；一张 `document_chunk` | 元数据与向量一体，避免第二套向量表 | langchain 自建 PGVector 集合 |
| 解析 | pymupdf、python-docx、标准库读文本 | 无 OCR | MinerU、Unstructured |
| 网页正文 | httpx + trafilatura | 公开页抽正文 | Playwright |
| 存储 | PostgreSQL + pgvector | 已安装；库名 `knowledge` | Milvus |
| ORM / 迁移 | SQLAlchemy 2 + Alembic | 表演进可重复 | 纯手写 SQL |
| 任务 | BackgroundTasks（短）；APScheduler + Redis + arq（定时） | 调度与执行分离 | Celery、Kafka |
| 关键词检索 | Elasticsearch BM25（P2 Hybrid） | 与 pgvector 同走 `search_chunks` | Meilisearch；用 ES 存 embedding |
| LLM / Embedding | PyPI `openai` 客户端 → **DashScope 兼容模式** | 不需要 OpenAI 账号 | 各家杂 SDK；Ollama |
| 重排 | DashScope/硅基兼容 `/reranks`；无 Key 则 LLM 打分 | 可降级 | — |
| 认证 | FastAPI Session Cookie + Argon2 | 身份只来自 Session | JWT / OAuth / RBAC |
| 对象存储 | MinIO（软依赖，方案/报告 HTML） | 未配置则仅实时展示 | 强制依赖云 OSS |
| 差旅工具 | flyai skill CLI（机票/酒店） | 外置 CLI，stdout JSON | 自建爬虫 |
| 部署 | Docker Compose（推荐）；或本机 `server/.venv` + npm | clone 即跑 | conda；K8s |
| 测试 | pytest + httpx | API 与隔离检索 | 强制 E2E |

目录：前端 `web/`；后端 `server/`。

---

## 前端

- Vue 3 `<script setup>` + TypeScript + Vite；Vue Router；`markdown-it`
- HTTP：`fetch`；SSE 用 `fetch` 读 stream
- 开发：Vite 代理 `/api` → FastAPI（绑 `127.0.0.1`）
- 样式约定：`web/style.md`
- 不做：Pinia 大模块、组件库套装、SSR

---

## 后端

- FastAPI + Pydantic v2 + python-dotenv
- 切块：Markdown 标题切分；长节 parent + children（`role` / `parent_id`）；parent 无 embedding、不进 ES
- P0 问答：`ChatOpenAI` 单链；检索只用当前句
- 检索（`search_chunks`）：pgvector +（可选）ES BM25 → RRF → Rerank → `RELEVANCE_MIN_SCORE`；仅 `role=child` 且有 embedding；门槛后按 `parent_id`（或无 parent 时 `doc+heading`）分组：seeds ∪ 各 seed ±1 去重，非 seed 邻居过双条件（最近 seed 余弦 ≥ `EXPAND_ANCHOR_MIN` 且 query 分 ≥ `EXPAND_QUERY_MIN`）后按 `chunk_index` 拼成 **1** 条 `content`；代表锚点取组内最高分；`SearchHit` 带 `neighbor_chunk_ids` / `expanded_chunk_ids`；不再默认 parent 全文或 V0 center-out；`search_debug` 不组装
- Agent：LangGraph；检索必须经 Tool 调现有 `search.py`，禁止第二套向量查询
- Checkpoint：LangGraph PostgresSaver，同一 `DATABASE_URL`；不作 STM/聊天权威
- URL 导入：`httpx` 超时 20s + `trafilatura`
- 内容哈希：SHA-256
- 定时任务：APScheduler 只入队；`python -m app.worker.worker` 消费 Redis 队列 `zhiyu:tasks`；单 uvicorn，勿开多 worker

默认模型：`qwen-plus`、`text-embedding-v3`、`EMBEDDING_DIM=1024`。同维换模型须 reindex；改维须重建向量列并全量 reindex。

---

## 存储

- PostgreSQL + pgvector；`CREATE EXTENSION vector`；HNSW + `vector_cosine_ops`
- 磁盘：`data/files/`、`data/parsed/`（无 `images`）

---

## 认证与部署

- HttpOnly Session；表 `users`
- **Compose**：根目录 `docker-compose.yml` + `./scripts/deploy.sh`；Nginx 反代 `/api`
- **本机**：`127.0.0.1`；Worker 另开进程
- **CI**：`.github/workflows/ci.yml`（pytest + 前端 build + `docker compose build`；Node 24）

---

## 测试

- pytest：默认库、上传校验、checksum 去重、库隔离、标签/收藏、无命中短路径（Embedding 可 mock）
- 真 DashScope / 真网页：本机手工验收

---

## 环境变量

| 变量 | 用途 |
|---|---|
| `DATABASE_URL` | 例 `postgresql+psycopg://用户@127.0.0.1:5432/knowledge` |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | DashScope 兼容，非 OpenAI |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | 向量；Key/URL 可与 LLM 相同 |
| `DATA_DIR` | 默认仓库 `data/` |
| `ELASTICSEARCH_URL` | P2 BM25；未配则关键词路不可用 |
| `RERANK_API_KEY` / `RERANK_BASE_URL` / `RERANK_MODEL` | 重排；无 Key 则降级 |
| `RELEVANCE_MIN_SCORE` | 逐条门槛，默认 0.5 |
| `EXPAND_ANCHOR_MIN` | 邻居–锚点余弦门槛，默认 0.6 |
| `EXPAND_QUERY_MIN` | 邻居–query 分门槛，默认 0.3（有 Rerank Key 用批量 Rerank，否则余弦） |
| `SESSION_SECRET` | Session 签名，≥32 字符 |
| `INITIAL_USERNAME` / `INITIAL_PASSWORD` | 空库引导用户（密码只放本机 `.env`） |
| `REDIS_URL` | 任务队列，默认 `redis://127.0.0.1:6379/0` |
| `FLYAI_CLI` / `FLYAI_API_KEY` / `FLYAI_TIMEOUT` | 差旅 CLI |
| `HOTEL_SOURCE` | 空=占位；`flyai`=启用酒店搜索 |
| `MINIO_*` | 方案/报告 HTML；未配置则降级 |
| `NEWS_SOURCES_PATH` | 可选，覆盖默认知讯源 YAML |

`.env` gitignore；提供无密钥的 `.env.example` / `.env.docker.example`。

---

## 明确拒绝

MinerU、LlamaIndex、Ollama、Milvus、Celery、Kafka、Kubernetes、Meilisearch、浏览器自动化抓登录页。  
Redis **仅**作 arq 任务队列，不作 Checkpoint / 通用缓存。  
P2 关键词用 ES BM25，不用 `pg_trgm` 冒充。

### LangGraph 边界

1. 只用于 P1 Agent / Research 等多步编排；P0 `/api/chat` 保持 LangChain Chain。
2. Agent 经 Tool 复用 P0 `search_chunks`，不得另建向量检索。
3. 摘要 / 自动标签 / 文档对比继续用 Chain，不强制 Graph。
4. Checkpoint 不替代 `message` / `conversation.summary` / `user_memory`。
