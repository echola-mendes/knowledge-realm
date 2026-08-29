# 架构地图

代码仓库名：`knowledge_realm`。V1/P0 已落地。约定目录见 `tech-stack.md`。

**阶段：** P0、P1.1–P1.4、**P2（PRD-P2 §7）已确认结束。** **KB-ENABLE 代码已验证，待提出人确认。** 未开始 P3（冲突/缺口/多 Agent/库自动更新）；未开始 `search_graph` Tool、未做力导向可视化。

| 路径 | 职责 |
|---|---|
| `PRD.md` | 产品需求（P0 名单；P1 指向 `PRD-P1.md`） |
| `PRD-P2.md` | P2 范围与边界（Hybrid；STM/Summary/LTM 与 Checkpoint 分层；reason 统一路由；P3 名单） |
| `memory-bank/design-document.md` | 实现规格 |
| `memory-bank/tech-stack.md` | 技术选型 |
| `AGENTS.md` | Agent 约束 |
| `server/.venv` | Python 3.12 虚拟环境（不用 conda） |
| `server/requirements.txt` | 后端依赖 |
| `server/app/config.py` | 环境变量与 Settings |
| `server/app/main.py` | FastAPI 入口、`/health`、Session、启动时确保用户与默认库 |
| `server/app/user.py` | `users` 表引导用户（环境变量密码哈希） |
| `server/app/passwords.py` | Argon2 |
| `server/app/deps.py` | Session 当前用户 |
| `server/app/routers/auth.py` | login/logout/me |
| `server/app/kb.py` | 默认库；`search_kb_ids`（未传 id → 用户已开启库；传 id → 单库） |
| `server/app/routers/knowledge_bases.py` | 知识库 HTTP（含 `is_enabled` 开关） |
| `web/src/views/KnowledgeBasesView.vue` | 知识库管理（开关/筛选） |
| `server/app/routers/documents.py` | 上传、笔记、URL、列表、详情、`parsed.md`、删除、打标签、收藏、`/index`、`/reindex`、P1.1 `POST .../summarize` 与 `POST .../auto-tags`、P1.4 `POST .../graph` 与 `GET .../related` |
| `web/src/App.vue` | 左侧主导航；库切换与用户在侧栏底部 |
| `web/src/views/DebugView.vue` | 调试模式页（检索调试；不含切片配置） |
| `web/src/views/SettingsView.vue` | 设置；调试 panel 内可开调试模式，开启后同 panel 配置用户级 Chunk Size/Overlap |
| `web/src/components/RetrievalDebugPanel.vue` | 对话页 Retrieval Debug 抽屉 |
| `server/app/routers/retrieval_debug.py` | `POST /api/retrieval-debug` 与 labels |
| `server/alembic/` | 迁移；当前 `20260828_0014`（`document.chunk_size` / `chunk_overlap`） |
| `web/src/styles.css` | 全局设计 token 与顶栏/页面自适应容器（不锁 1440×900） |
| `server/app/routers/tags.py` | 标签创建/列表/删除 |
| `server/app/search.py` | Hybrid + RRF + Rerank；经 `search_kb_ids` 定库；0.30 仍看向量第一名；再按 `RELEVANCE_MIN_SCORE` 逐条过滤；可选 `created_after`/`created_before`（文档 `created_at`） |
| `server/app/rerank.py` | DashScope 兼容 `/reranks`；无 Key 则 LLM 打分；都没有则保持 RRF 顺序 |
| `server/app/es_bm25.py` | BM25 索引与检索；chunk 与 PG 同步 upsert/删除；测试可替换为内存实现 |
| `server/app/routers/search.py` | `POST /api/search`（可选 kind / 时间窗） |
| `web/src/views/SearchView.vue` | 搜索页：标签、kind、时间窗；不调 Chat |
| `server/app/llm.py` | LangChain 单链 Chat；无命中不调用 |
| `server/app/chat.py` | 问答：检索只用当前句；最近 6 条历史给 LLM |
| `server/app/routers/chat.py` | `POST /chat`、`/chat/stream`；会话列表/消息/删除 |
| `server/app/url_import.py` | 公开页 httpx + trafilatura；超时 20s；无浏览器自动化 |
| `server/app/parse.py` | md/txt UTF-8；PDF PyMuPDF 按页 `## Page N`；DOCX 按段落。无 OCR/MinerU |
| `server/app/chunk.py` | LangChain 标题切分；默认 800/120；`split_markdown(..., chunk_size, chunk_overlap)`；无 LlamaIndex |
| `server/app/chunk_settings.py` | 按用户读写 `user_chunk_setting`；无行则默认 800/120 |
| `server/app/routers/chunk_settings.py` | `GET/PUT /api/chunk-settings`（Session 用户） |
| `server/app/index.py` | 切块 Embedding 写入 `document_chunk`；切块用文档所属用户配置并写入 `document.chunk_size`/`chunk_overlap`；状态 `ready`；额度不足提示改 v4 |
| `server/app/storage.py` | 本地文件路径与清理 |
| `server/app/schemas.py` | Pydantic 模型 |
| `server/app/models.py` | SQLAlchemy 表 |
| `web/src/views/LoginView.vue` | 独立登录页 |
| `server/app/p1/chains.py` | P1.1/P1.2/P1.4 摘要、自动标签、文档对比、图谱抽取 Chain；禁止 import LangGraph |
| `server/app/p1/conversation_summary.py` | 消息 >6 时压缩更早轮次写入 `conversation.summary` |
| `server/app/p1/ltm.py` | `user_memory` 读写；Agent 灌入 `ltm_hits`（非向量检索） |
| `server/app/p1/checkpoint.py` | LangGraph `PostgresSaver`（同库连接池）；`setup` 建 checkpoint 表 |
| `server/app/p1/tools.py` | `search_knowledge`（内部 `search_chunks`，禁止 HTTP `/api/search`）；P2-Agent-5 `web_search`（httpx POST 配置端点，禁止 Playwright） |
| `server/app/p1/graph.py` | 一张 StateGraph：reason → DIRECT \| RAG \| WEB；首圈可写入 ≤3 有序子任务，之后每圈仍只选三者之一；`run_tool` 只执行 reason 指定的 Tool；`generate` 可带 STM / Summary / LTM / web_hits，有子任务时汇总；compile 带 checkpointer；`task=agent|report` 同图；max_loops=3 |
| `server/app/routers/p1.py` | P1.2 `POST /api/compare`；P1.3 `POST /api/agent` 与 `/api/agent/stream`（`thread_id=conversation_id`，每轮重灌 STM）；P1.4 `GET /api/graph` |
| `web/src/views/ChatView.vue` | 默认 `/api/chat/stream`；「Agent / 报告」走 `/api/agent/stream`（共享 `conversation_id`） |
| `web/src/views/ReaderView.vue` | 阅读页：摘要/自动标签；P1.4「抽取图谱」+ 实体/关系列表 + 相近文档（无 vis.js/D3） |
| `web/` | Vite + Vue 3 + TS；左侧栏 + 首页/文档/搜索/对话/Debug/阅读/设置 |
| `data/files/`、`data/parsed/` | 原件与解析稿；内容被 gitignore |
| `.env.example` | 环境变量模板（DashScope，无真实密钥） |
| `.gitignore` | 忽略 `.env`、venv、node_modules、用户 data |
| 本机 PostgreSQL `echola_kb` | 已创建；`vector` 0.8.0。连接用户 `postgres`，密码仅本机，不入库 |

