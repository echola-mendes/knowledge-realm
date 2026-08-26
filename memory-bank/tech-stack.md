# 知域 — 技术栈

**依据：** `memory-bank/design-document.md`  
**原则：** 能覆盖 V1 P0 的最少组合；不引入设计已列为非目标的组件。

---

## 总览

| 层 | 选型 | 理由 | 不选 |
|---|---|---|---|
| 前端 | Vue 3 + TypeScript + Vite | 设计已定 Web；四五个页面，不必上大框架 | React（避免双栈） |
| 后端 | Python 3.11+ / FastAPI / Uvicorn | 上传 + JSON + SSE 足够 | Django |
| RAG 编排 | P0：LangChain 单链。P1 Agent / Research Report：LangGraph 做多步状态编排，经 Tool 调用 P0 检索 | P0 已定单链；Agent 复用而非替换 RAG | 用图重写 `/api/chat`；为引入图而重构 P0；LlamaIndex |
| P1 短任务 | LangChain Chain（摘要、自动标签、对比） | 一次 LLM 足够 | 把摘要/标签做成 Graph |
| 向量读写 | SQLAlchemy 管表 + SQL 余弦查询 | 一张 `document_chunk`，避免第二套向量表 | langchain 自建 PGVector 集合 |
| 解析 | pymupdf、python-docx、标准库读文本 | 无 MinerU、无 OCR | MinerU、Unstructured 全家桶 |
| 网页正文 | httpx + trafilatura | 公开文章抽正文，失败即导入失败 | Playwright（过重） |
| 存储 | 本机 PostgreSQL + pgvector | 已安装；元数据与向量一体 | Milvus、Docker Postgres |
| ORM / 迁移 | SQLAlchemy 2 + Alembic | 表演进可重复 | 纯手写 SQL |
| 任务 | FastAPI BackgroundTasks | 设计允许进程内；个人单机 | Celery、Redis |
| LLM / Embedding | Python 包 `openai`（仅作 HTTP 客户端）打 **DashScope 兼容模式** | 你不需要 OpenAI 账号；用阿里云 DashScope Key。协议碰巧和 OpenAI 一样 | 直连各家五花八门 SDK；Ollama |
| 认证 | 无 | 单用户本机；占位表 `app_user` 一行 | JWT |
| 部署 | 本机 `server/.venv` + npm；无 Docker | 设计明确 | conda 新建环境；K8s |
| 测试 | pytest + httpx | 测 API 与隔离检索 | 强制 E2E |

---

## 前端

- Vue 3 `<script setup>` + TypeScript + Vite  
- Vue Router：首页、文档、搜索、对话、阅读、设置（可合并）  
- Markdown 展示：`markdown-it`  
- HTTP：`fetch`；SSE 用 `fetch` 读 stream  
- 开发：Vite 代理 `/api` → FastAPI  
- 不做：Pinia 大模块、组件库套装、SSR  

目录：`web/`

---

## 后端

- FastAPI + Pydantic v2 + python-dotenv  
- LangChain：切块器用 `RecursiveCharacterTextSplitter` / Markdown 标题切分。P0 问答：`ChatOpenAI` 单链。P1 Agent（P1.3 起）可用 LangGraph，检索必须走现有 `search.py` 封装的 Tool，禁止第二套向量查询。  
- 检索：P0/P1 为 SQL `ORDER BY embedding <=> :q LIMIT k` + 应用层 0.30。P2 在同一 `search_chunks` 内：pgvector + ES BM25 + RRF + 最多 20 条 Rerank，再按 `RELEVANCE_MIN_SCORE` 逐条过滤  
- P2 Checkpoint：LangGraph 官方 Postgres checkpointer，同一 `DATABASE_URL`，禁止 Redis。Checkpoint 存 `AgentState` 快照，不替代 `message` / `conversation.summary` / `user_memory`。新 user 轮次从 DB 灌 STM，不以 checkpoint 旧消息为聊天权威。  
- P2 Agent 路由：`p1/graph.py` 的 `reason` 为唯一决策点。P2-Agent-5 起 `DIRECT` / `RAG` / `WEB`；P2-Agent-6 可写 ≤3 子任务但仍走同一 reason，无第二张图。  
- P2 关键词：本机 Elasticsearch（BM25）。应用仍绑 127.0.0.1；ES 为本机进程或**仅用于 ES 的** Docker，不把整个知域容器化。禁止 Meilisearch、禁止用 ES 存 embedding 做主向量检索   
- 对话与向量：安装 PyPI 上的包 **`openai`**。这是通用客户端，**不是**「必须注册 OpenAI」。  
  指向阿里云兼容地址即可，例如：  
  `LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`  
  `LLM_API_KEY=` 你的 **DashScope API Key**  
  `LLM_MODEL=qwen-plus`  
  Embedding 同样用该 Key 与兼容地址，默认 `EMBEDDING_MODEL=text-embedding-v3`。额度不够时由提出人改成 `text-embedding-v4`（应用须提示，不自动切换）。V1 不用本机 Embedding。  
