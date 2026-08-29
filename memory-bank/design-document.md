# 知域 — 产品设计文档

**状态：** 可执行  
**依据：** 仓库 `PRD.md`（P0 已确认）；P1 见 `PRD-P1.md`；P2 范围见 `PRD-P2.md`（提出人已确认边界修正）  
**产品名称：** 知域  
**用户：** 本机 Web；基础登录 + 按用户数据隔离（非企业 RBAC）  

---

## 1. 设计裁决

| 项 | 裁决 |
|---|---|
| V1 范围 | **P0 已完成**。P1.1–P1.4 已完成。**P2** 见 `PRD-P2.md`：未写进 `implementation-plan.md` 的步骤不要做代码。不要开始 `search_graph` Tool 或力导向可视化。Agent 记忆分层见第 4.7 节：Checkpoint ≠ Summary |
| 编排 | **P0：** LangChain 单链 RAG；`/api/chat` 不进图。**P1 Agent：** 允许 LangGraph，且必须经 Tool 调用 P0 检索。摘要/标签/对比只用 Chain。不上 LlamaIndex |
| 解析 | 不上 MinerU。PDF = PyMuPDF 文本层；DOCX = python-docx；MD/TXT/笔记 = 直读；URL = 抓公开页正文 |
| 检索 | **P0/P1：** pgvector 余弦（方案 A），`search_chunks` 最高分 &lt; 0.30 整次为空（只卡第一名）。**P2：** 同一入口内 Hybrid（向量 + **Elasticsearch BM25 关键词**）→ RRF →（后阶段）Rerank → 相关性判断；无相关不引用、Chat 不拒答。向量仍只在一张 `document_chunk`；ES **只做关键词 BM25**，禁止把 ES 当第二套向量库 |
| 知识库 | 可多个；启动时若不存在则创建名为 `默认知识库` 的记录。每库有 `is_enabled`（新建默认开启）。**导入/文档列表**仍可指定单个库（缺省默认库）。**搜索 / 对话 / Agent** 未传 `knowledge_base_id` 时检索**当前用户所有已开启库**；传了 id 则只打该库（须属于本人） |
| 用户 | 表 `users`（username、password_hash）。HttpOnly Session Cookie。身份只来自 Session，禁止请求参数 `user_id`。知识库/会话/标签/收藏带 `user_id`；文档与切片经库继承。不做 RBAC/租户/OAuth |
| 标签与收藏 | P0 必须实现 |
| Word | 仅 `.docx` |
| URL | 无需登录的公开页；失败则导入失败 |
| 出网 | 切块与问题发云端 Embedding/LLM（默认 DashScope 兼容接口）；原件与库在本机 |
| 界面 | Web（Vue 3 + TypeScript，与后续 tech-stack 一致） |

本文与 PRD 冲突时以 **本文 + PRD 文首已确认约束** 为准。

---

## 2. 范围与非目标

### 2.1 V1 目标

1. 知识库 CRUD；默认知识库。  
2. 导入：PDF / docx / md / txt、公开 URL、手动笔记（Markdown）。  
3. 异步处理：解析 → 切块 → Embedding → 入库。  
4. 文档列表/详情/阅读解析稿/删除/重新处理/来源展示。  
5. 标签：增删、打在文档上。P0 不自动打标；自动标签属 **P1.1**。  
6. 收藏：收藏/取消文档（V1 不收藏「片段」——PRD 片段收藏放到 P1，避免范围膨胀）。  
7. 搜索：余弦 TopK，可筛知识库、标签、类型。  
8. RAG 问答：全库（默认或指定）或指定文档；多轮；引用；流式。  
9. 首页：提问入口、统计（文档数/库数/标签数）、最近添加。对话记录在对话页左侧栏列出，可用按钮折叠。

### 2.2 非目标

MinerU、LlamaIndex、Ollama、Milvus、RBAC/组织/租户/OAuth/JWT、扫描件 OCR、`.doc`、登录墙网页、Meilisearch。P0 路径不上 LangGraph。知识冲突/缺口/整理/推荐、Multi-Agent、知识库自动更新属 **P3**。Web Search、Checkpoint、**Elasticsearch BM25 关键词**属 **P2**（见 `PRD-P2.md`）。登录为独立页，不是 Chat/Agent/Report/Debug 业务 Tab。

