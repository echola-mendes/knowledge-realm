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
| 认证 | FastAPI Session Cookie + Argon2 | 最小多用户隔离；身份只来自 Session | JWT / OAuth / RBAC |
| 部署 | 本机 `server/.venv` + npm；无 Docker | 设计明确 | conda 新建环境；K8s |
| 测试 | pytest + httpx | 测 API 与隔离检索 | 强制 E2E |

---

## 前端

- Vue 3 `<script setup>` + TypeScript + Vite  
- Vue Router：首页、文档、搜索、对话、阅读、设置（可合并）  
- 侧边栏菜单配置：`web/src/navConfig.ts` 定义带稳定 key 的菜单元数据（默认顺序：首页/对话/搜索/知识库/文档/图谱/检测/工具/监控/基础/设置，调试随开关追加在设置前），顺序与自定义名称持久化在 localStorage（key `zhiyu-nav-config`）；`web/src/views/MenuManageView.vue`（基础页"菜单管理"）支持改名与原生 HTML5 拖拽排序（附上移/下移按钮兜底），`/basics` 使用 `BasicsLayout.vue` 二级菜单布局，`/tools` 使用 `ToolsLayout.vue` 二级菜单（旅程 / AI咨询 / AI生图 / 更多工具，样式见 `web/style.md` §13），`MyTripsView` 用行程类型、无状态（`web/style.md` §14；`plan_record.trip_type` / `nights`），`/monitoring` 复用 `ToolPlaceholderView.vue` 占位  
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

