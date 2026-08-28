# 知域 — 实施计划

**读者：** 后续执行实现的 AI / 开发者  
**依据：** `memory-bank/design-document.md`、`memory-bank/tech-stack.md`  
**规则：** 一次只做一步；本步验证通过并经提出人确认后，才进入下一步。禁止添加计划外功能。禁止在本文件中编写或粘贴程序代码。  
**执行前必读：** `AGENTS.md`、`memory-bank/architecture.md`、`memory-bank/design-document.md`。

向量维度以环境变量 `EMBEDDING_DIM` 为准，默认 1024。LLM 与 Embedding 一律走 DashScope 兼容端点；禁止要求 OpenAI 账号。

---

## 步骤 0 — 本机数据库就绪

**指令：** 确认本机 PostgreSQL 已运行且已启用 pgvector。创建空库，名称必须为 `echola_kb`。不要用 Docker 再起一套 Postgres。

**验证：** 能连接到该库，并确认扩展 `vector` 可用（查询扩展列表中存在 `vector`）。把连接串格式记入稍后的 `.env.example` 说明中（本步尚不必写应用代码）。

---

## 步骤 1 — 仓库骨架与忽略规则

**指令：** 建立目录 `server/`、`web/`、`data/files/`、`data/parsed/`。添加根目录忽略规则：虚拟环境、`node_modules`、`.env`、`data/` 下用户文件、Python/前端缓存。提供 `.env.example`，列出技术栈文档中的全部环境变量名与含义，**不填写真实密钥**。`DATA_DIR` 默认指向仓库 `data/`。

**验证：** 目录存在；忽略规则包含 `.env` 与 `data/`；`.env.example` 含 `DATABASE_URL`、`LLM_*`、`EMBEDDING_*`、`DATA_DIR`，且注明 Key 来自 DashScope、Base URL 为兼容模式地址。

---

## 步骤 2 — Python 环境与依赖清单

**指令：** 使用 `server/.venv`（`python3.12 -m venv`，不用 conda）。用 `server/requirements.txt` 锁定依赖：FastAPI、Uvicorn、Pydantic v2、python-dotenv、SQLAlchemy 2、Alembic、psycopg（binary）、pgvector、LangChain 切块与 openai 对接、PyPI 包 `openai`、pymupdf、python-docx、httpx、trafilatura、pytest。禁止 MinerU、LlamaIndex、LangGraph、Celery、Redis。

**验证：** 全新安装依赖成功。依赖文件中不出现被禁止的包名。能够导入 FastAPI、SQLAlchemy、langchain 切块相关模块、pymupdf、trafilatura。

---

## 步骤 3 — 配置加载

**指令：** 实现启动时读取环境变量；缺 `DATABASE_URL` 则拒绝启动。缺 LLM/Embedding Key 时允许启动（便于测知识库 CRUD），但后续索引与问答须返回 503。校验 `EMBEDDING_DIM` 为正整数。监听地址固定为本机回环。

**验证：** 自动化测试：缺少 `DATABASE_URL` 时启动失败；配齐数据库后可以启动；未配 LLM Key 时健康检查仍可通过（若本步尚无健康检查，则至少配置对象能创建且标记「LLM 未配置」）。

---

## 步骤 4 — 数据库迁移与表结构

**指令：** 用 Alembic 建立迁移。表与字段必须与设计文档第 6 节一致：`knowledge_base`、`document`、`document_chunk`（含 `vector` 列与 HNSW 余弦索引）、`tag`、`document_tag`、`favorite`、`conversation`、`message`。外键级联与 UNIQUE 约束按设计。不要创建 entity/relation 表。

**验证：** 对空库执行迁移成功。用数据库工具或只读查询确认八张表存在、`document_chunk.embedding` 为 vector 类型、HNSW 索引存在、`knowledge_base.name` 唯一、`document` 上知识库+checksum 唯一、`favorite.document_id` 唯一。

---