**收藏片段：** V1 只收藏文档。

**P1：** 不重构 P0；旧 RAG 不进图。细则 `PRD-P1.md`。

---

## 3. 用户旅程

### 3.1 主路径

打开 Web → 见隐私说明 → 向默认库上传带文本层的 PDF → 状态至「已完成」→ 提问 → 回答带文件名与页码 → 点引用打开解析页。

### 3.2 知识库范围

导入落点：未指定库时写入默认知识库。侧栏切换器只影响导入与文档列表。

检索：知识库管理页可开关每个库；问答与搜索默认命中全部已开启库。关闭的库不参与检索。需要单库时接口仍可传 `knowledge_base_id`。

### 3.3 URL

粘贴公开文章 URL → 正文快照入库 → 可问可搜。登录页失败并显示原因。

### 3.4 标签与收藏

给文档打标签；按标签搜；收藏后在收藏列表可见。

---

## 4. 功能行为

### 4.1 导入与解析

- 上传：multipart，`knowledge_base_id` 可选（缺省默认库）。单文件 ≤ 100MB。扩展名：`.pdf` `.docx` `.md` `.markdown` `.txt`。  
- 路径：`data/files/{yyyy}/{id}{ext}`；解析：`data/parsed/{id}/document.md` 与轻量 `document.json`。URL 快照同目录。  
- 接口立即返回，后台处理。  
- PDF：按页文本，`## Page N`；page 从 1。无 OCR。  
- 空文本：`处理失败` / `empty_content`。解析超时 **60 秒**。  
- 同库相同 SHA-256：跳过解析与 embedding，返回已有文档。  

#### 4.1.1 文档状态（应用层状态机）

**说明：** 下列状态码为知域「导入 → 解析 → 切片向量化」流水线的**应用层约定**，存于 `document.status`（`String(32)`）。**不是** pgvector、Embedding API 或 LangChain 的内置状态。对用户产品语义仍为三类：**处理中 / 已完成 / 处理失败**；仅 `ready`（已完成）参与检索与问答。

**状态码与界面文案（文档列表「状态」列）：**

| 状态码 | 界面显示 | 产品语义 | 说明 |
|--------|----------|----------|------|
| `pending` | 待处理 | 处理中 | 已入库或 reindex 重置后，等待后台任务开始 |
| `parsing` | 解析中 | 处理中 | 读取原文并生成 `data/parsed/{id}/document.md` |
| `parsed` | 待向量化 | 处理中 | 解析成功；通常很快进入向量化（`process_document` 内联调用索引） |
| `indexing` | 向量化中 | 处理中 | 切片、Embedding、写入 `document_chunk` |
| `ready` | 已完成 | 已完成 | 终态；可被检索、问答、对比 |
| `parse_failed` | 解析失败 | 处理失败 | 终态；`error_message` 记录解析阶段原因 |
| `index_failed` | 向量化失败 | 处理失败 | 终态；`error_message` 记录向量化/入库阶段原因 |

**正常流转：**

```text
pending → parsing → parsed → indexing → ready
```

**失败分支：** `parsing` 阶段失败 → `parse_failed`；`indexing` 阶段失败 → `index_failed`。失败后不自动恢复；用户可点「向量化」（`POST /api/documents/{id}/reindex`）或删除后重新上传。

**触发入口：**

- 上传文件 / 创建笔记 / 导入 URL：创建时 `status=pending`，`BackgroundTasks` 调用 `process_document`（先解析，未 `parse_failed` 则继续 `index_document`）。
- 同库 checksum 命中：返回已有文档，**不**重新走状态机。
- reindex：删除该文档旧切片（及 ES 索引若已配置）→ `pending` + 清空 `error_message` → 重新 `process_document`。

**常见 `error_message`（失败原因列 / API `error_message`）：**

