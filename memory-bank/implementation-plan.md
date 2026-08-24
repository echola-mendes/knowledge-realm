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

## 执行纪律

- 每步结束后等待提出人确认，再开始下一步。  
- 发现与设计不符：停止实现，先改设计文档并征得同意。  
- 本计划含「验证」所述测试；步骤 20–22 允许以提出人手工验收为主，但 0–19 能自动化的必须自动化。  
- **P1：** 只做上文已列出且尚未验证的那一步。
