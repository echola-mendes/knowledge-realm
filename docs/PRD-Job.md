# 知域 — 通用定时任务需求文档（PRD-Job）

**版本：** V1.0  
**模块：** 知域 → 工具 → 定时任务  
**状态：** 待开发  
**来源：** 从 [`PRF-NEWS.md`](PRF-NEWS.md) 抽出的定时任务基础设施（§2、§21–38、§41、§44–55、§60）。资讯业务本身见 PRF-NEWS，不在本文实现范围。

---

## 1. 需求背景

建设一套**通用定时任务基础设施**，供本机后台任务复用。

第一版注册的业务类型：

```text
NEWS_REFRESH   # AI资讯更新（业务实现见 PRF-NEWS；本期 handler 可 stub）
```

后续可扩展，无需改调度/队列核心：

```text
KNOWLEDGE_SYNC
REPORT_GENERATE
AGENT_TASK
KB_AUTO_UPDATE
```

系统需要：

- 按间隔或 Cron 自动触发
- 支持手动「立即执行」
- 可启用 / 禁用
- 可查看执行历史（成功 / 失败）
- **执行不能阻塞 FastAPI**
- 同一业务类型同一时刻只允许一个执行实例

---

## 2. 核心原则

### 2.1 调度与执行分离

必须：

```text
APScheduler
    ↓  只决定「什么时候」
enqueue
    ↓
Redis Queue
    ↓
arq Worker
    ↓
Handler → Business Service
    ↓
PostgreSQL（任务定义 + 执行记录 + 业务数据）
```

禁止：

```text
APScheduler → 直接执行业务 Service
FastAPI 路由里 await NewsService.refresh()
```

定时触发与手动触发**走同一条 Worker 路径**。

### 2.2 产品边界

```text
工具 → AI资讯     业务功能（展示 Top20 / 详情）
工具 → 定时任务   系统基础设施（调度、启停、执行记录）
```

AI资讯**使用**定时任务，但不拥有定时任务页面。  
定时任务**不要**放在「工具 → AI资讯」子菜单。

---

## 3. 技术选型

| 模块 | 技术 |
| --- | --- |
| Web API | FastAPI（现有） |
| 定时调度 | APScheduler（挂在 FastAPI lifespan，单实例） |
| 队列 | 本机 Redis |
| Worker | arq，独立进程 |
| 持久化 | PostgreSQL + 现有 SQLAlchemy / Alembic |
| 日志 | Python logging |

不使用：Kafka、Celery、RabbitMQ、XXL-JOB、多 Scheduler 集群。

文档处理等短任务仍可用 FastAPI `BackgroundTasks`，与本模块无关。

---

## 4. 总体架构

```text
前端（基础 → 定时任务）
        ↓
FastAPI  Task API  +  APScheduler
        │                    │
        │  POST /run         │  到点
        └────────┬───────────┘
                 ↓
              enqueue(payload)
                 ↓
              Redis Queue
                 ↓
              arq Worker
                 ↓
         handlers / news_handler
                 ↓
           NewsService.refresh()   # 资讯管道在 PRF-NEWS；本期可 stub
                 ↓
           更新 task_execution
```

开发进程：

```text
Terminal 1    uvicorn（含 APScheduler）
Terminal 2    python -m app.worker.worker
```

第一版默认：1 个 FastAPI + 1 个 Scheduler + 1 个 Worker。  
多 uvicorn worker 会导致重复调度；本期不实现分布式 Scheduler 锁，架构预留独立 Scheduler 进程的可能。

---

## 5. 数据模型

### 5.1 `scheduled_task`

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| name | 展示名，如「AI资讯更新」 |
| task_type | 见 §6 |
| schedule_type | `INTERVAL` 或 `CRON` |
| schedule_config | JSON，见 §7 |
| enabled | 是否调度 |
| last_run_at | 最近一次开始/结束时间（实现时与 execution 对齐即可） |
| next_run_at | 下次计划时间 |
| created_at / updated_at | |

同 `task_type` 第一版只允许一条实例（`NEWS_REFRESH` 一条）。

### 5.2 `task_execution`

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| task_id | 外键 → scheduled_task |
| started_at / finished_at | |
| status | `PENDING` / `RUNNING` / `SUCCESS` / `FAILED` |
| result | JSON，业务摘要 |
| error_message | 失败信息 |
| created_at | |

---

## 6. task_type

第一版：`NEWS_REFRESH`。

Worker 按类型分发到 `worker/handlers/`。新增类型只加 handler，不改 Redis/Scheduler 核心。

---

## 7. 调度配置

`schedule_type`：

**INTERVAL**

```json
{ "minutes": 30 }
```

**CRON**

```json
{ "hour": 8, "minute": 0 }
```

前端给普通用户：每 N 分钟 / 每天 / 每周；高级 Cron 可选。  
系统种子任务：名称「AI资讯更新」，类型 `NEWS_REFRESH`，`schedule_config` 写入 `{ "minutes": 30 }`、启用。之后间隔**只**在定时任务页 / `PUT /api/tasks/{id}` 改 `schedule_config`，不从环境变量读取。

---

## 8. 执行流程

```text
到达时间或点击立即执行
    ↓
创建 task_execution（PENDING）
    ↓
Redis enqueue { task_id, task_type, run_id }
    ↓
Worker 领取 → RUNNING
    ↓
若同 task_type 已有 RUNNING → 跳过本次（不入队或入队后立刻 SKIP）
    ↓
调用对应 handler
    ↓
SUCCESS / FAILED，写 result / error_message
    ↓
更新 scheduled_task.last_run_at / next_run_at
```

### 8.1 Job payload

