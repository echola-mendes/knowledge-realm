# 知域 — 产品设计文档

**状态：** 可执行  
**依据：** 仓库 `PRD.md`（P0 已确认）；P1 见 `PRD-P1.md`；P2 范围见 `PRD-P2.md`（提出人已确认边界修正）  
**产品名称：** 知域  
**用户：** 单人；Web；本机为主  

---

## 1. 设计裁决

| 项 | 裁决 |
|---|---|
| V1 范围 | **P0 已完成**。P1.1–P1.4 已完成。**P2** 见 `PRD-P2.md`：未写进 `implementation-plan.md` 的步骤不要做代码。不要开始 `search_graph` Tool 或力导向可视化。Agent 记忆分层见第 4.7 节：Checkpoint ≠ Summary |
| 编排 | **P0：** LangChain 单链 RAG；`/api/chat` 不进图。**P1 Agent：** 允许 LangGraph，且必须经 Tool 调用 P0 检索。摘要/标签/对比只用 Chain。不上 LlamaIndex |
| 解析 | 不上 MinerU。PDF = PyMuPDF 文本层；DOCX = python-docx；MD/TXT/笔记 = 直读；URL = 抓公开页正文 |
| 检索 | **P0/P1：** pgvector 余弦（方案 A），`search_chunks` 最高分 &lt; 0.30 整次为空（只卡第一名）。**P2：** 同一入口内 Hybrid（向量 + **Elasticsearch BM25 关键词**）→ RRF →（后阶段）Rerank → 相关性判断；无相关不引用、Chat 不拒答。向量仍只在一张 `document_chunk`；ES **只做关键词 BM25**，禁止把 ES 当第二套向量库 |
| 知识库 | 可多个；启动时若不存在则创建名为 `默认知识库` 的记录。未传 `knowledge_base_id` 时只用默认库 |
| 用户 | 占位一行 `app_user`（`name=echola`）。仍无登录。不给其它表加 `user_id`。顶栏最右侧显示名称与字母头像 |
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

MinerU、LlamaIndex、Ollama、Milvus、多用户、扫描件 OCR、`.doc`、登录墙网页、Meilisearch。P0 路径不上 LangGraph。知识冲突/缺口/整理/推荐、Multi-Agent、知识库自动更新属 **P3**。Web Search、Checkpoint、**Elasticsearch BM25 关键词**属 **P2**（见 `PRD-P2.md`）。

**收藏片段：** V1 只收藏文档。

**P1：** 不重构 P0；旧 RAG 不进图。细则 `PRD-P1.md`。

---

## 3. 用户旅程

### 3.1 主路径

打开 Web → 见隐私说明 → 向默认库上传带文本层的 PDF → 状态至「已完成」→ 提问 → 回答带文件名与页码 → 点引用打开解析页。

### 3.2 默认库

不选库时问答与搜索只命中默认知识库。选「Java」库则只命中该库。

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
- 状态对用户：**处理中 / 已完成 / 处理失败**。内部可映射 `pending|parsing|indexing|ready|parse_failed|index_failed`。仅「已完成」参与检索。

### 4.2 切块

LangChain 按标题切，过长再 **800 字符 / overlap 120**。表格尽量整块；FAQ 问句与随后段落绑定（启发式）。

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
- 对话页仅在有引用时于气泡下方列出；超过 2 条先显示省略。 

- 多轮：最近 **6 条** 消息给 LLM；**检索只用当前句**，不改写。  
- 引用字段：`document_id`、`document_name`、`chunk_id`、`page_start`、`page_end`、`content`、`score`。无页码则页码为 null。  
- 流式 SSE 与非流式语义相同。

### 4.4 搜索 API

`POST /api/search`：走同一 `search_chunks`（P2 起含 Hybrid 内部阶段）。可选 `knowledge_base_id`、`tag_id`、`kind`。P2 可增加时间窗参数（`created_at`）。不调 Chat。

### 4.5 标签与收藏

