# 方案设计：通用定时任务基础设施

> 依据：`artifacts/prd-sub.md`、`docs/PRD-Job.md`

## 1. 架构总览

```text
┌─────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn)                                      │
│  ├── /api/tasks/*        CRUD / run / executions        │
│  ├── lifespan            APScheduler start/stop         │
│  └── scheduler/          读 DB → 注册 job → executor    │
└────────────────────────────┬────────────────────────────┘
                             │ enqueue(payload)
                             ▼
                    Redis (arq queue)
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  arq Worker (python -m app.worker.worker)               │
│  ├── 领取 job                                           │
│  ├── 防重检查 (task_type lock)                          │
│  ├── handlers/news_handler → NewsService.refresh() stub │
│  └── 更新 task_execution + scheduled_task timestamps    │
└─────────────────────────────────────────────────────────┘
                             │
                             ▼
                    PostgreSQL
              scheduled_task / task_execution
```

**原则**：Scheduler 与 API `/run` 均只调用 `executor.enqueue_task()`，不执行业务。

## 2. 依赖新增

`server/requirements.txt` 追加：

```text
apscheduler>=3.10.0
arq>=0.26.0
redis>=5.0.0
```

## 3. 数据模型

### 3.1 `scheduled_task`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BigInteger PK | 自增 |
| name | String(200) | 展示名 |
| task_type | String(64) | 如 `NEWS_REFRESH` |
| schedule_type | String(16) | `INTERVAL` / `CRON` |
| schedule_config | JSONB | `{ "minutes": 30 }` 或 `{ "hour": 8, "minute": 0 }` |
| enabled | Boolean | 默认 true |
| last_run_at | timestamptz nullable | |
| next_run_at | timestamptz nullable | |
| created_at / updated_at | timestamptz | |

**约束**：`UniqueConstraint("task_type")` — v1 同类型唯一。

### 3.2 `task_execution`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BigInteger PK | 自增 |
| task_id | FK → scheduled_task | |
| run_id | String(64) unique | UUID hex，Worker payload 携带 |
| started_at / finished_at | timestamptz nullable | |
| status | String(16) | PENDING/RUNNING/SUCCESS/FAILED |
| result | JSONB nullable | 业务摘要 |
| error_message | Text nullable | |
| created_at | timestamptz | |

## 4. 后端模块

```text
server/app/
├── models.py                    # + ScheduledTask, TaskExecution
├── schemas.py                   # TaskOut, TaskCreate, TaskUpdate, ExecutionOut
├── services/
│   └── task_service.py          # CRUD、seed、execution 创建、状态更新
├── scheduler/
│   ├── __init__.py
│   ├── scheduler.py             # APScheduler 生命周期、reload_jobs()
│   └── executor.py              # create execution + enqueue
├── jobs/
│   └── news_job.py              # NEWS_REFRESH 调度回调 → executor
├── worker/
│   ├── __init__.py
│   ├── settings.py              # arq WorkerSettings
│   ├── worker.py                # python -m app.worker.worker 入口
│   ├── queue.py                 # enqueue 封装、Redis 连接检查
│   └── handlers/
│       ├── __init__.py          # HANDLERS registry
│       └── news_handler.py      # stub NewsService.refresh()
├── news_service.py              # stub: return { news_pipeline_pending: true }
└── routers/
    └── task.py                  # HTTP API
```

### 4.1 注册 task_type

```python
REGISTERED_TASK_TYPES = {
    "NEWS_REFRESH": {"label": "AI资讯更新", "handler": "news_handler"},
}
```

新增类型：加 handler + 注册表条目，不改队列/调度核心。

### 4.2 执行流程

1. **触发**（Scheduler 到点 或 `POST /run`）
2. `task_service.create_execution(task_id)` → status=PENDING, run_id=uuid4().hex
3. `queue.enqueue({ task_id, task_type, run_id })`
4. Worker 函数：
   - 查 execution by run_id → RUNNING
   - 若同 task_type 已有其他 RUNNING → 标记 SKIP/FAILED(skip) 并返回
   - 调 handler（最多 3 次重试，指数退避）
   - 写 SUCCESS/FAILED + result/error_message
   - 更新 scheduled_task.last_run_at / next_run_at

