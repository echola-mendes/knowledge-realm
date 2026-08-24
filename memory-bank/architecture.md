# 架构地图

代码仓库名：`knowledge_realm`。V1/P0 已落地。约定目录见 `tech-stack.md`。

**阶段：** P0、P1.1、P1.2、P1.3、**P1.4 已落地**。未开始 `search_graph` Tool、未做力导向/ vis.js / D3 可视化。

| 路径 | 职责 |
|---|---|
| `PRD.md` | 产品需求（P0 名单；P1 指向 `PRD-P1.md`） |
| `PRD-P1.md` | P1 架构、Agent/RAG 边界、阶段 |
| `memory-bank/design-document.md` | 实现规格 |
| `memory-bank/tech-stack.md` | 技术选型 |
| `AGENTS.md` | Agent 约束 |
| `server/.venv` | Python 3.12 虚拟环境（不用 conda） |
| `server/requirements.txt` | 后端依赖 |
| `server/app/config.py` | 环境变量与 Settings |
| `server/app/main.py` | FastAPI 入口、`/health`、启动时确保默认库与占位用户 |
| `server/app/db.py` | 引擎与会话 |
| `server/app/kb.py` | 默认知识库 |
| `server/app/user.py` | 占位用户 `echola`；空表插入，已有行不改 |
| `server/app/routers/me.py` | `GET /api/me` |
| `server/app/routers/knowledge_bases.py` | 知识库 HTTP |
| `server/app/routers/documents.py` | 上传、笔记、URL、列表、详情、`parsed.md`、删除、打标签、收藏、`/index`、`/reindex`、P1.1 `POST .../summarize` 与 `POST .../auto-tags`、P1.4 `POST .../graph` 与 `GET .../related` |
| `web/src/` | 库切换（最右侧占位用户名与字母头像）、文档导入/标签/收藏、搜索、对话流式（默认 `/api/chat/stream`；可切 Agent / 报告走 `/api/agent/stream`）、阅读定位、阅读页生成摘要/自动标签/抽取图谱与相近文档列表、文档页勾选对比、设置密钥状态、隐私说明 |
| `web/src/styles.css` | 全局设计 token 与顶栏/页面自适应容器（不锁 1440×900） |
| `server/app/routers/tags.py` | 标签创建/列表/删除 |
| `server/app/search.py` | 余弦 TopK；只查 `ready`；低于 0.30 空列表；无第二套向量表 |
| `server/app/routers/search.py` | `POST /api/search` |
| `server/app/llm.py` | LangChain 单链 Chat；无命中不调用 |
| `server/app/chat.py` | 问答：检索只用当前句；最近 6 条历史给 LLM |
| `server/app/routers/chat.py` | `POST /chat`、`/chat/stream`；会话列表/消息/删除 |
| `server/app/url_import.py` | 公开页 httpx + trafilatura；超时 20s；无浏览器自动化 |
| `server/app/parse.py` | md/txt UTF-8；PDF PyMuPDF 按页 `## Page N`；DOCX 按段落。无 OCR/MinerU |
| `server/app/chunk.py` | LangChain 标题切分 + 800/120；内存 `TextChunk`（page/heading）；无 LlamaIndex |
| `server/app/index.py` | 切块 Embedding 写入 `document_chunk`；状态 `ready`；额度不足提示改 v4 |
| `server/app/storage.py` | 本地文件路径与清理 |
| `server/app/schemas.py` | Pydantic 模型 |
| `server/app/models.py` | SQLAlchemy 表 |
| `server/alembic/` | 迁移；当前 `20260824_0004` |
| `server/app/p1/chains.py` | P1.1/P1.2/P1.4 摘要、自动标签、文档对比、图谱抽取 Chain；禁止 import LangGraph |
| `server/app/routers/p1.py` | P1.2 `POST /api/compare`；P1.3 `POST /api/agent` 与 `/api/agent/stream`（`task=agent|report`，走 Graph，不经过 `/api/chat`）；P1.4 `GET /api/graph` |
| `server/app/p1/tools.py` | P1.3 `search_knowledge`：内部调用 `search_chunks`；禁止 HTTP `/api/search` |
| `server/app/p1/graph.py` | P1.3 一张 StateGraph：reason 只决策、run_tool 执行 search_knowledge、generate 成文；`task=agent|report` 同图；max_loops=3；无 Checkpoint |
| `web/src/views/ChatView.vue` | 默认 `/api/chat/stream`；「Agent / 报告」走 `/api/agent/stream` |
| `web/src/views/ReaderView.vue` | 阅读页：摘要/自动标签；P1.4「抽取图谱」+ 实体/关系列表 + 相近文档（无 vis.js/D3） |
| `web/` | Vite + Vue 3 + TS；路由首页/文档/搜索/对话/阅读/设置；`/api` 代理 `127.0.0.1:8000` |
| `data/files/`、`data/parsed/` | 原件与解析稿；内容被 gitignore |
| `.env.example` | 环境变量模板（DashScope，无真实密钥） |
| `.gitignore` | 忽略 `.env`、venv、node_modules、用户 data |
| 本机 PostgreSQL `echola_kb` | 已创建；`vector` 0.8.0。连接用户 `postgres`，密码仅本机，不入库 |

无 MinerU、无独立向量库、无 Docker。

## P1.3 已落地边界

- `/api/chat`、`/api/chat/stream` 仍为 P0 LangChain 单链，未进图。
- Agent / 研究报告：同一张 `p1/graph.py`；`POST /api/agent` 与 `/api/agent/stream`；Tool 仅 `search_knowledge` → 内部 `search.py`（不是 HTTP `/api/search`）。
- 摘要 / 自动标签 / 文档对比 / 图谱抽取：`p1/chains.py`，无 LangGraph。
- 未做：Checkpoint、HITL、Subgraph、Multi-Agent、`search_graph` Tool、力导向可视化。

## P1.4 已落地边界

- 表：`entity` / `entity_link`（迁移 `20260824_0004`）；实体按库隔离。
- 抽取：`extract_graph` Chain → `POST /api/documents/{id}/graph`；upsert 实体，按文档替换边。
- 只读：`GET /api/graph`（可选 `knowledge_base_id`、`document_id`）；`GET /api/documents/{id}/related` 内部 `search_chunks`，排除本文、按文档去重最多 5 条。
- 前端：阅读页列表/表格；禁止 vis.js/D3 关系图。
- `/api/chat` 未改。Agent Tool 仍仅 `search_knowledge`，**没有** `search_graph`。