- HttpOnly Session；表 `users`；监听 `127.0.0.1`  
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
| `SESSION_SECRET` | Session 签名，至少 32 字符 |
| `INITIAL_USERNAME` | 空库引导用户名，默认 `echola` |
| `INITIAL_PASSWORD` | 空库引导密码，只放本机 `.env`，哈希入库 |
| `FLYAI_CLI` / `FLYAI_API_KEY` / `FLYAI_TIMEOUT` | 飞猪 flyai skill CLI（免 Key trial 可用）；CLI 子命令 `search-flight`/`search-hotel`，stdout 单行 JSON |
| `HOTEL_SOURCE` | 酒店源：留空=占位提示（不伪造房型）；`flyai`=启用 flyai search-hotel |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET` / `MINIO_SECURE` | MinIO 软依赖：方案页 `plans/{conversation_id}/` 与知识报告 `reports/{conversation_id}/` 回看；未配置仅实时展示 |

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

### P4 Master 入口（2026-08-31 起）

- 对话模式分流：`task=knowledge` 直连旧版单知识库 Agent（`graph.py`，不经 Master）；`task=agent|report` 仍走 `/api/agent(/stream)`：**薄意图 → Master → 子能力**；`/api/chat` 不改，禁止并行第二条 travel API。
- **意图 ≠ Master**：`intent.py` 只输出标签（一次结构化 LLM 分类，失败回退启发式）；`master.py` 只按标签调度并整合，不做第二套意图识别。
- Master 图：`intent → (knowledge | chat | plan | booking) → finalize`。knowledge = 现有 `graph.py` 作为子图挂载（内部 checkpoint `thread_id=conversation_id` 不变）；plan = `plan_agent.py` ReAct 子图；booking = `booking_agent.py` HITL 子图。Master 自身 checkpoint 用 `master-{conversation_id}` 前缀，二者互不覆盖。
- `AgentOut` / stream 终态新增 `intent` 字段；stream 首个 SSE 事件为 `{type:'intent', intent}`。
- plan / booking 意图分别在 P4 Step 2 / 3 落地为真实子 Agent；Step 1 的 stub 已替换。
- 代码组织：原 `server/app/p1/` 已上移平铺到 `server/app/`（`intent.py` / `master.py` / `graph.py` / `tools.py` / `chains.py` / `ltm.py` / `checkpoint.py` / `conversation_summary.py`）；路由层仍在 `routers/master.py`。
- **TRAVEL-PLAN-1（Step 2，2026-09-01）**：`plan` 意图 → `plan_agent.py` ReAct 子图（reason→run_tool 循环，无 checkpointer）。工具：`travel/tools.py` 的 `search_flights`（flyai 响应原样透传，前端卡片绑 `itemList`）/`search_hotels`（无源时 `{kind:"placeholder"}`，不伪造房型）/`plan_itinerary`（LLM 结构化 `{options,comparison,recommendation,total_price_summary}`，失败用搜索结果兜底）/`save_plan_html`（渲染 HTML→MinIO `plans/`，软依赖）。缺失要素（出发地/目的地/出发日期）对话补问；口头偏好只改提及字段，params merge 不丢日期/城市。SSE 事件：`progress`/`travel_data`（平铺 flights/hotels/plan）/`plan_html`；`task=report` 报告 HTML 上传 MinIO `reports/`，`AgentOut.report_url` 回传。
- **TRAVEL-BOOK-1（Step 3，2026-09-01）**：`booking` 意图 → `booking_agent.py` HITL 子图。写操作（book/cancel）先返回 `pending_action`，经 SSE `{type:'hitl', ...}` 推送前端；`list` / 确认落库后 SSE `{type:'booking_data', items}`。用户同会话确认（`AgentRequest.hitl_confirm`）后再落库。数据表 `booking_record`；`list_bookings` 仅查当前用户；`cancel_booking` 校验用户归属并更新 `status='cancelled'`。写限流 30 次/分钟 → HTTP 429。`AgentOut` 含 `pending_action`、`bookings`；前端 `BookingListCard.vue` 展示列表/支付链接。


### 文件说明
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
| `server/app/routers/knowledge_bases.py` | 知识库 HTTP（含 `is_enabled` 开关；P3 `POST .../refresh-urls`） |
| `web/src/views/KnowledgeBasesView.vue` | 知识库管理（开关/筛选） |
| `server/app/routers/documents.py` | 上传、笔记、URL、列表、详情、版本、删除、标签、收藏、index/reindex、P3 `POST .../refresh`（url）、P1 summarize/auto-tags/graph/related |
| `web/src/App.vue` | 左侧主导航；库切换与用户在侧栏底部 |
| `web/src/views/DebugView.vue` | 调试模式页：检索调试、Agent 执行轨迹（含总 Token）、答案质量评估；不含切片配置 |
| `web/src/views/SettingsView.vue` | 设置；调试 panel 内可开调试模式，开启后同 panel 配置用户级 Chunk Size/Overlap |
| `web/src/components/RetrievalDebugPanel.vue` | 对话页 Retrieval Debug 抽屉 |
| `server/app/routers/retrieval_debug.py` | `POST /api/retrieval-debug`、labels、`POST /api/retrieval-debug/answer-quality` |
| `server/app/routers/master.py` | `/api/agent`、`/api/agent/stream`（伪流式，**sync def** 跑线程池，避免占事件循环卡住侧栏 `/me`）与旁路 `POST /api/agent/trace`（`stream_mode="updates"` 逐节点 SSE，不落库） |
| `server/alembic/` | 迁移；当前 `20260901_0018`（新增 `booking_record`） |
| `web/src/styles.css` | 全局设计 token 与顶栏/页面自适应容器（不锁 1440×900） |
| `server/app/routers/tags.py` | 标签创建/列表/删除 |
| `server/app/search.py` | Hybrid + RRF + Rerank；经 `search_kb_ids` 定库；0.30 仍看向量第一名；再按 `RELEVANCE_MIN_SCORE` 逐条过滤；可选 `created_after`/`created_before`（文档 `created_at`） |
| `server/app/rerank.py` | DashScope 兼容 `/reranks`；无 Key 则 LLM 打分；都没有则保持 RRF 顺序 |
| `server/app/es_bm25.py` | BM25 索引与检索；chunk 与 PG 同步 upsert/删除；测试可替换为内存实现 |
| `server/app/routers/search.py` | `POST /api/search`（可选 kind / 时间窗） |
| `web/src/views/SearchView.vue` | 搜索页：标签、kind、时间窗；不调 Chat |
| `server/app/insights.py` | P3 洞察 Chain：冲突 / 缺口 / 自动整理（补标签 + 重复/空摘要/命名报告） |
| `server/app/routers/insights.py` | `POST /api/knowledge-bases/{id}/insights/conflicts|gaps|organize`；报告不落库（organize 的自动补标签会写 `document_tag`） |
| `server/app/recommendations.py` | 主动推荐：收藏 + 最近 citation 文档作种子，`search_chunks` 扩展相似文档，排除种子/已收藏，取 5 |
| `server/app/routers/recommendations.py` | `GET /api/recommendations` |
| `web/src/views/HomeView.vue` | 首页：统计、最近文档、推荐阅读卡片 |
| `web/src/views/InsightsView.vue` | `/insights`：冲突检测 + 缺口分析 + 自动整理；本机历史 |
| `web/src/api-insights.ts` | 洞察 API 客户端 |
| `server/app/llm.py` | LangChain 单链 Chat；`chat_with_usage()` 返回 usage；Agent Trace 读取 token；无命中不调用 |
| `server/app/chat.py` | 问答：检索只用当前句；最近 6 条历史给 LLM |
| `server/app/routers/chat.py` | `POST /chat`、`/chat/stream`（sync def，与 agent/stream 同样不占事件循环）；会话列表/消息/删除 |
| `server/app/url_import.py` | 公开页 httpx + trafilatura；超时 20s；无浏览器自动化 |
| `server/app/parse.py` | md/txt UTF-8；PDF PyMuPDF 按页 `## Page N`；DOCX 按段落。无 OCR/MinerU |
| `server/app/chunk.py` | LangChain 标题切分；默认 800/120；`split_markdown(..., chunk_size, chunk_overlap)`；无 LlamaIndex |
| `server/app/chunk_settings.py` | 按用户读写 `user_chunk_setting`；无行则默认 800/120 |
| `server/app/routers/chunk_settings.py` | `GET/PUT /api/chunk-settings`（Session 用户） |
| `server/app/index.py` | 切块 Embedding 写入 `document_chunk`；切块用文档所属用户配置并写入 `document.chunk_size`/`chunk_overlap`；状态 `ready`；额度不足提示改 v4；P3 `index_document_incremental` 差量更新 |
| `server/app/storage.py` | 本地文件路径与清理 |
| `server/app/schemas.py` | Pydantic 模型；`AgentRequest` 新增 `hitl_confirm`，`AgentOut` 新增 `pending_action` |
| `server/app/models.py` | SQLAlchemy 表；新增 `booking_record` 存储旅行预订 |
| `web/src/views/LoginView.vue` | 独立登录页 |
| `server/app/chains.py` | P1.1/P1.2/P1.4 摘要、自动标签、文档对比、图谱抽取 Chain；禁止 import LangGraph |
| `server/app/conversation_summary.py` | 消息 >6 时压缩更早轮次写入 `conversation.summary` |
| `server/app/ltm.py` | `user_memory` 读写；Agent 灌入 `ltm_hits`（非向量检索） |
| `server/app/checkpoint.py` | LangGraph `PostgresSaver`（同库连接池）；`setup` 建 checkpoint 表 |
| `server/app/tools.py` | `search_knowledge`（内部 `search_chunks`，禁止 HTTP `/api/search`）；P2-Agent-5 `web_search`（httpx POST 配置端点，禁止 Playwright） |
| `server/app/graph.py` | 一张 StateGraph：reason → DIRECT \| RAG \| WEB \| GRAPH；首圈可写入 ≤3 有序子任务，之后每圈仍只选四者之一；`run_tool` 只执行 reason 指定的 Tool；`generate` 可带 STM / Summary / LTM / web_hits，有子任务时汇总；compile 带 checkpointer；`task=agent|report` 同图；max_loops=3 |
| `server/app/intent.py` | P4 薄意图：一次 LLM 结构化分类 → `knowledge \| plan \| booking \| chat`；`task=report` 强制 `knowledge`；LLM 失败/解析失败回退关键词启发式；只出标签，不做检索与整合 |
| `server/app/master.py` | P4 Master 图（Supervisor 骨架）：`intent → knowledge/chat/plan/booking → finalize`；knowledge 节点调用 `graph.build_graph()`（子图 checkpoint `thread_id=conversation_id` 不变）；chat 节点经 `llm.chat` 直接寒暄；plan 节点调用 `plan_agent.py`；booking 节点调用 `booking_agent.py`；Master 自身 checkpoint `thread_id=master-{conversation_id}` |
| `server/app/plan_agent.py` | P4 plan 子 Agent（TRAVEL-PLAN-1）：ReAct reason→run_tool；缺要素 `ask` 补问；params merge 保留未提及字段；无 checkpointer |
| `server/app/booking_agent.py` | P4 booking 子 Agent（TRAVEL-BOOK-1）：ReAct reason→run_tool；book/cancel 写操作 HITL；未确认生成 `pending_action`，确认后落库 `booking_record`；无 Master 自身 checkpoint 外的持久 |
| `server/app/travel/rate_limit.py` | 预订写限流：进程内 sliding window，用户维度 30 次/60s，超限抛 `RateLimitedError` |
| `server/app/travel/flyai.py` | flyai skill CLI 封装：`search-flight`/`search-hotel`；stdout 单行 JSON 原样返回（含 `itemList`）；失败抛 `FlyaiError` |
| `server/app/travel/tools.py` | 差旅工具：机票透传/酒店占位（无源不伪造）/`plan_itinerary`（LLM 结构化+兜底）/`save_plan_html`（HTML→MinIO） |
| `server/app/travel/minio_store.py` | MinIO 软依赖：`plans/{conversation_id}/{ts}.html` 与 `reports/{conversation_id}/{ts}.html` 前缀分离；未配置/失败返回 None 降级 |
| `server/app/models.py` / Alembic `20260902_0019` | `plan_record`：本人行程方案元数据（title/origin/destination/depart_date/minio_key/url/payload） |
| `server/app/routers/plans.py` | `GET /api/plans`、`GET /api/plans/{id}`：Session 用户隔离 |
| `server/app/plan_agent.py` | `save` 后 `persist_plan_record`（无 MinIO 也落库）；Master `node_plan` 传入 session/user_id |
| `server/app/routers/master.py` | P1.2 `POST /api/compare`；`POST /api/agent` 与 `/api/agent/stream`：`task=knowledge` 直连 `build_graph()`；`task=agent|report` 调 `build_master_graph()`（薄意图 → Master → 子能力；stream 首事件 `{type:'intent'}`；booking HITL）；旁路 `POST /api/agent/trace` 仍走 `graph.py` |
| `web/src/views/ChatView.vue` | 默认 `/api/chat/stream`；「知识 Agent」→ `task=knowledge` 直连 `graph.py`；「Multi Agent / Report」→ `task=agent|report` 经 Master；共享 `conversation_id`；离开页 abort SSE，且仅在 `/chat` 上 sync query，避免思考中把侧栏导航拽回 |
| `web/src/views/ReaderView.vue` | 阅读页：摘要/自动标签；P1.4「抽取图谱」+ 实体/关系列表 + 相近文档；P3-EXT 抽取后「查看图谱」入口 |