## 步骤 5 — 默认知识库

**指令：** 应用启动时：若没有任何知识库，插入一条，名称为「默认知识库」，`is_default` 为真。保证任意时刻至多一个默认库。提供内部方法：未指定 id 时解析为默认库 id。

**验证：** pytest：空库启动后恰好一条默认知识库；再启动不会重复插入。删除全部库后再启动会再次创建默认库。

---

## 步骤 6 — 知识库 HTTP API

**指令：** 实现设计文档第 7 节知识库接口：列表、创建、获取、改名、删除。删除须级联文档、切片，并删除该库文档对应的本地 `data/files` 与 `data/parsed` 目录。名称冲突返回明确错误。路径前缀 `/api`。

**验证：** pytest + 测试客户端：创建两个库；列表含默认库与新库；改名成功；删除非默认库后文档与磁盘文件消失；重名创建失败。未指定库的后续接口将在后步验证「落到默认库」。

---

## 步骤 7 — 文件落盘与校验（尚不解析）

**指令：** `POST /api/documents/upload`：可选知识库 id，缺省默认库。校验扩展名仅 pdf/docx/md/markdown/txt（大小写不敏感），超过 100MB 拒绝。计算 SHA-256。原件写到 `data/files/{年}/{文档id}{扩展名}`。写入 `document` 行，状态为处理中。接口须在 1 秒量级返回，不要在请求线程里做解析。同库相同 checksum：不新建行，返回已有文档并说明已存在。

**验证：** 上传合法 txt 得到 2xx 与文档 id，磁盘上有原件。上传 `.exe` 得 400。超大文件策略可用较小上限的测试夹具或 mock 体积字段，断言拒绝逻辑。同一文件连续上传两次，第二次不新增 `document` 行。无知识库 id 时 `knowledge_base_id` 等于默认库。

---

## 步骤 8 — 文本类解析（md / txt）

**指令：** 后台任务：对 md/txt 以 UTF-8 读取，写出 `data/parsed/{id}/document.md` 与仅含文本结构的 `document.json`。无页码。空内容则失败状态，原因 `empty_content`。超时 60 秒。成功则进入「解析完成、待索引」内部态（对用户仍可显示处理中，直到索引结束；若简化，解析后立即进入索引步骤，见步骤 11）。本步可先将状态置为内部 `parsed`。禁止 OCR 与 MinerU。

**验证：** 上传非空 txt，处理后存在 `document.md` 且内容与原文一致。上传仅空白的 txt，状态为处理失败且原因含 `empty_content`。pytest 可同步调用解析函数而不依赖真实后台时序。

---

## 步骤 9 — PDF 与 DOCX 解析

**指令：** PDF 用 PyMuPDF 按页抽文本，Markdown 中每页二级标题为 Page 加从 1 开始的页码。DOCX 用 python-docx 按段落拼接，无页码。同样写 md/json。抽空则失败。超时 60 秒。

**验证：** 用夹具生成「至少一页可选中文字」的 PDF，解析后 md 含 Page 1 且含该文字。用夹具 docx 含两段可见文字，解析后 md 含该两段。无文本层或空 PDF 失败。测试目录禁止引入 MinerU。

---

## 步骤 10 — 切块

**指令：** 用 LangChain 文本切分：优先按 Markdown 标题；过长再按 800 字符、重叠 120 字符。尽量保持表格整段；问号结尾行与随后段落绑定。输出块带 page、heading（能取则取）。本步只入内存或临时结构，或先写入不含 embedding 的行——二选一但须在步骤 11 补全向量。禁止 LlamaIndex。

**验证：** 对一篇含两个标题、总长超过 800 字的 Markdown 运行切分：块数大于 1，每块长度不超过约定上限（最后一块除外可更短），重叠可从相邻块前缀/后缀人工抽查。空文档得到零块并应在索引阶段失败。

---

## 步骤 11 — Embedding 写入与索引完成

