# Execution Plan：AI 资讯（PRD-NEWS）

> 依据：`artifacts/prd-sub.md`。从顶部取第一个未全 ✅ 的 Step 执行。  
> 栈：FastAPI / Vue3；复用 APScheduler+Redis+arq；禁止 Celery。  
> 依赖新增（实现时写入 requirements）：`PyYAML`、`feedparser`（RSS/Atom）。  
> **执行约定：** 每个 Step 验收全部 `[✅]` 后暂停，等用户确认再开始下一 Step。

---

## Step 1：数据模型与迁移

### 目标

落地 `news` / `news_daily_rank` / `news_settings` 表，并种子默认启用三板块。

### 方案

1. `server/app/models.py`：三模型；`news.url`、`news.content_hash` 唯一；`news_daily_rank` 含 `rank_date` + `category`（含 `all`）+ `rank`
2. Alembic 迁移；upgrade 末尾若不存在则插入 `news_settings`（`enabled_categories` 三开）
3. 不改 `scheduled_task` 表结构

### 验收

- [ ] 迁移可 upgrade / downgrade
- [ ] 三表存在；`news_settings` 有默认一行
- [ ] `url` / `content_hash` 唯一约束生效

---

## Step 2：配置与源加载

### 目标

可读 `news_sources.yaml`，并接入 `NEWS_*` 标量配置。

### 方案

1. `config.py` / `.env.example`：`NEWS_SOURCES_PATH`（默认 `server/config/news_sources.yaml`）、`NEWS_TOP_K=20`、`NEWS_MAX_ITEMS`、`NEWS_HTTP_TIMEOUT`、`NEWS_LLM_TIMEOUT`
2. `app/news/sources.py`（或等价）：加载 yaml → 校验 schema → 按 `enabled` + category 过滤
3. 路径相对仓库根解析

### 验收

- [ ] 默认路径能加载出至少 8 条 `enabled: true` 源
- [ ] 非法 category / 缺 url 时明确报错（启动或首次 refresh 即可）
- [ ] `NEWS_SOURCES_PATH` 可覆盖默认路径

---

## Step 3：采集、解析、去重

### 目标

无 LLM 情况下，能从启用源拉 RSS 并去重入库候选。

### 方案

1. `collector.py`：httpx 拉 feed；单源失败记录错误并继续
2. `parser.py`：feedparser → 统一字段（title/url/content/published_at/source/category/weight）
3. `dedup.py`：URL 已存在 → 可更新时间/热度相关、不进 LLM 队列；标题 Hash 冲突 → skip
4. 单测覆盖：标题标准化 Hash、URL 冲突行为（mock DB 或临时 session）

### 验收

- [ ] 针对 fixture RSS/XML，parser 产出稳定字段
- [ ] 去重单测：同 URL / 同标题 Hash 行为符合 prd-sub
- [ ] 正文可为空，无网页抓取逻辑

---

## Step 4：摘要、热度与排行榜编排

### 目标

对新条目做 LLM 摘要/重要性，算 heat_score，写当日 `news_daily_rank`。

### 方案

1. `summarizer.py`：DashScope 兼容客户端；摘要 50～120 字；重要性 1～10；失败 importance=5、summary 可 null；金融 prompt 禁投资建议；**不**改分类
2. `scorer.py`：公式 45/25/30 + §15 新鲜度档；时区 Asia/Shanghai
3. `service.py`：`refresh(categories)` 全流程；截断 `NEWS_MAX_ITEMS`；重写当日相关 category + `all` 的 rank 快照；返回 result 计数 dict
4. 可保留/迁移根级 `news_service.py` 为薄封装，避免双实现

### 验收

- [ ] scorer 单测：给定 importance/weight/新鲜度档，heat 在预期区间
- [ ] 不足 20 条不跨分类补榜
- [ ] 综合榜逻辑为合并后 TopK，非三榜拼接

---

## Step 5：接通 NEWS_REFRESH Handler

### 目标

Worker 执行真实管道，不再返回 `news_pipeline_pending` stub。

### 方案

1. `news_handler.py`：读 DB `news_settings.enabled_categories` → `NewsService.refresh(...)`
2. 写 `task_execution.result`：`categories/fetched/saved/summarized/failed/skipped_dup`
3. 不改 Scheduler/队列核心；任务页不加分类多选

### 验收

- [ ] 手动 enqueue / `/run` 后 execution 为 SUCCESS（源与 LLM 可用时）或 FAILED（整源级灾难且无任何产出的约定以实现为准，需在 result/error 可观测）
- [ ] result 含计数字段，不再仅有 `news_pipeline_pending`
- [ ] 仅启用 `ai` 时不采集 technology/finance 源

---

## Step 6：News API

### 目标

对外提供热榜、详情、设置 API。

### 方案

1. `schemas.py`：HotOut / NewsDetail / SettingsIn/Out
2. `routers/news.py` + `main.py` include；Session 鉴权
3. `GET /api/news/hot` 读快照；非法 category → 400；默认今天（上海）
4. `GET/PUT /api/news/settings`

### 验收

- [ ] 未登录 401；非法 category 400
- [ ] hot 返回结构含 date/category/items（≤20）
- [ ] PUT settings 后 GET 一致；至少保留一个分类

---

## Step 7：前端 AI资讯页

### 目标

工具菜单可打开列表与详情；可改启用板块。

### 方案

1. `web/src/api.ts` 客户端
2. `NewsListView.vue` / `NewsDetailView.vue`；路由 `/tools/news`、`/tools/news/:id`
3. 工具 Layout 导航增加「AI资讯」
4. 样式遵循 `web/style.md`；无立即更新按钮

### 验收

- [ ] 路由可进入；默认「全部」频道
- [ ] 启用板块勾选会调 settings API
- [ ] `npm run typecheck` 通过
- [ ] 详情可打开；正文空时仍可看摘要与原文链接

---

## Step 8：回归与文档同步准备

### 目标

关键路径可回归；文档变更列入本步完成（TECH/PRD 同步，非改 PRD-NEWS）。

### 方案

1. 补充/收紧 `server/tests`（settings、dedup、scorer、hot API 契约按需）
2. 更新 `docs/TECH.md`、`docs/PRD.md` 中资讯条目
3. 确认 AGENTS 无需改栈（已有定时任务约束）

### 验收

- [ ] 相关单测通过
- [ ] TECH.md / PRD.md 已提及 AI资讯与 `news_sources.yaml`
- [ ] 全 execution-plan 步骤验收均可勾选（本步为收尾）

---
