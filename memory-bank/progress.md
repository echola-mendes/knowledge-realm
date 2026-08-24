# 进度

## 步骤 0 — 本机数据库就绪

- 状态：已执行并验证（提出人提供本机连接凭据）
- 结果：本机 PostgreSQL 16（非 Docker）已有库 `echola_kb`；扩展 `vector` 版本 0.8.0
- 连接串格式（密钥只放本机 `.env`，勿提交仓库）：`postgresql+psycopg://postgres@127.0.0.1:5432/echola_kb`
- 下一步：已确认继续，见步骤 1

## 步骤 1 — 仓库骨架与忽略规则

- 状态：已执行并验证
- 结果：`server/`、`web/`、`data/files/`、`data/parsed/`；根目录 `.gitignore`、`.env.example`（无真实密钥；DashScope 兼容 URL 已注明）
- 下一步：步骤 2 已开始（venv，见下）

## 步骤 2 — Python 环境与依赖清单

- 状态：已执行并验证
- 结果：`server/.venv`（Python 3.12.1）；`server/requirements.txt`；阿里云镜像安装成功。可导入 fastapi、sqlalchemy、langchain_text_splitters、pymupdf、trafilatura。清单无 MinerU/LlamaIndex/Celery/Redis。langchain 1.x 会顺带装上 langgraph 包，**应用禁止 import/使用**，只当切块与 Chat。
- 下一步：步骤 3 已完成，见下

## 步骤 3 — 配置加载

- 状态：已执行并验证
- 结果：`server/app/config.py`、`server/app/main.py`、`GET /health`；缺 `DATABASE_URL` 拒绝加载；无 LLM Key 时 `ai_configured=false` 且健康检查 200。`pytest tests/test_config.py` 4 passed。
- 下一步：步骤 4 已完成，见下

## 步骤 4 — 数据库迁移与表结构

- 状态：已执行并验证
- 结果：Alembic `20260823_0001` 已 upgrade。八张业务表 + alembic_version；`document_chunk.embedding` 为 vector(1024)；HNSW `vector_cosine_ops`；name / kb+checksum / favorite 唯一约束存在。
- 下一步：步骤 5（代码已写，验证见下）

## 步骤 5 — 默认知识库

- 状态：已执行并验证
- 结果：启动时空库会插入「默认知识库」；重复启动不重复插入；清空后再启动会再建。`tests/test_default_kb.py` 2 passed。已纠正磁盘上 `.env` 的 `DATABASE_URL`（须含用户名 `postgres`）。
- 下一步：步骤 6 已完成，见下

## 步骤 6 — 知识库 HTTP API

- 状态：已执行并验证
- 结果：`/api/knowledge-bases` CRUD；重名 409；删除级联文档并清理 `data/files` 与 `data/parsed`。`pytest` 本步相关 + 回归共 9 passed。
- 下一步：步骤 7 已完成，见下

## 步骤 7 — 文件落盘与校验

- 状态：已执行并验证
- 结果：`POST /api/documents/upload`；缺省默认库；非法扩展名/超大拒绝；SHA-256 去重；状态 `pending`。`tests/test_upload.py` 通过。
- 下一步：步骤 8 已完成，见下

## 步骤 8 — 文本类解析（md / txt）

- 状态：已执行并验证
- 结果：`parse_text_document` 写 `document.md` + 轻量 `document.json`；空白失败 `empty_content`；成功内部态 `parsed`；上传后对 txt/md 用 BackgroundTasks。`tests/test_parse_text.py` 同步调用解析。禁止 MinerU。
- 下一步：步骤 9 已完成，见下

## 步骤 9 — PDF 与 DOCX 解析

- 状态：已执行并验证
- 结果：PDF 按页抽文本，`## Page N`（从 1）；DOCX 段落拼接无页码；空文本 `empty_content`。夹具 PDF（CJK 可选中）与两段 docx 的 pytest 通过。测试目录无 MinerU。
- 下一步：步骤 10 已完成，见下

## 步骤 10 — 切块

- 状态：已执行并验证
- 结果：`split_markdown` 用 Markdown 标题切分，过长再 800/120；表格尽量整段；问号行绑定随后段落。只返回内存结构，不写 `document_chunk`（embedding 非空，步骤 11 再入库）。空文档零块。`tests/test_chunk.py` 通过。
- 下一步：步骤 11 已完成，见下