**指令：** 调用 Embedding（DashScope 兼容，模型与维度按配置，默认 v3）。批量请求，失败重试两次后文档 `index_failed`。成功写入 `document_chunk.embedding`，文档状态「已完成」。仅已完成文档可被检索。未配置 Key 时索引返回 503 且状态失败原因说明缺密钥。checksum 命中的重复上传不得再次调用 Embedding。识别额度不足 / v3 停用类错误时，失败原因须提示将 `EMBEDDING_MODEL` 改为 `text-embedding-v4`，禁止自动改模型。

**验证：** 自动化测试用假 Embedding（固定向量）完成索引：chunk 行数大于 0，状态已完成。模拟 Key 缺失得 503。假 Embedding 计数器：第二次上传同文件调用次数为零。不要在本步接真实 DashScope（可另附手工项）。

---

## 步骤 12 — 重新处理与删除文档

**指令：** `POST /api/documents/{id}/reindex`：删除该文档旧切片后从解析重新走完。`DELETE` 文档：删库行（级联切片）、删本地 files/parsed。允许删除处理中的文档。列表与详情接口返回状态、错误信息、来源（路径或 URL）。

**验证：** 文档已完成后改磁盘解析源再 reindex（或 mock 解析输出变化），切片内容更新。删除后 GET 404，磁盘目录不存在。列表能看到失败原因字段。

---

## 步骤 13 — 笔记与 URL 导入

**指令：** `POST /api/documents/notes`：创建 kind=note 的文档，正文为 Markdown，checksum 用正文哈希，随后切块索引。`POST /api/documents/url`：httpx 20 秒超时取公开页，trafilatura 抽正文；失败则文档失败；成功则快照写入 parsed 并索引。source_url 保存原始 URL。禁止浏览器自动化。

**验证：** 创建非空笔记后状态可到已完成且有切片。URL 测试：对本地 httpx mock 返回一篇带标题正文的 HTML，导入成功且 md 含正文；mock 空 body 或超时则失败。不启动 Playwright。

---

## 步骤 14 — 标签

**指令：** 标签名唯一。创建、列表、删除标签。给文档设置标签列表（覆盖式）。删除标签时中间表行消失。GET 文档列表支持按 `tag_id` 过滤（本步列表过滤即可；搜索接口在步骤 16 再接向量）。

**验证：** 创建标签、打到文档、列表按标签只返回该文档。删除标签后文档不再带该标签。重名标签失败。

---

## 步骤 15 — 收藏

**指令：** 收藏/取消收藏文档。同一文档只能收藏一次。`GET /api/documents?favorite=true` 只返回已收藏。

**验证：** 收藏后列表可见；再收藏不复制行（或返回已收藏）；取消后列表为空。删除文档后面收藏记录不残留（外键或显式删除）。

---

## 步骤 16 — 向量搜索 API

**指令：** `POST /api/search`：对 query 做 embedding；SQL 按余弦距离排序取 TopK；只包含已完成文档。可选过滤：知识库（缺省默认库）、tag_id、kind。返回片段与文档摘要、分数。最高分低于 0.30 可返回空列表（搜索不调用 Chat）。禁止写第二套向量表。禁止全文检索。

**验证：** 用假 Embedding：库 A 一篇「苹果」、库 B 一篇「橙子」；在默认库/A 搜「苹果」只命中 A。带 tag 过滤只命中打了该标签的文档。kind=note 不返回 pdf。断言测试过程中 Chat/LLM 调用次数为零。分数按相似度降序。

---

## 步骤 17 — RAG 问答（非流式）

**指令：** `POST /api/chat`：解析知识库（缺省默认）、可选 document_id 与 k。检索逻辑与步骤 16 相同。无命中或最高分低于 0.30：仍调用 LLM 作普通对话，citations 为空。有命中：LangChain 单链，优先根据资料回答、禁止编造出处；返回设计规定的 citations 字段。无 conversation_id 则新建会话，title 为问题前 40 字。未完成文档作为 document_id 时 400。未配 Key 且需要 LLM 时 503。禁止 LangGraph 与问题改写。