- 也可改成 DeepSeek / 其它兼容端点，仍用同一包，只改 env。  
- **不需要** OpenAI 官网账号或 `sk-` OpenAI 密钥。  
- URL：`httpx` 超时 20s；`trafilatura` 抽正文  
- 哈希：SHA-256  

目录：`server/`

默认模型：`qwen-plus`、`text-embedding-v3`、`EMBEDDING_DIM=1024`。同维换 `text-embedding-v4` 后须对该库文档 reindex。改 `EMBEDDING_DIM` 必须重建向量列并全量 reindex。

---

## 存储

- 本机 PostgreSQL（已含 pgvector），库名 `echola_kb`  
- `CREATE EXTENSION vector`；HNSW + `vector_cosine_ops`  
- 磁盘：`data/files/`、`data/parsed/`（无 `images`）  

---

## 认证与部署

- 无登录；仅有占位用户行；监听 `127.0.0.1`  
- 不使用 Docker  

---

## 测试

- pytest 覆盖：默认库、上传校验、checksum 去重、库隔离、标签筛选、收藏、无命中短路径（Embedding 可 mock）  
- 真 DashScope、真网页：本机按设计第 9 节手工验收  

---

## 环境变量

| 变量 | 用途 |
|---|---|
| `DATABASE_URL` | 例 `postgresql+psycopg://用户@127.0.0.1:5432/echola_kb` |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | **DashScope** Key 与兼容 Base URL，不是 OpenAI |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | 向量；Key/URL 可与 LLM 相同 |
| `DATA_DIR` | 默认仓库 `data/` |
| `ELASTICSEARCH_URL` | P2 BM25；例 `http://127.0.0.1:9200`。未配则 Hybrid 关键词路不可用（见计划，禁止假装已 Hybrid） |
| `RERANK_API_KEY` / `RERANK_BASE_URL` / `RERANK_MODEL` | P2-RAG-2 重排。硅基：`https://api.siliconflow.cn/v1/rerank` + `Qwen/Qwen3-Reranker-0.6B`。无 Key 则 LLM 打分 |
| `RELEVANCE_MIN_SCORE` | P2-RAG-3 逐条门槛，默认 0.5（Rerank 分；未重排时仍是余弦分）。须可调 |

`.env` gitignore；提供无密钥的 `.env.example`。

---

## 明确拒绝

MinerU、LlamaIndex、Ollama、Milvus、Celery、Redis、Kubernetes、Meilisearch、浏览器自动化抓登录页。P2 关键词检索用 Elasticsearch BM25，不用 Postgres `pg_trgm` 充当 BM25。

### LangGraph 使用边界

核心：LangGraph 只负责 P1 的复杂 Agent 工作流；P0 RAG 保持原样。Agent 调用 P0 RAG，而不是替换 P0 RAG。

1. LangGraph 用于 P1 的 Agent / Research Report 等需要多步骤状态编排的能力。
2. P0 的 `/api/chat` 和 `/api/chat/stream` 保持现有 LangChain Chain 实现，不迁移到 LangGraph。
3. P1 Agent 必须复用 P0 已有 RAG / Search 能力，不得重新实现 pgvector 检索。
4. LangGraph 可以通过 Tool 调用 P0 Search/RAG 能力。
5. 不得为了引入 LangGraph 而重构 P0。  
6. P1 中简单的摘要、自动标签、文档对比等线性任务继续使用 LangChain Chain，不强制 Graph 化。  
7. P2 检索增强必须改现有 `search.py` 的 `search_chunks`，供 Chat、搜索 HTTP、Agent Tool 共用。  
8. P2 不得把 `/api/chat` 迁到 LangGraph；不得无命中强制 Web Search；不得用 `document_chunk` 冒充 LTM。  
9. P2 不得把 Checkpoint 当成 STM/Summary；`reason` 统一路由，禁止各 Tool 自行决定是否调用。
