# 知域 — 产品设计文档

**状态：** 可执行  
**依据：** 仓库 `PRD.md`（已与提出人确认同步）  
**产品名称：** 知域  
**用户：** 单人；Web；本机为主  

---

## 1. 设计裁决

| 项 | 裁决 |
|---|---|
| V1 范围 | 仅 PRD 第 18 节 **P0**。摘要、自动标签、图谱、Agent、研究报告、知识发现为 P1/P2 |
| 编排 | **LangChain** 单链。不上 LangGraph、不上 LlamaIndex |
| 解析 | 不上 MinerU。PDF = PyMuPDF 文本层；DOCX = python-docx；MD/TXT/笔记 = 直读；URL = 抓公开页正文 |
| 检索 | 问答与搜索均为 **pgvector 余弦相似度**（方案 A）。全文检索与按时间/来源筛为方案 B，V1 不做 |
| 知识库 | 可多个；启动时若不存在则创建名为 `默认知识库` 的记录。未传 `knowledge_base_id` 时只用默认库 |
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
5. 标签：增删、打在文档上、AI **不**自动打标（自动标签属 P1）。  
6. 收藏：收藏/取消文档（V1 不收藏「片段」——PRD 片段收藏放到 P1，避免范围膨胀）。  
7. 搜索：余弦 TopK，可筛知识库、标签、类型。  
8. RAG 问答：全库（默认或指定）或指定文档；多轮；引用；流式。  
9. 首页：提问入口、统计（文档数/库数/标签数）、最近添加、最近对话。

### 2.2 非目标

MinerU、LlamaIndex、LangGraph、Ollama、Milvus、图谱、Agent、研究报告、智能摘要、自动标签、知识冲突/缺口、Web Search、多用户、扫描件 OCR、`.doc`、登录墙网页、关键词全文检索。

**收藏片段：** V1 只收藏文档。

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
- 最高分余弦 **&lt; 0.30** 或无切片：仍调用 Chat，按普通对话回答，citations 为空；有命中时优先根据资料回答并带引用，禁止编造出处。对话页仅在有引用时于气泡下方列出；超过 2 条先显示省略。  

- 多轮：最近 **6 条** 消息给 LLM；**检索只用当前句**，不改写。  
- 引用字段：`document_id`、`document_name`、`chunk_id`、`page_start`、`page_end`、`content`、`score`。无页码则页码为 null。  
- 流式 SSE 与非流式语义相同。

### 4.4 搜索 API

`POST /api/search`：query embedding → 余弦 TopK → 返回 chunk/文档摘要。可选 `knowledge_base_id`、`tag_id`、`kind`（`pdf|docx|md|txt|url|note`）。不调 Chat。

### 4.5 标签与收藏

- 标签名全局唯一（个人单用户）。文档与标签多对多。  
- 收藏：用户-文档，唯一约束。列表接口可 `?favorite=true`。

### 4.6 笔记

创建/编辑 Markdown 正文，视为一种文档 `kind=note`，走同一切块索引。

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

**knowledge_base：** id, name UNIQUE, is_default BOOL, timestamps  

**document：** id, knowledge_base_id FK CASCADE, filename, ext, kind, source_url 可空, checksum, status, error_message, byte_size, timestamps。UNIQUE(knowledge_base_id, checksum) 对文件；笔记可无 checksum 或对正文哈希。  

**document_chunk：** id, document_id FK CASCADE, chunk_index, content, page 可空, heading 可空, metadata JSONB, embedding vector(N)。HNSW cosine。  

**tag：** id, name UNIQUE  

**document_tag：** document_id, tag_id, PK 复合  

**favorite：** document_id UNIQUE（单用户）  

**conversation：** id, knowledge_base_id, title, timestamps  

**message：** id, conversation_id, role, content, citations JSONB, created_at  

不建：entity、relation、fragment_favorite。

---

## 7. API（前缀 `/api`）

知识库：`GET/POST /knowledge-bases`，`GET/PUT/DELETE /knowledge-bases/{id}`  

文档：`POST /documents/upload`，`POST /documents/url`，`POST /documents/notes`，`GET /documents`，`GET /documents/{id}`，`GET /documents/{id}/parsed.md`，`DELETE`，`POST .../reindex`  

标签：`GET/POST /tags`，`DELETE /tags/{id}`，`PUT /documents/{id}/tags`  

收藏：`POST /documents/{id}/favorite`，`DELETE /documents/{id}/favorite`  

搜索：`POST /search`  

Chat：`POST /chat`，`POST /chat/stream`，会话 CRUD  

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

实现以本文为准。
