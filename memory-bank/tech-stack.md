# 知域 — 技术栈

**依据：** `memory-bank/design-document.md`  
**原则：** 能覆盖 V1 P0 的最少组合；不引入设计已列为非目标的组件。

---

## 总览

| 层 | 选型 | 理由 | 不选 |
|---|---|---|---|
| 前端 | Vue 3 + TypeScript + Vite | 设计已定 Web；四五个页面，不必上大框架 | React（避免双栈） |
| 后端 | Python 3.11+ / FastAPI / Uvicorn | 上传 + JSON + SSE 足够 | Django |
| RAG 编排 | LangChain（切块 + Chat/Embedding 调用） | 设计已定单链 | LlamaIndex、LangGraph |
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
- LangChain：切块器用 `RecursiveCharacterTextSplitter` / Markdown 标题切分。调用模型可用 `langchain-openai` 里的 `ChatOpenAI` / `OpenAIEmbeddings`（**类名带 OpenAI，实际 `base_url` 填 DashScope**），或直接用 `openai` 包。二者都只要 DashScope Key。  
- 检索：自写 SQL `ORDER BY embedding <=> :q LIMIT k`（cosine 距离；与 HNSW `vector_cosine_ops` 一致），再在应用层换算分数并做 0.30 阈值  
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

`.env` gitignore；提供无密钥的 `.env.example`。

---

## 明确拒绝

MinerU、LlamaIndex、LangGraph、Ollama、Milvus、Celery、Redis、Kubernetes、全文检索引擎、浏览器自动化抓登录页。