**验证：** 假 LLM + 假 Embedding：有相关切片时答案来自假 LLM 且 citations 含正确 document_name。无关查询（分数压到阈值下）仍调用假 LLM，citations 为空。指定 document_id 指向处理中文档得 400。指定库 B 时不得出现库 A 的文件名。

---

## 步骤 18 — 多轮与流式

**指令：** 会话列表、消息列表、删除会话。问答将最近 6 条历史（不含系统）发给 LLM；检索仍只用当前问题。`POST /api/chat/stream` 用 SSE 输出与非流式相同的最终答案与引用（可先流式 token 再发 citations 事件，但字段集合必须一致）。客户端断开时尽力取消生成。

**验证：** 连续两轮：第二轮请求体带 conversation_id，发给假 LLM 的消息列表含第一轮问答。流式测试：收集 SSE 后拼接文本与非流式答案一致（假 LLM 固定输出）。删除会话后 GET 消息 404。

---

## 步骤 19 — 前端工程与代理

**指令：** 在 `web/` 用 Vite + Vue 3 + TypeScript 初始化。路由：首页、文档列表、搜索、对话、文档阅读、设置。开发服务器把 `/api` 代理到 FastAPI 本机端口。朴素样式即可。

**验证：** `npm` 安装与类型检查通过。浏览器打开开发地址能看到壳页面。代理：前端请求 `/api/knowledge-bases` 能打到后端（可用浏览器或 curl 经代理端口）。

---

## 步骤 20 — 前端：库、文档、上传、笔记、URL

**指令：** 页面可切换知识库（含默认）。上传文件、提交 URL、创建笔记。列表展示状态与失败原因、重新处理、删除。阅读页请求解析 Markdown 并渲染。隐私说明固定展示：片段会发往所配置的第三方 AI。

**验证：** 提出人手工：上传 txt 看到处理中变为已完成；打开阅读页能看到正文。失败文档能看到原因并点重新处理。隐私文案可见。本步不要求自动化 E2E。

---

## 步骤 21 — 前端：标签、收藏、搜索、问答

**指令：** 打标签、收藏列表。搜索页调用搜索 API，结果按分数列出，不经过「生成长答案」。对话页支持流式显示、引用列表；点击引用跳到阅读页并尽量定位到对应标题或 Page。首页：提问框、文档数/库数/标签数、最近文档、最近对话。设置页只显示是否已配置密钥、不回显明文 Key。

**验证：** 手工按设计第 9 节第 2、3、7、8、10 条走通。搜索结果页不得出现完整 LLM 长文（仅列表）。引用可点击。提出人确认后在 `progress.md` 记录本步完成。

---

## 步骤 22 — 对照设计第 9 节总验收

**指令：** 使用真实 DashScope Key（提出人本机 `.env`）与一份带文本层的 PDF、一个公开 URL、一个故意失败的 URL，按设计文档第 9 节十条逐项打勾。缺项只修缺陷，不开新功能。

**验证：** 十条全部通过。更新 `memory-bank/architecture.md`，写上真实文件路径与职责。在 `memory-bank/progress.md` 追加总验收通过记录。

---

# P1.1 — 智能摘要与自动标签

**依据：** `PRD-P1.md`。P0 步骤 0–22 已结束。本阶段**禁止** LangGraph、文档对比、Agent、研究报告、知识图谱。

**规则：** 一次只做一步；提出人确认后再下一步。不改 `/api/chat` 与 `/api/search` 契约。不重构 P0 切块与 embedding。

---

## 步骤 P1.1-0 — 设计已确认

**指令：** 不写代码。确认 `PRD-P1.md`、`design-document.md` 编排裁决、`AGENTS.md` 与本文 P1.1 范围一致。