- 标签名全局唯一（个人单用户）。文档与标签多对多。  
- 收藏：用户-文档，唯一约束。列表接口可 `?favorite=true`。

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
| LTM | 跨会话用户事实（背景/偏好/目标） | 独立表 `user_memory`，不是 `message`、不是 `document_chunk` |
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
- Agent-6 的 PLAN 不是第四张子图、不是动态 DAG、不是 Multi-Agent。子任务必须能在 3 圈内跑完，最后 generate 汇总。

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

**app_user：** id, name UNIQUE, phone UNIQUE 可空, timestamps。启动时空表插入 `name=echola`；已有行不改。  

**knowledge_base：** id, name UNIQUE, is_default BOOL, timestamps  

**document：** id, knowledge_base_id FK CASCADE, filename, ext, kind, source_url 可空, checksum, status, error_message, byte_size, summary 可空, timestamps。UNIQUE(knowledge_base_id, checksum) 对文件；笔记可无 checksum 或对正文哈希。  

**document_chunk：** id, document_id FK CASCADE, chunk_index, content, page 可空, heading 可空, metadata JSONB, embedding vector(N)。HNSW cosine。  

**tag：** id, name UNIQUE  

**document_tag：** document_id, tag_id, PK 复合  

**favorite：** document_id UNIQUE（单用户）  

**conversation：** id, knowledge_base_id, title, timestamps  

**message：** id, conversation_id, role, content, citations JSONB, created_at  

**P1.4 entity：** id, knowledge_base_id FK CASCADE, name, type（自由短字符串，如 concept/person/tool）, timestamps。UNIQUE(knowledge_base_id, name, type)。  

**P1.4 entity_link：** id, from_id FK CASCADE → entity, to_id FK CASCADE → entity, rel（短字符串）, document_id FK ON DELETE SET NULL 可空, created_at。UNIQUE(from_id, to_id, rel, document_id)。两实体须同库。  

**P2 conversation：** 可加 `summary` TEXT 可空。这是 Summary 的权威存储（本场过长历史压缩；至少 Agent 使用），**不是** Checkpoint。  

**P2 Checkpoint：** LangGraph checkpointer 落**同一** Postgres（禁止 Redis）。`thread_id` = `conversation_id` 字符串。只存 `AgentState` 快照；不替代 `message` / `conversation.summary` / `user_memory`。  

**P2 user_memory（LTM）：** 独立表，**不是** `document_chunk`。建议字段：id、kind（短字符串如 profile/preference/goal）、content TEXT、timestamps。单用户仍不给 `user_id`。禁止第二套知识库向量集合。读写由 reason 决定后调用内部函数或 Tool；细则在 LTM 那一步计划写死。  

不建：fragment_favorite、Neo4j、第二套 **向量** 表。P2 允许本机 Elasticsearch 仅作 BM25 关键词索引。  

---

## 7. API（前缀 `/api`）

当前用户：`GET /me`（`name=echola` 那一行；没有则 404）。无登录、无创建。  

知识库：`GET/POST /knowledge-bases`，`GET/PUT/DELETE /knowledge-bases/{id}`  

文档：`POST /documents/upload`，`POST /documents/url`，`POST /documents/notes`，`GET /documents`，`GET /documents/{id}`，`GET /documents/{id}/parsed.md`，`DELETE`，`POST .../reindex`  

标签：`GET/POST /tags`，`DELETE /tags/{id}`，`PUT /documents/{id}/tags`  

收藏：`POST /documents/{id}/favorite`，`DELETE /documents/{id}/favorite`  

搜索：`POST /search`  

Chat：`POST /chat`，`POST /chat/stream`，会话 CRUD  

P1.4 图谱：`POST /documents/{id}/graph` 抽取并落库；`GET /graph?knowledge_base_id=` 返回该库实体与边的 JSON；`GET /documents/{id}/related` 用 P0 `search_chunks` 给出相近文档（排除本文，不进 LangGraph）。  

---

## 8. 非功能

本机 Postgres+pgvector（已安装，不 Docker）。上传 &lt;1s 返回。检索 &lt;2s。绑定 127.0.0.1。无登录。密钥 `.env`。

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
