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
- 下一步：步骤 13