无 MinerU、无独立向量库、无 Docker。

## P1.3 已落地边界

- `/api/chat`、`/api/chat/stream` 仍为 P0 LangChain 单链，未进图。
- Agent / 研究报告：同一张 `p1/graph.py`；`POST /api/agent` 与 `/api/agent/stream`；Tool 为 `search_knowledge`（内部 `search.py`，不是 HTTP `/api/search`）与 `web_search`（httpx）。`reason` 路由 DIRECT / RAG / WEB；复杂问句仅首圈可写 ≤3 有序子任务（`AgentState.subtasks` / `subtask_index`），之后每圈仍只选三者之一；无第二张图，`max_loops=3` 未放宽。
- Agent 记忆：STM 在 `message`（最近 6 条）；`conversation.summary` 为窗口外摘要；`user_memory` 为跨会话 LTM；Checkpoint 为 Postgres 图快照（`thread_id=conversation_id`）。
- 摘要 / 自动标签 / 文档对比 / 图谱抽取：`p1/chains.py`，无 LangGraph。
- 未做：HITL、Subgraph、Multi-Agent、`search_graph` Tool、力导向可视化。Summary / LTM / WEB / Planning 见设计文档第 4.7 节。

## P1.4 已落地边界

- 表：`entity` / `entity_link`（迁移 `20260824_0004`）；实体按库隔离。
- 抽取：`extract_graph` Chain → `POST /api/documents/{id}/graph`；upsert 实体，按文档替换边。
- 只读：`GET /api/graph`（可选 `knowledge_base_id`、`document_id`）；`GET /api/documents/{id}/related` 内部 `search_chunks`，排除本文、按文档去重最多 5 条。
- 前端：阅读页列表/表格；禁止 vis.js/D3 关系图。
- `/api/chat` 未改。Agent Tool 为 `search_knowledge` 与 `web_search`，**没有** `search_graph`。

## P2 已落地的 Agent 分层

- STM / Summary / LTM 是记忆，权威在表；Checkpoint 是图快照，不是 `AgentState` 字段。  
- `reason` 唯一路由：DIRECT / RAG / WEB；Agent-6 子任务 ≤3 已确认，仍一张图，不是第四张子图 / 动态 DAG / Multi-Agent。  
- 细则：`design-document.md` 第 4.7 节；步骤：`implementation-plan.md` P2-Agent-1～6。**P2 已确认结束。** KB-ENABLE：`knowledge_base.is_enabled`；检索未传 id 只打已开启库。不开始 P3，也不做 `search_graph` / 力导向可视化。