| 码 | 典型场景 |
|----|----------|
| `empty_content` | 解析结果为空 |
| `missing_original` | 本地原文文件缺失 |
| `invalid_utf8` | 文本编码无效 |
| `parse_timeout` | 解析超过 60 秒 |
| `parse_error:…` | 其他解析异常 |
| `no_parsed_markdown` | 缺少解析产物 |
| `no_chunks` | 无法生成有效切片 |
| `未配置 Embedding API Key` | 未配置 Embedding |
| `embed_failed:…` / `index_error:…` | Embedding 或入库异常 |
| `url_timeout` / `url_fetch_failed` | URL 抓取失败 |

**列表筛选映射：** 「处理中」= 非 `ready` 且非 `parse_failed` / `index_failed`；「处理失败」= `parse_failed` 或 `index_failed`；「已完成」= `ready`。

### 4.2 切块

LangChain 按标题切，过长再按字符上限与 overlap 切。**默认** Chunk Size **800**、Overlap **120**。每用户可覆盖：表 `user_chunk_setting`（按 Session 用户）；无行则用默认。切块时按文档所属知识库的 `user_id` 读取配置。成功写入向量后，把**本次所用**的 size/overlap 记在 `document.chunk_size` / `document.chunk_overlap`。表格尽量整块；FAQ 问句与随后段落绑定（启发式）。

**生效边界：** 改配置**不**自动全库 reindex，也**不**改写已有文档上的 `chunk_size` / `chunk_overlap`。只影响该用户之后的新导入、`process_document` / `index_document`、以及用户手动触发的单篇 `reindex`。已向量化切片保持不变，直到该文档被手动 reindex。

### 4.3 检索与问答

- Embedding 与 Chat：OpenAI 兼容 SDK，环境变量配置。Chat 默认 `qwen-plus`。  
- **Embedding 方案（已确认）：** 走 DashScope 兼容接口，**不**改用本机权重（Qwen3-Embedding / BGE 等留作以后若改设计再议）。默认 `EMBEDDING_MODEL=text-embedding-v3`，`EMBEDDING_DIM=1024`。额度用尽、限流或官方提示 v3 不可再调时：**不要自动换模型**；在文档 `error_message` 与接口错误中写明：把 `.env` 的 `EMBEDDING_MODEL` 改为 `text-embedding-v4` 后重启。v4 若仍为 1024 维可只改模型名并 reindex；**改维度必须改库列并全量重建向量**。  
- TopK 默认 5，范围 1～20。  
- **P0/P1：** 最高分余弦 **&lt; 0.30** 或无切片：仍调用 Chat，按普通对话回答，citations 为空；有命中时优先根据资料回答并带引用。只判断 `hits[0]`。  
- **P2 RAG（统一 `search_chunks`，Chat / `POST /api/search` / Agent Tool 共用，禁止 Agent 另写一套）：**  
  1. Hybrid：向量余弦 TopK（pgvector）+ 关键词路 **Elasticsearch BM25**（索引字段含 chunk 正文与 `knowledge_base_id` / `document_id` / `kind` / `chunk_id`，与 Postgres 切片同步写入、删除文档时同步删）。两路 RRF 融合（标准 `1/(60+rank)`，常数 60）。未配置 ES 时行为由该步计划写明（须失败可见，禁止静默退回仅向量却假装 Hybrid）。  
  2. 其后阶段：Rerank（模型/接口在该步计划写明，默认走 DashScope 兼容 rerank，未配置则用 LLM 对候选打分，候选上限 20）。  
  3. 相关性判断：决定是否进入 Context / 是否生成 citations；**不**决定 LLM 是否回答。无相关：Chat 闲聊、Agent 继续、无 Citation。验收锚点：「今天天气不错」对仅有自我介绍笔记的库 **不得**出现 `笔记.md` 引用。逐条门槛环境变量 `RELEVANCE_MIN_SCORE`，暂定默认 **0.5**（Rerank 分），提出人可改。  
  4. 筛选：现有库/标签/`kind`；P2 可加 `created_at` 时间窗。来源用现有 `kind`（`pdf|docx|md|txt|url|note`），不新造 upload/manual/web。  
