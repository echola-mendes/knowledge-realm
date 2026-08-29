# 知域 — 实施计划

**读者：** 后续执行实现的 AI / 开发者  
**依据：** `memory-bank/design-document.md`、`memory-bank/tech-stack.md`  
**规则：** 一次只做一步；本步验证通过并经提出人确认后，才进入下一步。禁止添加计划外功能。禁止在本文件中编写或粘贴程序代码。  
**执行前必读：** `。

向量维度以环境变量 `EMBEDDING_DIM` 为准，默认 1024。LLM 与 Embedding 一律走 DashScope 兼容端点；禁止要求 OpenAI 账号。

---


## 步骤 P1.2-2 — 文档页触发对比

**指令：** 前端提供选择两篇已完成文档并展示对比结果。走 P1.2-1 接口。不改默认对话为 Agent。

**验证：** 浏览器走通一次；对话页仍走 `/api/chat/stream`。

---

## 步骤 P1.2-3 — 阶段收口

**指令：** 更新 `memory-bank/architecture.md`。`progress.md` 记录 P1.2 通过。不要开始 P1.3。

**验证：** 提出人确认后才开 P1.3。

---

# P1.3 — Agent（LangGraph）

**依据：** `PRD-P1.md`。P1.2 已结束。本阶段引入 LangGraph，**仅**用于 Agent。禁止 Checkpoint、HITL、Subgraph、Multi-Agent。禁止改 `/api/chat`。禁止 Tool 走 HTTP `/api/search`。

**规则：** 一次只做一步；提出人确认后再下一步。`reason` 禁止执行 Tool；`run_tool` 才执行。`max_loops=3`。`task=report` 与 `task=agent` 同一张图。

---

## 步骤 P1.3-0 — 范围已确认

**指令：** 不写代码。确认节点职责、Tool 内部调 `search.py`、SSE 新路径 `/api/agent/stream`。

**验证：** 提出人已允许进入 P1.3。本步仅作计划锚点。

---

## 步骤 P1.3-1 — search_knowledge Tool

**指令：** 新增 `server/app/p1/tools.py`：`search_knowledge` 直接调用现有 `search.py` 的 `search_chunks`，参数与阈值与 P0 一致。禁止 HTTP、禁止第二套向量 SQL、禁止 import LangGraph。本步不建 Graph、不改前端、不改 chat/search 路由。

**验证：** pytest：该函数转发到 `search_chunks`；源码无 `langgraph`、无 `/api/search`、无 `httpx`。

---

## 步骤 P1.3-2 — StateGraph（reason / run_tool / generate）

**指令：** 新增 `server/app/p1/graph.py`：State 含 `knowledge_base_id`、`task`、`messages`、`citations`、`loop_count`、`max_loops=3`。`reason` 只决策；`run_tool` 只执行 `search_knowledge`；Conditional Edge 控制是否再搜；`loop_count >= 3` 必须 generate。不做 Checkpoint。不做 HTTP。

**验证：** pytest 假 LLM：需要检索时经过 run_tool；循环不超过 3。`chat.py` 未被 import LangGraph。

---

## 步骤 P1.3-3 — POST /api/agent（非流式）

**指令：** `POST /api/agent`，body 含 `task`（先支持 `agent`）、`query`、`knowledge_base_id`。走 Graph，不经过 `/api/chat`。缺 Key 503。

**验证：** pytest 假 LLM + 假检索；默认对话接口契约不变。

---

## 步骤 P1.3-4 — POST /api/agent/stream

**指令：** SSE 与非流式最终答案、引用字段对齐（便于点进阅读页）。不经过 `/api/chat/stream`。

**验证：** 收集 SSE 后字段与非流式一致。

---

## 步骤 P1.3-5 — 前端 Agent 入口

**指令：** 另入口或对话页「模式」切换；**默认提问仍为 P0 `/api/chat/stream`**。

**验证：** 浏览器：默认对话仍走旧接口；Agent 模式走 `/api/agent/stream`。

---

## 步骤 P1.3-6 — task=report

**指令：** 同一张 Graph，`task=report` 时 generate 按报告组织。不新开 Graph。

**验证：** pytest：同一模块、不同 task；无第二套 Agent 进程。

---

## 步骤 P1.3-7 — 阶段收口

**指令：** 更新 `architecture.md` 与 `progress.md`。不要开始 P1.4。

**验证：** 提出人确认后才开图谱。

---

# P1.4 — 知识图谱（最小）

**依据：** `PRD-P1.md`。P1.3 已结束。本阶段只做：实体/关系落库、抽取 Chain、知识关联检索、JSON 列表展示。

**禁止：** 力导向/复杂可视化、Neo4j、第二套向量表、把抽取或关联做成 LangGraph、改 `/api/chat`、给 Agent 增加 `search_graph` Tool、Checkpoint/HITL/Subgraph/Multi-Agent。

**规则：** 一次只做一步；提出人确认后再下一步。实体按库隔离。抽取复用 `gather_document_text`。关联只调现有 `search_chunks`。

---

## 步骤 P1.4-0 — 范围已确认

**指令：** 不写功能代码。确认表结构、三个 HTTP、无可视化、无 `search_graph` Tool。

**验证：** 提出人已允许进入 P1.4，并同意下文步骤。本步仅作计划锚点。

---

## 步骤 P1.4-1 — entity / entity_link 表

**指令：** Alembic 新迁移（revision `20260824_0004`，revises `20260824_0003`）。`server/app/models.py` 增加 `Entity`、`EntityLink`，字段与设计文档第 6 节一致：`entity` 含 `knowledge_base_id`、`name`、`type`、timestamps，UNIQUE(knowledge_base_id, name, type)；`entity_link` 含 `from_id`、`to_id`、`rel`、可空 `document_id`（ON DELETE SET NULL）、UNIQUE(from_id, to_id, rel, document_id)；from/to 外键 CASCADE 到 `entity`。删除知识库时实体级联删除。不写 HTTP、不写抽取、不改 chat/search、不做前端。

**验证：** pytest 能在 `echola_kb_test` 插入同库两实体一条边；跨库外键不可用。测完不留用户库数据。

---

## 步骤 P1.4-2 — 抽取 Chain 与 POST /api/documents/{id}/graph

**指令：** 在 `server/app/p1/chains.py` 增加抽取函数（LangChain Chain + 现有 ChatOpenAI）：入参为文档正文，出参为实体列表（name、type）与关系列表（from_name、to_name、rel）。文档须存在且 ready；用 `gather_document_text`；缺 Key 503；空正文 400。按 (knowledge_base_id, name, type) upsert 实体；先删除该 `document_id` 的旧 `entity_link`，再写入新边（同库解析名称；找不到端点则跳过该边）。不调用 LangGraph。不改 `/api/chat`。不做前端。

**验证：** pytest 假 LLM：返回非空实体与边；再抽一次则该文档的边被替换而非无限叠加。本步文件无 `langgraph` import。

---

## 步骤 P1.4-3 — GET /api/graph

**指令：** `GET /api/graph`，query：`knowledge_base_id` 可选（缺省默认库）、`document_id` 可选。返回 JSON：`entities`（id、name、type）、`links`（from_id、to_id、rel、document_id）。若传 `document_id`：只返回该文档的边，以及这些边两端的实体。只读，无布局坐标。不改 chat。不做前端。

**验证：** pytest：抽过的文档能按库列出；按 `document_id` 过滤不含其它文档的边。

---

## 步骤 P1.4-4 — GET /api/documents/{id}/related

**指令：** 文档须存在。用现有 `search_chunks`：query 优先 `document.summary`，否则文件名；`knowledge_base_id` 为该文档所属库；结果去掉本文 `document_id`，按文档去重后最多 5 条。返回 `document_id`、`document_name`、`score`、`content` 片段。不调 LLM。不进 LangGraph。禁止 HTTP 调 `/api/search`。不改 `/api/chat`。不做前端。

**验证：** pytest 假 embedding：同库另一篇相近文档出现；本文不出现在结果里。

---

## 步骤 P1.4-5 — 阅读页展示

**指令：** 阅读页增加「抽取图谱」按钮（走 P1.4-2）以及实体/关系列表（走 P1.4-3，带当前 `document_id`）和「相近文档」列表（走 P1.4-4，可点进另一篇阅读页）。列表/表格即可。禁止力导向图、禁止 vis.js/D3 关系图。不改默认对话为 Agent。

**验证：** 浏览器：ready 文档可抽取并看到实体或空态；相近文档可点击。对话页默认仍走 `/api/chat/stream`。

---

## 步骤 P1.4-6 — 阶段收口

**指令：** 更新 `architecture.md` 与 `progress.md`。不要开始 `search_graph` Tool，不要开始下一版本可视化。

**验证：** 提出人确认后本阶段结束。

---

## P2 — RAG 与 Agent 增强

**依据：** `PRD-P2.md`、`design-document.md` 第 4.3 / 4.7 / 第 6 节 P2 表。  
**规则：** 一次只做一步；禁止在本文件粘贴程序代码。测试库仅 `echola_kb_test`。不放宽 `max_loops=3`。不引入 Redis / 第二套向量表。关键词路为 **Elasticsearch BM25**，不是 `pg_trgm`。

注意：天气问句误引用的验收在 **P2-RAG-3**。P2-RAG-1 只上 Hybrid+RRF，短中文仍可能过线。  
Agent：Checkpoint 与 Summary 分步（Agent-2 / Agent-3）；`reason` 为唯一路由。细则见设计文档第 4.7 节。

---

## 步骤 P2-RAG-1 — Hybrid：向量 + 关键词 + RRF

**指令：** 在现有 `search_chunks` 内增加关键词召回路：**Elasticsearch BM25**（环境变量 `ELASTICSEARCH_URL`）。索引文档与 `document_chunk` 同步：索引写入时 upsert ES 文档（含 content、knowledge_base_id、document_id、kind、chunk_id）；删文档时删除对应 ES 文档。向量路保持现有 pgvector 余弦 TopK。两路各取 k（默认 5，仍受 1～20 限制），用 RRF（`1/(60+rank)`）融合后截断为 k。过滤条件（库、ready、tag、kind、document_id）两路语义相同。调用方（Chat、`POST /api/search`、`search_knowledge`、相近文档）不改签名。本步**不**改 0.30 阈值语义、不得做 Rerank。禁止 Agent 另写检索。禁止把 embedding 写入 ES 当主向量检索。测试可 mock ES；禁止用 `pg_trgm` 代替 BM25。

**验证：** pytest mock ES：关键词能召回对应 chunk 并进入 RRF 结果；库隔离仍成立；`search.py` 仍无第二套向量 SQL、无 `pg_trgm`。提出人确认后再 P2-RAG-2。

---

## 步骤 P2-RAG-2 — Rerank

**指令：** 在 RRF 结果上对最多 20 条候选重排。优先 DashScope 兼容 rerank（新环境变量，无密钥则回退 LLM 打分）。输出仍为 `SearchHit.score`。不改 Chat 拒答语义。不做时间筛选。

**验证：** pytest mock rerank：顺序按假分数变化；无 Key 时走回退且不 500。

---

## 步骤 P2-RAG-3 — 相关性判断（误引用收口）

**指令：** 在 rerank（若已上）或 RRF 之后，用融合/重排分数决定是否整表清空。**逐条**低于阈值的 hit 丢弃；若清空则返回 `[]`。阈值写入配置，默认值须经提出人确认。无命中：Chat 仍闲聊、无 citations；Agent 不强制 Web Search。

**验证：** 假检索：「今天天气不错」类无关查询 citations 为空；「echola是谁」类相关查询仍有命中。真实库手工点对话页确认天气问句无 `笔记.md` 引用。

---

## 步骤 P2-DEBUG-UI — Debug 页与左侧导航

**指令：** 全站顶栏导航改为左侧栏（首页/文档/搜索/对话/Debug/设置）。新增 `DebugView` 对照 RAG Studio 布局：Query、Evaluation K、Vector/BM25/RRF/Rerank 卡片、流水线、结果表、指标表。向量与 BM25 的 TopK 绑定同一 `K`；RRF 为独立 N；Rerank 为独立 M。本步不接真实检索、不改 Chat API。

**验证：** 浏览器打开 `/debug`：左侧可进各页；Debug 页可改 K/N/M、点运行后表格与指标有演示数据。对话页 Chat/Agent/Report 仍在页内。

---

## 步骤 P2-DEBUG-1 — Retrieval Debug（对话页旁路）

**指令：** 不改 Chat/Agent/Report 返回体。扩展 ES/Memory 检索带出 BM25 分数。新增 `search_debug` 与 `POST /api/retrieval-debug`（可调 vector/bm25/rrf/rerank TopK、向量阈值、RRF 常数）。向量第一名低于阈值仍记录向量阶段。表 `retrieval_label`（user_id、规范化 query、knowledge_base_id、document_id、relevance 0–3）。`GET/PUT /api/retrieval-debug/labels`。前端：对话页 Debug 开关 + 可折叠 Retrieval Debug 抽屉；OFF 不展示内部 score 与 GT。评测 Recall@K / Precision@K 按 Final 文档去重序、只认 GT≥2。

**验证：** pytest：chat JSON 字段不变；debug 含四阶段 + Final；假 GT 下指标正确。浏览器：开 Debug 提问可见各阶段；改 TopK 重新检索不改气泡；关 Debug UI 复原。

---

## 步骤 P2-CHUNK-1 — 用户级 Chunk Size / Overlap

**指令：** 迁移表 `user_chunk_setting`（user_id PK/FK CASCADE，chunk_size，chunk_overlap，timestamps）。`split_markdown(text, *, chunk_size, chunk_overlap)`；默认常量仅作无行时的 800/120。`get_user_chunk_settings(session, user_id)`；`index_document` 与文档预览切块经 `document → knowledge_base.user_id` 取配置；成功索引时把所用参数写入 `document.chunk_size` / `chunk_overlap`（迁移 `20260828_0014`，ready 历史行回填 800/120）。`DocumentOut` 展示文档上存的值，禁止用当前用户设置覆盖。`GET/PUT /api/chunk-settings`（Session 用户，禁止 body/query `user_id`）；PUT 不改 document 行、不 reindex。设置页「调试」同一 panel：调试模式开启后显示 Chunk Size、Overlap + 保存切片配置；开启时 GET 回填；`/debug` 页不放切片配置。去掉 Debug 页初始「点运行后检索…不是演示文档」hint。与 `/debug` localStorage「保存配置」（K/N/M）分离。改配置不自动全库 reindex；只影响之后新导入与单篇 reindex。不改 Chat/Agent 返回体；不做 `search_graph` / 可视化。

**验证：** pytest：无行默认 800/120；PUT 后同用户切块/索引 mock 用新值；另一用户仍默认；改配置不改动未 reindex 文档的 chunk 行，也不改该文档 `chunk_size`/`chunk_overlap`；单篇 reindex 后文档两字段为新配置。浏览器：`/settings` 开调试后同 panel 可见两项；关调试不可见；`/debug` 无切片配置卡片；保存设置后文档列表 Size/Overlap 不随当前设置联动；无上述演示 hint。

---

## 步骤 AUTH-1 — 基础登录与用户数据隔离

**指令：** 按设计文档：表 `users`（Argon2）；HttpOnly Session；`POST /api/auth/login|logout`、`GET /api/auth/me`。`knowledge_base`/`conversation`/`tag`/`favorite` 加 `user_id`；文档与切片经库继承。历史数据归初始用户。禁止 query `user_id`。`search_chunks` 必参 `user_id` 并 JOIN `knowledge_base`。独立 `/login` 页。无 RBAC/OAuth/JWT。密码只来自 `INITIAL_PASSWORD`。

**验证：** 未登录 `/api/*` 401；登录后只见本人库；检索 JOIN 过滤，跨用户文档 404。pytest 覆盖。

---

## 步骤 P2-RAG-4 — 时间筛选（来源用 kind）

**指令：** `search_chunks` 增加可选 `created_after` / `created_before`（文档 `created_at`）。`POST /api/search` 与搜索页可传。来源继续用现有 `kind`，不新增枚举。不改 Chat 默认（不传时间则全库）。

**验证：** pytest：窗外文档不出现；kind 过滤仍可用。

---

## 步骤 P2-Agent-1 — Agent 短期记忆

**指令：** `AgentRequest` 增加可选 `conversation_id`。无则新建 `conversation`（与 Chat 同表）。将最近 N=6 条 `message` 写入 `AgentState.messages` 再跑图。`generate` 把历史交给现有 `llm.chat`。落库本轮 user/assistant。图结构保持 P1：`reason` → search | generate。不引入 Summary、Checkpoint、LTM、WEB、PLAN。不改 `/api/chat` 进图。

**验证：** pytest：第二轮带同一 `conversation_id` 时假 LLM 收到上轮内容；无第二套会话表。

---

## 步骤 P2-Agent-2 — Checkpoint

**指令：** `graph.compile` 使用 Postgres checkpointer（同一数据库）。`thread_id` 为 `conversation_id`。Checkpoint **只**保存图快照（这一次执行到哪、当前 `AgentState`），**不**替代 STM。每次新 user 请求：从 `message` 表重新灌最近 6 条；`loop_count` 从 0；本轮 citations/tool 结果按上限裁剪或清空，避免与上一轮快照叠两份聊天、避免只增不减。禁止 Redis。禁止在本步做 Conversation Summary。

**验证：** pytest 或可重复脚本：同一 `thread_id` 可第二次 invoke；prompt 所用近期消息与 DB 中最近消息一致，而不是未重置的上一轮 `messages` 全量。重启后仍能对同一 `conversation_id` invoke。

---

## 步骤 P2-Agent-3 — Conversation Summary

**指令：** 与 Checkpoint 分家：`conversation.summary` 可空，这是摘要权威存储。消息超过 N=6 时，对更早消息生成中文摘要并**写入该列**；Agent 上下文 = `conversation.summary` + 最近 6 条。State 可带已加载的 `summary` 字符串，但不得只把摘要写进 checkpointer。Chat 本步可不改。

**验证：** pytest 假 LLM：超过 6 条时 prompt 含摘要且不含被压缩的原文全量；`conversation.summary` 非空。

---

## 步骤 P2-Agent-4 — Long-term Memory 表

**指令：** 迁移 `user_memory`（id、**user_id**、kind、content、timestamps）。本轮读到的内容可放入 State 的 `ltm_hits`；表才是权威。读写由 `reason` 决定后走内部函数或 Tool，禁止 Tool 擅自在未路由时读写。禁止写入 `document_chunk`。禁止第二套知识库向量表。

**验证：** pytest：写入后新会话（不同 conversation_id）仍能读到；源码无把 LTM 当 chunk 检索。

---

## 步骤 P2-Agent-5 — web_search 与统一路由

**指令：** `p1/tools.py` 增加 `web_search`（httpx，超时有上限；配置搜索端点；禁止 Playwright）。扩展现有 `reason` 为唯一路由：`DIRECT`（generate）/ `RAG`（`search_knowledge`）/ `WEB`（`web_search`）。`run_tool` 只执行 `reason` 指定的那一个。禁止检索空结果时强制 WEB。禁止本步增加 PLAN / 子任务列表。`max_loops` 仍为 3。

**验证：** pytest mock httpx：reason 指定 WEB 时调用；空 citations 不自动 web；未指定时 `web_search` 不被调用。

---

## 步骤 P2-Agent-6 — 轻量 Planning

**指令：** 仍一张图、仍同一 `reason`。复杂问句可先写入最多 3 条有序子任务（与 `max_loops` 对齐）；之后每一圈 `reason` 仍只选 DIRECT / RAG / WEB 执行当前子任务，最后 generate 汇总。禁止第四张子图、禁止动态 DAG、禁止 Multi-Agent、不提高 loop 上限。

**验证：** pytest：拆出的子任务数 ≤ 3；图仍一张；无第二套 Graph 模块。

---

## 步骤 P2-7 — 阶段文档收口

**指令：** 更新 `architecture.md`、`progress.md`。不要开始 P3（冲突/缺口/多 Agent/库自动更新）、不要 `search_graph` 可视化。

**验证：** 提出人确认 P2 结束。

---

## 步骤 KB-ENABLE — 检索默认已开启库

**指令：** `knowledge_base` 增加 `is_enabled`（默认 true）。知识库管理可开关。未传 `knowledge_base_id` 时搜索/对话/Agent 只打当前用户已开启库；传了 id 仍单库。导入与文档列表仍用指定库或默认库。ES 关键词过滤与向量路同一组库 id。

**验证：** pytest：两库都开启、不传 id 可跨库命中；关闭一库后该库不再被无 id 检索命中；传 id 仍隔离。

---

## 步骤 AGENT-SMART-SEARCH — Agent/Report「智能搜索」开关

**指令：** 对话页仅在 Agent / Report 模式、输入框下方显示「智能搜索」开关（默认关）。`AgentRequest.allow_web: bool`（默认 false）。关：`reason` 不得选 WEB，`run_tool` 不得调用 `web_search`。开：行为与现有 P2-Agent-5 一致（可 DIRECT / RAG / WEB）。不改 Chat。不强制 WEB。本步不要求网页来源单独 UI（可后续加）。

**验证：** pytest：`allow_web=false` 时即使 reason 返回 web 也不调用 `web_search`；`allow_web=true` 时 WEB 路径仍可调用。浏览器：Chat 无开关；Agent/Report 有开关。

---

## 执行纪律

- 每步结束后等待提出人确认，再开始下一步。  
- 发现与设计不符：停止实现，先改设计文档并征得同意。  
- 本计划含「验证」所述测试；步骤 20–22 允许以提出人手工验收为主，但 0–19 能自动化的必须自动化。  
- **P1：** 已收口。  
- **P2：** 已确认结束（PRD-P2 §7；阈值保持 0.5）。  
- **当前：** **AGENT-SMART-SEARCH**（进行中）。KB-ENABLE 代码已验证、待提出人确认。P2-DEBUG-UI 待看 UI。P2-DEBUG-1 / AUTH-1 代码已写。确认后勿擅自开 P3。