## 设计备忘 — Embedding（提出人已确认）

- 云端 DashScope：默认 `text-embedding-v3`，维 1024。不上本机 Embedding。
- 额度不够或 v3 不可用：失败文案提醒改 `.env` 为 `text-embedding-v4`，不自动切换。

## 步骤 11 — Embedding 写入与索引完成

- 状态：已执行并验证
- 结果：解析后 `process_document` 切块并写入 `document_chunk`；成功状态 `ready`。无 Key 时 `POST /api/documents/{id}/index` 为 503。同 checksum 再传不调用 Embedding。额度类错误文案含 `text-embedding-v4`。测试用假向量，未打真实 DashScope。
- 下一步：步骤 12 已完成，见下

## 步骤 12 — 重新处理与删除文档

- 状态：已执行并验证
- 结果：`POST /api/documents/{id}/reindex` 清切片后重新解析+索引；`DELETE` 删库行与本地 files/parsed（处理中也可删）；`GET` 列表/详情含 status、error_message、source_path/source_url。`tests/test_document_manage.py` 通过。
- 下一步：步骤 13 已完成，见下

## 步骤 13 — 笔记与 URL 导入

- 状态：已执行并验证
- 结果：`POST /api/documents/notes`（kind=note，正文 SHA-256）与 `POST /api/documents/url`（httpx 20s + trafilatura）。空正文/超时失败。`tests/test_notes_url.py` 用 mock HTML，无 Playwright。
- 下一步：步骤 14 已完成，见下

## 步骤 14 — 标签

- 状态：已执行并验证
- 结果：`/api/tags` 创建/列表/删除；`PUT /api/documents/{id}/tags` 覆盖设置；`GET /api/documents?tag_id=` 过滤。重名 409。`tests/test_tags.py` 通过。
- 下一步：步骤 15 已完成，见下

## 步骤 15 — 收藏

- 状态：已执行并验证
- 结果：`POST/DELETE /api/documents/{id}/favorite`；同文档再收藏不增行；`GET ?favorite=true` 只返回已收藏；删文档时清收藏行。`tests/test_favorites.py` 通过。
- 下一步：步骤 16 已完成，见下

## 步骤 16 — 向量搜索 API

- 状态：已执行并验证
- 结果：`POST /api/search` 对 query embedding 后 SQL `<=>` TopK；可筛库/标签/kind；最高分 &lt; 0.30 空列表；不调 Chat。假向量测试隔离库 A/B。
- 下一步：步骤 17 已完成，见下

## 步骤 17 — RAG 问答（非流式）

- 状态：已执行并验证
- 结果：`POST /api/chat`；无命中固定文案且不调 LLM；有命中走 LangChain 单链并返回 citations；处理中 document_id 为 400；库隔离。`tests/test_chat.py` 用假 LLM/Embedding。
- 下一步：步骤 18 已完成，见下

## 步骤 18 — 多轮与流式

- 状态：已执行并验证
- 结果：会话 CRUD；第二轮带 conversation_id 时 LLM 收到上轮问答；SSE token + citations 与非流式字段一致。`tests/test_chat_multi.py` 通过。
- 下一步：步骤 19 已完成，见下

## 步骤 19 — 前端工程与代理

- 状态：已执行并验证
- 结果：`web/` Vite + Vue 3 + TS；六条路由壳页；`npm run typecheck` 通过；`/api` 代理到 8000，经 5173 可取知识库列表。`app.main:app` 改为 `create_app()` 实例以便 uvicorn 启动。
- 下一步：步骤 20 已完成，见下

## 步骤 20 — 前端：库、文档、上传、笔记、URL

- 状态：已执行并验证（类型检查；解析稿接口自动化。手工上传/阅读由提出人确认）
- 结果：顶栏切换知识库；文档页上传/URL/笔记；列表状态与失败原因、重新处理、删除；阅读页渲染 `parsed.md`；固定隐私说明。补 `GET /api/documents/{id}/parsed.md`。
- 下一步：步骤 21 已完成，见下

## 步骤 21 — 前端：标签、收藏、搜索、问答

