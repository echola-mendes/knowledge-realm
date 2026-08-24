# 架构地图

代码仓库名：`knowledge_realm`。代码尚未落地。约定目录见 `tech-stack.md`。

| 路径 | 职责 |
|---|---|
| `PRD.md` | 产品需求（V1=P0） |
| `memory-bank/design-document.md` | 实现规格 |
| `memory-bank/tech-stack.md` | 技术选型 |
| `AGENTS.md` | Agent 约束 |
| `server/.venv` | Python 3.12 虚拟环境（不用 conda） |
| `server/requirements.txt` | 后端依赖 |
| `server/app/config.py` | 环境变量与 Settings |
| `server/app/main.py` | FastAPI 入口、`/health`、启动时确保默认库 |
| `server/app/db.py` | 引擎与会话 |
| `server/app/kb.py` | 默认知识库 |
| `server/app/routers/knowledge_bases.py` | 知识库 HTTP |
| `server/app/routers/documents.py` | 上传、笔记、URL、列表、详情、`parsed.md`、删除、打标签、收藏、`/index`、`/reindex` |
| `web/src/` | 库切换、文档导入/标签/收藏、搜索、对话流式（左侧可折叠会话列表）、阅读定位、设置密钥状态、隐私说明 |
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
| `server/alembic/` | 迁移；当前 `20260823_0001` |
| `web/` | Vite + Vue 3 + TS；路由首页/文档/搜索/对话/阅读/设置；`/api` 代理 `127.0.0.1:8000` |
| `data/files/`、`data/parsed/` | 原件与解析稿；内容被 gitignore |
| `.env.example` | 环境变量模板（DashScope，无真实密钥） |
| `.gitignore` | 忽略 `.env`、venv、node_modules、用户 data |
| 本机 PostgreSQL `echola_kb` | 已创建；`vector` 0.8.0。连接用户 `postgres`，密码仅本机，不入库 |

无 MinerU、无独立向量库、无 Docker。