- **P2 Debug UI（演示页）：** 全站主导航为左侧栏。独立路由 `/debug` 可用演示数据；**不改** Chat/Agent/Report 返回体。  
- **P2 Retrieval Debug（对话页旁路）：** 右上角 Debug 开关（`localStorage`）。不新增 Chat/Agent/Report 一级 Tab，不跳转新页。开则在对话页右侧抽屉展示一次 Query 的向量 / BM25 / RRF / Rerank / Final。`POST /api/retrieval-debug` 单独返回各阶段 Rank/Score；线上 `search_chunks` 与 Chat JSON 不变。可调参数只作用于该请求。Ground Truth 文档级、0–3 分，表 `retrieval_label`（含 `user_id`），评测只认 GT≥2，不算检索分。重新检索不重跑 LLM。  
- 对话页引用展示（API 仍返回切片级 `citations`，前端聚合）：  
  - 气泡「引用来源」按 `document_id` 去重，**只显示文档名、不显示分数**；超过 2 篇先省略。  
  - 右侧「资料来源」按文档分组；组内展示本回答用到的切片正文；同文档多切片合并展示，相关切片链到 `/documents/:id/chunks`。  

- 多轮：最近 **6 条** 消息给 LLM；**检索只用当前句**，不改写。  
- 引用字段：`document_id`、`document_name`、`chunk_id`、`page_start`、`page_end`、`content`、`score`。无页码则页码为 null。  
- 流式 SSE 与非流式语义相同。

### 4.4 搜索 API

`POST /api/search`：走同一 `search_chunks`（P2 起含 Hybrid 内部阶段）。可选 `knowledge_base_id`、`tag_id`、`kind`、`created_after` / `created_before`（文档 `created_at`）。不调 Chat。不传时间则不按时间裁。

### 4.5 标签与收藏

- 标签名在同一 `user_id` 下唯一。文档与标签多对多。  
- 收藏：(`user_id`, `document_id`) 唯一。列表接口可 `?favorite=true`。

### 4.6 笔记

创建/编辑 Markdown 正文，视为一种文档 `kind=note`，走同一切块索引。

### 4.7 P2 Agent 记忆、Checkpoint 与路由

`/api/chat` 仍单链，不进图。P1 `AgentState` 不重建，只按步骤扩展字段。`reason` 是唯一路由节点；Tool 被叫才执行，不自己决定是否调用。

**两层不要画成一棵树。** Checkpoint 不是 `AgentState` 的字段，也不是会话记忆。

图外存储（权威来源）：

| 名称 | 存什么 | 落在哪 |
|---|---|---|
| STM | 本场最近 N=6 条消息 | 现有 `conversation` / `message` |
| Summary | 窗口外历史的中文压缩 | `conversation.summary`（可空） |
| LTM | 跨会话用户事实（背景/偏好/目标） | 独立表 `user_memory`（须含 `user_id`），不是 `message`、不是 `document_chunk` |
| Checkpoint | 某一时刻整份 `AgentState` 快照（图执行到哪、字段是什么） | LangGraph Postgres checkpointer，同一 `DATABASE_URL`；`thread_id` = `conversation_id` 字符串。禁止 Redis |

图内 `AgentState`（本轮给图用的副本）：

- `messages`：本轮从 `message` 表灌入的 STM，**不以** checkpointer 里的旧 `messages` 为聊天权威  
- `summary`：本轮从 `conversation.summary` 读入（Agent-3 起）  
- `ltm_hits`：本轮读到的 LTM 片段（Agent-4 起，可空）  
- 本轮 Tool 结果（`citations` 等）：有上限裁剪，禁止跨轮只增不减  
- 路由字段：`next_action`、`loop_count`、`search_query`；Agent-6 可加有序子任务列表（≤3）

**每次新的 Agent 请求**（新 user 消息）：从 DB 重新加载 STM 与 Summary；`loop_count` 从 0 起；本轮 Tool 结果按该步约定清空或裁剪。禁止把上一轮 checkpoint 中的 `messages` 叠到 STM 上。重启后同一 `thread_id` 仍可 invoke；对话内容仍以表为准。

**reason 渐进（一张图，`max_loops=3` 不放宽）：**