### 4.3 APScheduler

- `AsyncIOScheduler` 挂 lifespan
- 启动时 `reload_jobs(session)`：读 enabled 任务，按 schedule_type 注册
- INTERVAL → `IntervalTrigger(**schedule_config)`
- CRON → `CronTrigger(**schedule_config)`
- 任务变更（PUT/enable/disable/delete）后调用 `reload_jobs()`

### 4.4 Redis / arq

- `REDIS_URL` 来自 env（默认 `redis://127.0.0.1:6379/0`）
- 未配置或 ping 失败 → API 返回 503，`detail` 明确提示
- arq 队列名：`zhiyu:tasks`
- Worker 单函数 `process_task(ctx, payload)`

### 4.5 防重

Redis key `task:lock:{task_type}`，TTL 略大于任务超时；Worker 领取前先 SET NX。
备选：DB 查同 task_type RUNNING 计数 > 0 则 skip。

## 5. API 设计

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/api/tasks` | 列表 |
| POST | `/api/tasks` | 创建（校验 task_type 已注册 + 唯一） |
| PUT | `/api/tasks/{id}` | 更新 name/schedule；改后 reload scheduler |
| DELETE | `/api/tasks/{id}` | 删除 + 从 scheduler 移除 |
| POST | `/api/tasks/{id}/enable` | enabled=true + reload |
| POST | `/api/tasks/{id}/disable` | enabled=false + reload |
| POST | `/api/tasks/{id}/run` | 创建 execution + enqueue，返回 `{ execution_id, run_id }` |
| GET | `/api/tasks/{id}/executions` | 最近 N 条（默认 20） |
| GET | `/api/tasks/types` | `[{ value, label }]` 已注册类型 |

## 6. 前端

### 6.1 路由与导航

- `router.ts`：`/basics/jobs` → `JobsManageView.vue`
- `BasicsLayout.vue`：二级菜单加「定时任务」
- `navConfig.ts`：无需改全局侧栏（「基础」已存在）

### 6.2 页面 `JobsManageView.vue`

布局参照 `MenuManageView` / `MyTripsView` 卡片风格（`style.md`）：

- 顶栏：标题 +「新建任务」按钮
- 任务卡片列表：名称、类型标签、调度描述、启停 badge、上次/下次
- 卡片操作：立即执行 / 启用·停用 / 编辑 / 删除
- 下方「最近执行」表格：时间、状态、摘要/错误
- 新建/编辑 Modal：名称、类型 select、调度（interval 分钟 或 hour+minute）

### 6.3 API 客户端

`web/src/api.ts` 追加 `Task`、`TaskExecution` 类型与 CRUD/run/executions 函数。

## 7. 配置与启动

`.env` / `.env.example` 追加：

```text
REDIS_URL=redis://127.0.0.1:6379/0
```

启动：

```text
# Terminal 1
cd server && uvicorn app.main:app --reload

# Terminal 2
cd server && python -m app.worker.worker
```

## 8. 测试策略

| 范围 | 内容 |
| --- | --- |
| 单元 | task_service CRUD、同类型唯一约束、schedule 解析 |
| 集成 | POST /run 只入队不阻塞；mock handler 验证 execution 状态流转 |
| 防重 | 并发 enqueue 同 task_type，仅一条 RUNNING |
| 重试 | handler 注入失败，验证 3 次后 FAILED |

不依赖真实 RSS/LLM。

## 9. 文档同步（最后 Step）

- `AGENTS.md`：任务分层（BackgroundTasks 短任务 + Redis/arq 定时任务）
- `docs/TECH.md`：调度架构、依赖、启动方式
- `docs/PRD.md`：子需求完成状态

## 10. 风险与取舍

| 项 | 取舍 |
| --- | --- |
| ID 类型 | BigInteger 自增（与 PRD payload `task_id: 1` 一致；任务表不与 UUID 用户体系混用） |
| Scheduler 单实例 | 不实现分布式锁；文档注明勿多 uvicorn worker |
| news_handler | stub 即可，后续 PRF-NEWS 替换 |
| CRON 前端 | v1 支持「每天 HH:MM」映射为 `{ hour, minute }`；不做通用 cron 字符串 |
