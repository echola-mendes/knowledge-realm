# 当前子需求：AI 资讯（PRD-NEWS V1.1）

> 需求来源：`docs/PRD-NEWS.md`  
> 前置：PRD-Job 已完成；`NEWS_REFRESH` handler 仍为 stub  
> 默认源：`server/config/news_sources.yaml`（8 启用 + Reuters 备选关闭）

## 1. 目标

在「工具 → AI资讯」实现资讯聚合、摘要、热度与 Top20 展示；通过现有 `NEWS_REFRESH` 定时任务异步更新，不重做调度基建。

## 2. 背景

通用定时任务（APScheduler → Redis → arq）已就绪。本子需求落地资讯业务管道与前端，并把 stub handler 接到真实 `NewsService.refresh`。

## 3. 功能范围

### 后端

- 表：`news`、`news_daily_rank`、`news_settings`（Alembic）
- 模块：`app/news/`（collector / parser / dedup / summarizer / scorer / service）、`routers/news.py`
- 读 `server/config/news_sources.yaml`（或 `NEWS_SOURCES_PATH`）；URL 不硬编码
- 管道：按启用板块过滤源 → RSS 采集 → 解析 → URL/标题 Hash 去重 → 摘要 + 重要性 → 热度 → 写当日排行榜快照
- 正文仅用 RSS/API 字段，可空；不抓网页全文
- API（Session）：
  - `GET /api/news/hot?category=&date=`
  - `GET /api/news/{id}`
  - `GET/PUT /api/news/settings`（`enabled_categories`）
- Worker：`news_handler` 读 `news_settings.enabled_categories` 后调用 refresh；任务页不配分类
- `task_execution.result` 含 fetched/saved/summarized/failed/skipped_dup 等计数

### 前端

- 路由：`/tools/news`、`/tools/news/:id`；入口在工具菜单
- 列表：启用板块勾选 + 频道（全部/科技/AI/金融）+ 当日 Top20
- 详情：标题/来源/时间/分类/摘要/正文（可空）/查看原文
- 样式遵循 `docs/style.md`（或项目 `style.md`）
- 无「立即更新」按钮；无源管理 UI；历史日 API 就绪，UI 第一版只展示当天

### 文档

- 完成后同步 `docs/TECH.md`、`docs/PRD.md`（Skill Phase 4）；不改用户需求文档 `PRD-NEWS.md`

## 4. 非目标

- 重做 APScheduler / Redis / Worker / 通用任务管理
- 语义去重、Embedding 聚类、多源出现加分
- LLM 改分类；trafilatura 抓全文
- 源管理 UI；资讯页立即执行
- 无限滚动 / 全库浏览器
- Celery / Kafka

## 5. 业务规则

| 规则 | 内容 |
| --- | --- |
| 分类 | 仅来源默认 `technology` / `ai` / `finance` |
| 启用板块 | 资讯页设置；默认三开；任务执行时读取 |
| 热度 | `0.45*importance_norm + 0.25*source_weight + 0.30*freshness`，clamp 0～100 |
| 重要性失败 | `importance_score = 5` |
| 时区 | `Asia/Shanghai`；无 published_at 用 collected_at；超 24h 不入当日榜 |
| 去重 | URL 唯一；同 URL 不重 LLM；标题 Hash 冲突 skip |
| 排行榜 | 写 `news_daily_rank`（含 `all`）；API 读快照；支持 `?date=` |
| 综合榜 | 三分类合并后按 heat Top20（非三榜拼接） |
| 金融 | Prompt 禁止投资建议 |
| 任务类型 | `NEWS_REFRESH` / 展示名「AI资讯更新」 |
| 失败 | 单条失败继续；整源不可用记错误 |

## 6. 输入与输出

- 输入：yaml 源、启用板块、定时/手动触发的 Worker 任务
- 输出：`news` 行、当日（及历史）`news_daily_rank`、热榜/详情/设置 API、资讯前端页

## 7. 涉及模块

- 新：`server/app/news/*`、`routers/news.py`、迁移、`web` 资讯视图与路由
- 改：`news_handler.py`、`news_service.py`（或迁入 `news/service.py`）、`models.py`、`schemas.py`、`main.py`、`config.py`、工具菜单导航
- 配置：`server/config/news_sources.yaml`、`.env` 可选 `NEWS_*`

## 8. 验收标准

| ID | 标准 |
| --- | --- |
| AC-01 | 工具 → AI资讯可打开 |
| AC-02 | 默认「全部」 |
| AC-03 | 四个浏览频道 |
| AC-04/05 | 全部与各分类最多 20 条 |
| AC-06 | 列表含标题/摘要/来源/时间/分类/热度 |
| AC-07/08 | URL 与标题 Hash 去重 |
| AC-09/10 | AI 摘要与热度 |
| AC-11 | 金融无投资建议 |
| AC-12 | 定时 `NEWS_REFRESH` 可更新 |
| AC-13/14 | 资讯页启停板块；取消后下次任务不更新该分类 |
| AC-15 | 定时任务页立即执行可更新 |
| AC-16 | 单条失败不拖垮整任务 |
| AC-17 | 热榜读快照；`?date=` 可读历史 |
| AC-18 | 无正文可打开详情，不抓网页 |

## 9. 待确认问题

无阻塞项（V1.1 已拍板；默认源已写入 yaml）。若确认①无异议 → Phase 2。