```text
P1 / Agent-1～4     reason → search | generate
P2-Agent-5          reason → DIRECT | RAG | WEB
P2-Agent-6          复杂问句可先写入 ≤3 条子任务；
                    每一圈仍由同一 reason 只选 DIRECT | RAG | WEB
```

- DIRECT = 不调 Tool，走现有 generate  
- RAG = `search_knowledge`（内部 `search_chunks`）  
- WEB = `web_search`（httpx，禁止 Playwright；禁止 RAG 空结果强制 WEB）  
- Agent-6 的 PLAN 不是第四张子图、不是动态 DAG、禁止 Multi-Agent。子任务必须能在 3 圈内跑完，最后 generate 汇总。  
- **智能搜索开关（对话页）：** 仅 Agent / Report 模式、输入框下方显示「智能搜索」。默认关闭。关闭时 `reason` 不得选 WEB、不得调用 `web_search`（仅 DIRECT / RAG）。开启时才允许 WEB。请求体字段 `allow_web`（bool）。Chat 模式无此开关、不调 `web_search`。

---

## 5. 边界

| 情况 | 行为 |
|---|---|
| 未配 API Key | 索引与问答 503 |
| Embedding 额度不足 / v3 不可用 | 索引失败；文案提示改 `EMBEDDING_MODEL=text-embedding-v4` |
| 文档未完成就对该文档问答 | 400 |
| 库内无已完成文档 | 无相关文案 |
| 删除处理中的文档 | 允许，尽力取消任务 |

---

## 6. 数据模型（V1 表）

**users：** id UUID, username UNIQUE, password_hash（Argon2，禁止明文）, timestamps。空表时用 `INITIAL_USERNAME`（默认 echola）与 `INITIAL_PASSWORD`（仅环境变量）创建；已有行不改密码。删除 `app_user`。  

**knowledge_base：** id, user_id FK CASCADE, name, is_default BOOL, is_enabled BOOL（默认真）, timestamps。UNIQUE(user_id, name)。每用户至多一个 is_default。  

**document：** id, knowledge_base_id FK CASCADE, filename, ext, kind, source_url 可空, checksum, status, error_message, byte_size, summary 可空, chunk_size INT 可空, chunk_overlap INT 可空（最近一次成功索引所用参数；未成功索引则为 null）, timestamps。UNIQUE(knowledge_base_id, checksum) 对文件；笔记可无 checksum 或对正文哈希。  

**document_chunk：** id, document_id FK CASCADE, chunk_index, content, page 可空, heading 可空, metadata JSONB, embedding vector(N)。HNSW cosine。  

**tag：** id, user_id FK CASCADE, name。UNIQUE(user_id, name)  

**document_tag：** document_id, tag_id, PK 复合  

**favorite：** PK(user_id, document_id)  

**conversation：** id, user_id FK CASCADE, knowledge_base_id, title, timestamps  

**message：** id, conversation_id, role, content, citations JSONB, created_at  

**P1.4 entity：** id, knowledge_base_id FK CASCADE, name, type（自由短字符串，如 concept/person/tool）, timestamps。UNIQUE(knowledge_base_id, name, type)。  

**P1.4 entity_link：** id, from_id FK CASCADE → entity, to_id FK CASCADE → entity, rel（短字符串）, document_id FK ON DELETE SET NULL 可空, created_at。UNIQUE(from_id, to_id, rel, document_id)。两实体须同库。  

**P2 conversation：** 可加 `summary` TEXT 可空。这是 Summary 的权威存储（本场过长历史压缩；至少 Agent 使用），**不是** Checkpoint。  

**P2 Checkpoint：** LangGraph checkpointer 落**同一** Postgres（禁止 Redis）。`thread_id` = `conversation_id` 字符串。只存 `AgentState` 快照；不替代 `message` / `conversation.summary` / `user_memory`。  

**P2 user_memory（LTM）：** 独立表，**不是** `document_chunk`。字段：id、**user_id**、kind、content TEXT、timestamps。禁止第二套知识库向量集合。读写由 reason 决定后调用内部函数或 Tool；细则在 LTM 那一步计划写死。  

