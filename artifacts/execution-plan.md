# Execution Plan：通用定时任务

> 从顶部取第一个 pending Step 执行。验证成功后删除该 Step。

---

## Step 1：数据模型与迁移

### 目标

`scheduled_task` / `task_execution` 表 + Alembic 迁移 + 种子 NEWS_REFRESH。

### 改动

1. `models.py`：`ScheduledTask`、`TaskExecution`
2. Alembic `20260903_0022_scheduled_task.py`
3. 迁移 downgrade 安全；upgrade 末尾 seed 一条 NEWS_REFRESH（不存在时）

### 验收

- [ ] 迁移可 up/down
- [ ] 表存在且 seed 一条 enabled 任务
- [ ] `task_type` 唯一约束生效

---

## Step 2：Schemas 与 TaskService

### 目标

业务层 CRUD、execution 创建、registered types 查询。

### 改动

1. `schemas.py`：TaskOut/Create/Update、ExecutionOut、TaskTypeOut
2. `services/task_service.py`：list/create/update/delete/enable/disable/create_execution/update_execution
3. `REGISTERED_TASK_TYPES` 常量

### 验收

- [ ] 创建重复 task_type 抛错
- [ ] create_execution 生成 run_id + PENDING 记录

---

## Step 3：Redis 队列与 arq Worker

### 目标

enqueue 封装 + Worker 进程 + news_handler stub 跑通一轮。

### 改动

1. `config.py`：`redis_url` 字段
2. `requirements.txt`：apscheduler、arq、redis
3. `worker/queue.py`、`worker/settings.py`、`worker/worker.py`
4. `worker/handlers/news_handler.py`、`news_service.py`（stub）
5. Worker 内：RUNNING → handler → SUCCESS + result

### 验收

- [ ] `python -m app.worker.worker` 可启动
- [ ] 手动 enqueue 后 execution 变 SUCCESS，`result.news_pipeline_pending=true`
- [ ] Redis 不可用时 enqueue 明确报错

---

## Step 4：APScheduler 与 Executor

### 目标

lifespan 启停 Scheduler；到点与 /run 共用 enqueue 路径。

### 改动

1. `scheduler/executor.py`：create_execution + enqueue
2. `scheduler/scheduler.py`：reload_jobs、Interval/Cron trigger
3. `jobs/news_job.py`：调度回调
4. `main.py` lifespan 集成 scheduler start/shutdown

### 验收

- [ ] 启动 uvicorn 后 scheduler 注册 enabled 任务
- [ ] 手动 trigger job 能 enqueue（可用短 interval 或 mock）

---

## Step 5：Task API 路由

### 目标

完整 REST API，/run 只入队立即返回。

### 改动

1. `routers/task.py`：全部端点
2. `main.py` include_router
3. Redis 不可用返回 503

### 验收

- [ ] GET/POST/PUT/DELETE /api/tasks 正常
- [ ] POST /run 立即返回 execution_id，Worker 异步完成
- [ ] GET /executions 返回历史

---

## Step 6：前端定时任务页

### 目标

基础 → 定时任务 CRUD 页面。

### 改动

1. `web/src/api.ts`：task API 客户端
2. `web/src/views/JobsManageView.vue`：列表 + 新建/编辑 Modal + 执行历史
3. `router.ts`：`/basics/jobs`
4. `BasicsLayout.vue`：导航项

### 验收

- [ ] 页面可访问，展示种子任务
- [ ] 新建/编辑/删除/启停/立即执行可用
- [ ] 执行历史展示 SUCCESS/FAILED
- [ ] `npm run typecheck` 通过

---

## Step 7：防重、重试、测试与文档

### 目标

AC-13/AC-14 + 文档同步。

### 改动

1. Redis lock 或 DB 防重（同 task_type 并行 skip）
2. handler 3 次重试 + 指数退避
3. `server/tests/test_tasks.py`：CRUD、/run 入队、防重、重试
4. 更新 `AGENTS.md`、`docs/TECH.md`、`docs/PRD.md`
5. `.env.example` 加 REDIS_URL

### 验收

- [ ] 同 task_type 并行仅一条 RUNNING（AC-14）
- [ ] 失败重试后 FAILED（AC-13）
- [ ] 测试通过
- [ ] 文档已更新
