# Memory

## 完成记录

| 子需求 | 日期 | 结果 | 验收 |
|---|---|---|---|
| 通用定时任务（PRD-Job） | 2026-09-04 | APScheduler+Redis+arq+任务页；NEWS_REFRESH handler 仍 stub | 全 ✅ |
| AI资讯（PRD-NEWS） | 2026-09-04 | news 表/管道/API/前端热榜；NEWS_REFRESH 接真实 refresh；源 yaml | 全 ✅ |

## 经验

### REDIS_URL 须用 redis://

日期：2026-09-04　来源：PRD-Job

问题：写成 `http://` 会被 arq `from_dsn` 拒绝。

解法：`.env` 使用 `redis://127.0.0.1:6379/0`。

### NEWS_REFRESH 与资讯业务解耦

日期：2026-09-04　来源：PRD-Job

问题：调度基建先于资讯管道落地。

解法：handler stub 返回 `news_pipeline_pending`；资讯管道见 PRD-NEWS，执行时读 `news_settings`，任务页不配分类。

> 后续：PRD-NEWS 已接通真实管道，stub 仅作历史记录。

### NEWS_REFRESH 读 settings 不读任务配置

日期：2026-09-04　来源：PRD-NEWS

问题：分类启停与调度间隔职责分离。

解法：启用板块只存 `news_settings.enabled_categories`；handler 执行时读取；任务页不配分类。源列表在 `server/config/news_sources.yaml`，路径可用 `NEWS_SOURCES_PATH` 覆盖。

### 热榜只读当日快照

日期：2026-09-04　来源：PRD-NEWS

问题：列表若现算 heat 会与任务结果不一致。

解法：`GET /api/news/hot` 只读 `news_daily_rank`；refresh 重写相关 category + `all`；不足 TopK 不跨分类补榜。

---

## 2026-09-04：PRD-NEWS 子需求完成

- 表：`news` / `news_daily_rank` / `news_settings`；迁移 `20260904_0023_news`
- 管道：`app/news/`（sources→collector→parser→dedup→summarizer→scorer→service）；薄封装 `news_service.py`
- Worker：`news_handler` 读 enabled_categories → `NewsService.refresh`；result 含 fetched/saved/summarized/failed/skipped_dup
- API：`/api/news/hot|settings|{id}`；前端 `/tools/news`、`/tools/news/:id`
- 单测：`test_news_*.py` 14 passed；文档已同步 TECH/PRD；AGENTS 栈未变

---

> 归档：2026-09-03 工具菜单 + 我的行程单已完成（见 git 历史）。  
> 新子需求 PRD-Job 启动，prd-sub 待确认。

## 2026-09-03：PRD-Job Phase 0–3

- 需求来源：`docs/PRD-Job.md` — 通用定时任务（APScheduler + Redis + arq）
- 用户确认：Redis+arq OK；入口 `/basics/jobs`；前端 full CRUD（同 task_type 唯一）
- plan.md + execution-plan.md（7 Steps）已生成，待确认后执行

## 2026-09-04：Step 1 完成

- 模型：`ScheduledTask` / `TaskExecution`（BigInteger PK，`task_type` 唯一）
- 迁移：`20260903_0022_scheduled_task.py` 已 up/down 验证
- seed：`NEWS_REFRESH` / 间隔 30 分钟 / enabled

## 2026-09-04：Step 2 完成

- `schemas.py`：TaskCreate/Update/Out、ExecutionOut、TaskTypeOut
- `app/services/task_service.py`：CRUD + create_execution；重复 NEWS_REFRESH 抛 TaskTypeConflictError
- create_execution 写 PENDING + run_id

## 2026-09-04：Step 3 完成

- `REDIS_URL` 须为 `redis://`（`http://` 会被 arq `from_dsn` 拒绝）
- Worker：`python -m app.worker.worker`；enqueue → SUCCESS + `{ news_pipeline_pending: true }`
- Redis 不可用抛 `QueueUnavailableError`

## 2026-09-04：Step 4 完成

- APScheduler 挂 FastAPI lifespan；enabled 任务注册为 `task-{id}`
- 调度回调与 `/run` 共用 `executor.enqueue_task()`

## 2026-09-04：Step 5 完成

- `/api/tasks` CRUD + enable/disable/run/executions/types；`/run` 只入队
- Redis 不可用 `/run` 返回 503

## 2026-09-04：Step 6 完成

- `/basics/jobs` 定时任务页：列表/新建编辑 Modal/启停/立即执行/执行历史
- `npm run typecheck` 已通过（修了 `KnowledgeGraphView.vue` 三处模板类型）

## 2026-09-04：Step 7 完成

- Worker：Redis `task:lock:{task_type}` 防重；handler 最多 3 次尝试 + 指数退避；失败不再抛给 arq 重试
- `server/tests/test_tasks.py` 4 passed
- 文档：`AGENTS.md` / `docs/TECH.md` / `docs/PRD.md` / `.env.example`

## 2026-09-04：PRD-Job 子需求完成

- 通用定时任务基础设施已落地：表 + TaskService + Redis/arq Worker + APScheduler + `/api/tasks` + `/basics/jobs`
- `NEWS_REFRESH` handler 仍为 stub（`news_pipeline_pending`）；资讯管道见 PRF-NEWS
- `KnowledgeGraphView.vue` 三处模板类型已修，`npm run typecheck` 通过
- `REDIS_URL` 必须是 `redis://`（不要写成 `http://`）