**P2 user_chunk_setting：** user_id PK/FK CASCADE → users.id，chunk_size INT NOT NULL，chunk_overlap INT NOT NULL，timestamps。无行 = 默认 800/120。应用层校验：chunk_size > 0、chunk_overlap ≥ 0、chunk_overlap < chunk_size。不写 `.env`；不改 `users` 表加列。  

**P2 retrieval_label：** id, user_id FK CASCADE, query_norm, knowledge_base_id 可空 FK SET NULL, document_id FK CASCADE, relevance INT 0–3, timestamps。UNIQUE(user_id, query_norm, knowledge_base_id, document_id)。文档级标注。  

不建：fragment_favorite、Neo4j、第二套 **向量** 表。P2 允许本机 Elasticsearch 仅作 BM25 关键词索引。  

---

## 7. API（前缀 `/api`）

认证：`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`。HttpOnly Session Cookie。除 `/health` 与 login 外 `/api/*` 未登录 401。业务查询只用 Session 中的 user_id。`GET /api/me` 删除。无注册接口。  

知识库：`GET/POST /knowledge-bases`，`GET/PUT/DELETE /knowledge-bases/{id}`  

文档：`POST /documents/upload`，`POST /documents/url`，`POST /documents/notes`，`GET /documents`，`GET /documents/{id}`，`GET /documents/{id}/parsed.md`，`DELETE`，`POST .../reindex`  

标签：`GET/POST /tags`，`DELETE /tags/{id}`，`PUT /documents/{id}/tags`  

收藏：`POST /documents/{id}/favorite`，`DELETE /documents/{id}/favorite`  

搜索：`POST /search`  

Retrieval Debug：`POST /retrieval-debug`；`GET/PUT /retrieval-debug/labels`。不改变 Chat/Agent 响应字段。  

切片配置（当前用户）：`GET /chunk-settings`、`PUT /chunk-settings`（body：`chunk_size`、`chunk_overlap`）。身份只来自 Session，禁止请求参数 `user_id`。设置页「调试」面板内、调试模式开启后可改并保存；与 `/debug` 页 localStorage 检索参数分离。`DocumentOut.chunk_size` / `chunk_overlap` 展示该文档**最近一次成功索引所用**参数（可空）；改用户设置不改已有文档这两字段。  

Chat：`POST /chat`，`POST /chat/stream`，会话 CRUD  

P1.4 图谱：`POST /documents/{id}/graph` 抽取并落库；`GET /graph?knowledge_base_id=` 返回该库实体与边的 JSON；`GET /documents/{id}/related` 用 P0 `search_chunks` 给出相近文档（排除本文，不进 LangGraph）。  

---

## 8. 非功能

本机 Postgres+pgvector（已安装，不 Docker）。上传 &lt;1s 返回。检索 &lt;2s。绑定 127.0.0.1。Session 登录。密钥 `.env`。检索 JOIN `knowledge_base.user_id`，禁止全库召回后再在 Python 滤用户。

---

## 9. 验收

1. 默认库存在；上传文本层 PDF → 已完成 → 有 chunk。  
2. 专属问题能答且引用含该文件名。  
3. 点引用打开解析稿。  
4. 无关问题无相关或声明不知道，不出现未检索文件名。  
5. 非默认库文档，未选该库时搜不到。  
6. 公开 URL 成功；假登录墙 URL 失败。  
7. 打标签后可按标签搜到；收藏列表含该文档。  
8. 搜索接口不调用 Chat，结果按相似度排序。  
9. 同文件再传不重复 embedding。  
10. UI 有隐私说明（片段出网）。

---

## 10. 后续工作流

- `memory-bank/tech-stack.md`  
- `memory-bank/implementation-plan.md`  
- `memory-bank/architecture.md` / `progress.md`  
- `PRD-P1.md`（P1 架构与阶段）  
- `PRD-P2.md`（P2 范围）  

实现以本文为准；P1 增量以本文第 1 节 + `PRD-P1.md` 为准；P2 以本文检索/记忆裁决 + `PRD-P2.md` 为准。