**验证：** 提出人已确认 11 条边界。本步仅作计划锚点。

---

## 步骤 P1.1-1 — 摘要 Chain 与持久化

**指令：** 新增 `server/app/p1/chains.py`：对指定已完成文档，用现有 chunk（无则解析稿）生成摘要（LangChain Chain + DashScope ChatOpenAI）。结果写入 `document.summary`。`POST /api/documents/{id}/summarize`。处理中/失败文档 400。未配 Key 503。不调用 LangGraph。不改 chat / search 路由。

**验证：** pytest：假 LLM 下 ready 文档得到非空摘要并可再 GET 到；非 ready 为 400。`grep` 或测试保证本步文件无 `langgraph` import。

---

## 步骤 P1.1-2 — 文档页展示与触发摘要

**指令：** 阅读页或文档详情提供「生成摘要」并展示已有摘要。走 P1.1-1 接口。不改默认对话为 Agent。

**验证：** 浏览器：对一篇已完成文档点生成后可见摘要；对话页提问仍走 `/api/chat/stream`。

---

## 步骤 P1.1-3 — 自动标签 Chain

**指令：** Chain 根据文档内容提出标签名；只创建尚不存在的 `tag`（或复用同名）并**追加** `document_tag`；不得删除用户已打标签。`POST /api/documents/{id}/auto-tags`。同样 400/503 规则。无 LangGraph。

**验证：** pytest：已有标签 A 时自动打标后 A 仍在，并可能增加新标签。非 ready 400。

---

## 步骤 P1.1-4 — 文档页触发自动标签

**指令：** 文档页提供「自动标签」；完成后列表标签更新。用户仍可手改/删除标签（P0 行为保留）。

**验证：** 浏览器走通一次；手打标签不被清空。

---

## 步骤 P1.1-5 — 阶段收口

**指令：** 更新 `memory-bank/architecture.md` 真实 P1.1 路径。`progress.md` 记录 P1.1 通过。不要开始 P1.2/P1.3。

**验证：** 提出人确认后才开下一阶段。

---

# P1.2 — 文档对比

**依据：** `PRD-P1.md`。P1.1 已结束。本阶段**禁止** LangGraph、Agent、研究报告、知识图谱。

**规则：** 一次只做一步；提出人确认后再下一步。不改 `/api/chat` 与 `/api/search` 契约。不重构 P0 切块与 embedding。对比结果不落库。

---

## 步骤 P1.2-0 — 范围已确认

**指令：** 不写代码。确认对比 = 两篇 `document_id` 的 LangChain Chain；`POST /api/compare`；两篇须同库且均为 ready。

**验证：** 提出人已允许进入 P1.2。本步仅作计划锚点。

---

## 步骤 P1.2-1 — 对比 Chain 与 API

**指令：** 在 `server/app/p1/chains.py` 增加对比 Chain（复用 `gather_document_text`）。`POST /api/compare`，body 为两篇文档 id。两篇须存在、ready、同一知识库、正文非空。缺 Key 503；两 id 相同或跨库 400。不持久化对比结果。不调用 LangGraph。不改 chat / search 路由。不做前端。

**验证：** pytest：假 LLM 下两篇 ready 文档返回非空 comparison；非 ready / 跨库为 400。本步文件无 `langgraph` import。

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

## 执行纪律

- 每步结束后等待提出人确认，再开始下一步。  
- 发现与设计不符：停止实现，先改设计文档并征得同意。  
- 本计划含「验证」所述测试；步骤 20–22 允许以提出人手工验收为主，但 0–19 能自动化的必须自动化。  
- **P1：** 已收口。  
- **P2：** 只做上文已列出且尚未验证的那一步。当前：**P2-Agent-4**（代码已写，待提出人确认）。下一未开始步骤：**P2-Agent-5**。P2-Agent-1～3 已确认。P2-DEBUG-1 代码已写。AUTH-1 代码已写。P2-RAG-3 待提出人确认阈值。