- 状态：已执行并验证（类型检查 + 浏览器走通页面；设计第 9 节完整问答仍待提出人用真实 Key 确认）
- 结果：文档页打标签/收藏/只看收藏；搜索页只列片段与分数；对话页 SSE 与可点引用；首页提问框与统计；设置页只显示是否已配置密钥。首页最近对话带 `?c=`。
- 下一步：步骤 22 已完成，见下

## 步骤 22 — 对照设计第 9 节总验收

- 状态：已执行并验证（提出人确认 P0 完成）
- 结果：本机已配置 DashScope，`GET /health` 为 `ai_configured=true`。提出人确认设计第 9 节总验收通过，V1/P0 收口。
- 下一步：P0 实施计划结束。P1 见 `PRD-P1.md` 与下文 P1.1。

## 步骤 P1.1-0 — 设计已确认

- 状态：已执行并验证（提出人确认 11 条边界及 ChatGPT 两点澄清）
- 结果：`search_knowledge` 内部调 `search.py`，不走 HTTP `/api/search`；`reason` 只决策、`run_tool` 才执行 Tool。P1.1 仅摘要+自动标签 Chain。
- 下一步：P1.1-1～4 已落地，见下

## 步骤 P1.1-1 — 摘要 Chain 与持久化

- 状态：已执行并验证
- 结果：`document.summary`（迁移 `20260824_0003`）；`POST /api/documents/{id}/summarize`；非 ready 400、无 Key 503。`tests/test_p1_summary_tags.py` 假 LLM。无 langgraph import。未改 chat/search。
- 下一步：P1.1-2 已完成，见下

## 步骤 P1.1-2 — 文档页展示与触发摘要

- 状态：已执行并验证（浏览器阅读页可见「生成摘要」与已有摘要）
- 结果：`ReaderView.vue` 展示并触发摘要。对话仍走 `/api/chat/stream`。
- 下一步：P1.1-3 已完成，见下

## 步骤 P1.1-3 — 自动标签 Chain

- 状态：已执行并验证
- 结果：`POST /api/documents/{id}/auto-tags`；只追加 `tag`/`document_tag`，不删已有标签。pytest 覆盖保留手打标签。
- 下一步：P1.1-4 已完成，见下

## 步骤 P1.1-4 — 文档页触发自动标签

- 状态：已执行并验证（浏览器阅读页「自动标签」）
- 结果：阅读页按钮走自动标签接口；手打标签不被清空。
- 下一步：P1.1-5 已完成，见下

## 步骤 P1.1-5 — 阶段收口

- 状态：已执行并验证（提出人确认 P1.1 通过）
- 结果：`architecture.md` 已记 P1.1 路径。未开始 P1.2（文档对比）与 P1.3（Agent）。
- 下一步：P1.2 已落地，见下

## 步骤 P1.2-0 — 范围已确认

- 状态：已执行并验证
- 结果：对比为两篇同库 ready 文档的 Chain；`POST /api/compare`；结果不落库。
- 下一步：P1.2-1 已完成，见下

## 步骤 P1.2-1 — 对比 Chain 与 API

- 状态：已执行并验证
- 结果：`compare_documents`；`POST /api/compare`；同 id / 跨库 / 非 ready 为 400。`tests/test_p1_compare.py`。无 langgraph import。
- 下一步：P1.2-2 已完成，见下

## 步骤 P1.2-2 — 文档页触发对比

- 状态：已执行并验证（浏览器勾选两篇点「对比所选」可见结果）
- 结果：`DocumentsView.vue`；对话仍走 `/api/chat/stream`。
- 下一步：P1.2-3 已完成，见下

## 步骤 P1.2-3 — 阶段收口

- 状态：已执行并验证（提出人确认继续开发）
- 结果：`architecture.md` 已记对比路径。未开始 P1.3 Graph / 报告 / 图谱。
- 下一步：P1.3，一次只做计划中未验证的那一步

## 步骤 P1.3-1 — search_knowledge Tool

- 状态：已执行并验证（提出人确认图设计后继续）
- 结果：`server/app/p1/tools.py` 内部调用 `search_chunks`；测试 `tests/test_p1_tools.py`。无 HTTP `/api/search`，无 LangGraph。
- 下一步：P1.3-2 已完成，见下