| `server/app/tools.py` | 新增 `search_graph()` 与 `search_graph_details()`：实体名子串匹配 → 沿 `entity_link` 扩展 1–2 跳 → 返回关联文档切片；`search_graph_details` 额外返回命中实体、关系、路径、相关文档；两者不建第二套向量集合 |
| `server/app/routers/master.py` | 新增 `GET /api/graph/search`、`GET /api/graph/search/details`、`GET /api/graph/documents`；`/api/agent/stream` 流式事件识别 `search_graph` Tool |
| `server/app/graph.py` | Agent StateGraph 新增 `GRAPH` action：`reason` 输出 `action=graph`，`run_tool` 调用 `search_graph` |
| `web/src/views/KnowledgeGraphView.vue` | `/knowledge-graph` 力导向 SVG 可视化页：知识库/实体/关系筛选与重置、力导向布局、搜索高亮、4 Tab 面板（节点详情、路径探索、邻居节点、检索辅助）、画布控制、统计 |
| `web/src/components/Icon.vue` | 补齐 `minus / maximize / refresh / fullscreen` 等图谱控制图标 |
| `web/src/router.ts` | `/knowledge-graph`；`/tools` 布局（默认 `trips`；另有 `consult` / `image` 占位） |
| `web/src/App.vue` | 侧栏「知识图谱」；「工具」（`tools` 图标）→ `/tools` |
| `web/src/views/ToolsLayout.vue` | 工具页内二级菜单：旅程 / AI咨询 / AI生图 |
| `web/src/views/MyTripsView.vue` | 工具 → 我的行程单：接 `GET /api/plans` 列表；空态引导 Multi Agent |
| `server/app/message_ui.py` | 助手消息 UI 载荷：`plan_html`/`travel_data` 随 `message.citations` envelope 落库；`GET .../messages` 解包回放，旧消息可从 `plan_record` 补 url |
| `web/src/views/ToolPlaceholderView.vue` | 工具占位页：读 `route.meta.title/sub`，展示「即将推出」 |

| `web/` | Vite + Vue 3 + TS；左侧栏 + 首页/文档/搜索/对话/Debug/阅读/设置 |
| `data/files/`、`data/parsed/` | 原件与解析稿；内容被 gitignore |
| `.env.example` | 环境变量模板（DashScope，无真实密钥） |
| `.gitignore` | 忽略 `.env`、venv、node_modules、用户 data |
| 本机 PostgreSQL `echola_kb` | 已创建；`vector` 0.8.0。连接用户 `postgres`，密码仅本机，不入库 |