```json
{
  "task_id": 1,
  "task_type": "NEWS_REFRESH",
  "run_id": "xxx"
}
```

`run_id` 对应一次 `task_execution`，Worker 不得猜测执行记录。

### 8.2 Redis 职责

第一版：任务队列。  
防重：Redis lock（如 `news:refresh:lock`）或 DB 上「已有 RUNNING 则跳过」。同一时间不能有两个 `NEWS_REFRESH` 实例。

Redis 不当业务库。未配置或连不上时，API 明确失败，前端提示，不假装已调度。

### 8.3 重试与超时

Worker 对外部失败有限重试（约 3 次）+ 指数退避，禁止无限重试。

超时（资讯管道落地后生效，框架本期预留）：

- RSS / HTTP：约 10s（或与项目 `httpx` 超时对齐）
- LLM：约 60s

资讯业务规则（handler 接上 NewsService 后）：单条 LLM 失败不导致整任务失败，记入 `result` 失败计数，任务仍可 `SUCCESS`；RSS 整体不可用则为 `FAILED`。

---

## 9. API

身份只来自 Session。任务为本机全局一份，不按请求参数指定 `user_id`。

```http
GET    /api/tasks
POST   /api/tasks
PUT    /api/tasks/{id}
DELETE /api/tasks/{id}
POST   /api/tasks/{id}/enable
POST   /api/tasks/{id}/disable
POST   /api/tasks/{id}/run
GET    /api/tasks/{id}/executions
```

`POST .../run` **只入队**，立即返回（可带 `execution_id`），禁止在请求内跑业务。

---

## 10. 代码结构

```text
server/app/
├── routers/task.py          # HTTP
├── scheduler/
│   ├── scheduler.py         # 启停 APScheduler、按 DB 注册
│   ├── task.py
│   └── executor.py          # 只 enqueue
├── jobs/news_job.py         # NEWS_REFRESH → Redis，不跑资讯业务
├── worker/
│   ├── worker.py            # python -m app.worker.worker
│   ├── queue.py             # 统一 enqueue，业务不直连 Redis
│   └── handlers/news_handler.py
└── models/                  # scheduled_task、task_execution
```

| 模块 | 职责 |
| --- | --- |
| `api/task.py` | CRUD、启停、立即执行、执行历史 |
| `scheduler.py` | 注册/删除/更新调度，无业务 |
| `executor.py` / `news_job.py` | 组 payload 并 enqueue |
| `queue.py` | 封装 Redis |
| `news_handler.py` | 调用 `NewsService.refresh()` |

---

## 11. 配置

调度间隔、Cron、启用状态一律在 `scheduled_task`（及前端定时任务页），**不设** `NEWS_REFRESH_INTERVAL` 一类环境变量。

环境变量仅连接类配置（勿硬编码）：

```text
REDIS_URL=
```

资讯管道相关超时/条数见 PRF-NEWS，不在本期必配。

---

## 12. 日志

至少：`task_id`、`run_id`、`task_type`、开始/结束、耗时、`status`、错误信息。  
资讯 handler 接上后追加采集/去重/LLM/Top20 数量。

```text
[NEWS_REFRESH] task_id=1 run_id=abc duration=32.4s status=SUCCESS
```

---

## 13. 前端

入口：

```text
知域 → 工具 → 定时任务
```

路由建议：`/basics/jobs`，挂在现有 `BasicsLayout`（与「菜单管理」并列）。样式遵循 `web/style.md`。

页面：

```text
定时任务

┌────────────────────────────────────┐
│ AI资讯更新       每30分钟   ●启用  │
│ 上次执行：14:30                    │
│ 下次执行：15:00                    │
│ [立即执行] [停用]                  │
└────────────────────────────────────┘

最近执行
14:30   ✓ 成功   …
14:00   ✓ 成功   …
13:30   ✕ 失败   …
```

本期可不做完整「新建任务」表单：种子一条 `NEWS_REFRESH` 即可；若做创建，类型只能选自已注册 `task_type`。

---

## 14. MVP 范围

必须：

- APScheduler + Redis + arq Worker
- 种子任务 `NEWS_REFRESH`，默认每 30 分钟、启用
- 手动执行、启用/禁用
- `task_execution` 成功/失败记录
- 有限重试 + 超时框架
- 防 `NEWS_REFRESH` 并行

本期不做：

- 资讯 RSS/LLM/Top20 页面与表（PRF-NEWS）
- Kafka / Celery / 多机 Scheduler
- 用户任意提交脚本或未注册任务类型

`NEWS_REFRESH` handler 在资讯管道未落地前：调用 stub `NewsService.refresh()`，写入明确 `result`（如 `news_pipeline_pending`），执行仍算走通队列，状态 `SUCCESS`。

---

## 15. 验收标准

| ID | 标准 |
| --- | --- |
| AC-08 | 启动后 APScheduler 加载已启用任务 |
| AC-09 | 到点：Scheduler → Redis → Worker 能跑完一轮 |
| AC-10 | FastAPI 请求不因任务执行阻塞 |
| AC-11 | 「立即执行」只入队，由 Worker 执行 |
| AC-12 | 结束后 `task_execution` 为 SUCCESS 或 FAILED |
| AC-13 | 超时/失败可重试，超次数 FAILED（可用测试注入，不接真 RSS） |
| AC-14 | 同一时刻不能有两个 `NEWS_REFRESH` 执行实例 |

---

## 16. 一句话

> APScheduler 只调度，Redis 做队列，arq Worker 执行，PostgreSQL 记任务与运行结果；AI资讯更新是第一种业务任务，页面在「基础」，不在「工具 → 资讯中心」。