## 步骤 P1.3-2 — StateGraph（reason / run_tool / generate）

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：`server/app/p1/graph.py`；reason 不执行 Tool；`max_loops=3`；无 Checkpoint。测试 `tests/test_p1_graph.py`。`chat.py` / `chains.py` 无 langgraph。
- 下一步：P1.3-3 已落地，见下

## 步骤 P1.3-3 — POST /api/agent（非流式）

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：`POST /api/agent`，body 为 `task`（本期仅 `agent`）、`query`、`knowledge_base_id`；走 Graph；缺 Key 503。测试 `tests/test_p1_agent.py`。未改 `/api/chat` 契约。
- 下一步：P1.3-4 已落地，见下

## 步骤 P1.3-4 — POST /api/agent/stream

- 状态：已执行并验证（提出人回复「可以」进入下一步）
- 结果：SSE token + 最终 `citations` 事件字段与非流式 `POST /api/agent` 对齐。不经过 `/api/chat/stream`。
- 下一步：P1.3-5 已落地，见下

## 步骤 P1.3-5 — 前端 Agent 入口

- 状态：已执行并验证（提出人回复「继续」进入下一步）
- 结果：对话页「对话 / Agent」切换；默认仍为 `/api/chat/stream`；Agent 走 `/api/agent/stream`。首页提问仍进默认对话模式。
- 下一步：P1.3-6 已落地，见下

## 步骤 P1.3-6 — task=report

- 状态：已执行并验证（提出人回复「开始」进入收口）
- 结果：同一 `graph.py` / `build_graph()`；`task=report` 时 generate 按报告（大纲+分节）组织。`POST /api/agent` 与 stream 接受 `report`。对话页增加「报告」。无第二套 Graph。
- 下一步：P1.3-7 已落地，见下

## 步骤 P1.3-7 — 阶段收口

- 状态：已执行并验证（提出人回复 1 进入 P1.4）
- 结果：`architecture.md` 已记 P1.3 路径与边界。P1.3 通过。
- 下一步：P1.4，见下

## 步骤 P1.4-0 — 范围已确认

- 状态：已执行并验证（提出人回复 1 同意计划）
- 结果：最小 `entity` / `entity_link`；抽取 Chain；关联走 `search_chunks`；无复杂可视化；无 `search_graph` Tool。
- 下一步：P1.4-1 已落地，见下

## 步骤 P1.4-1 — entity / entity_link 表

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：迁移 `20260824_0004`；模型 `Entity` / `EntityLink`。测试 `tests/test_p1_graph_tables.py`。
- 下一步：P1.4-2 已落地，见下

## 步骤 P1.4-2 — 抽取 Chain 与 POST /api/documents/{id}/graph

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：`extract_graph`；`POST /api/documents/{id}/graph` upsert 实体、按文档替换边；未知端点跳过。测试 `tests/test_p1_extract_graph.py`。无 langgraph。未做 GET /graph 与前端。
- 下一步：P1.4-3 已落地，见下

## 步骤 P1.4-3 — GET /api/graph

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：`GET /api/graph` 按库返回实体与边 JSON；`document_id` 只返回该文档的边及两端实体。测试 `tests/test_p1_get_graph.py`。未改 chat，未做前端。
- 下一步：P1.4-4 已落地，见下

## 步骤 P1.4-4 — GET /api/documents/{id}/related

- 状态：已执行并验证（提出人回复 1 进入下一步）
- 结果：`GET /api/documents/{id}/related` 内部调 `search_chunks`（摘要优先否则文件名）；排除本文、按文档去重最多 5 条。测试 `tests/test_p1_related.py`。不调 LLM、不进 LangGraph、不 HTTP `/api/search`。未做前端。
- 下一步：P1.4-5 已落地，见下

## 步骤 P1.4-5 — 阅读页展示

- 状态：已执行并验证（提出人回复 1 进入收口）
- 结果：阅读页「抽取图谱」+ 实体/关系列表 + 相近文档列表（可点进阅读页）。无 vis.js/D3。对话页默认仍为 `/api/chat/stream`。
- 下一步：P1.4-6 已落地，见下

## 步骤 P1.4-6 — 阶段收口

- 状态：已执行并验证（提出人回复 1 确认阶段结束）
- 结果：`architecture.md` 已记 P1.4 路径与边界。P1.4 通过。未开始 `search_graph` Tool，未开始下一版本可视化。
- 下一步：无。须先改计划再开新阶段
