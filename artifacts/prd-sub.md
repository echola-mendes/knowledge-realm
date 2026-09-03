# 子需求：通用定时任务基础设施（PRD-Job）

> 需求来源：`docs/PRD-Job.md` V1.0  
> 状态：**已确认**

## 已确认决策

| # | 决策 |
| --- | --- |
| 1 | 同意引入 **Redis + arq + APScheduler**，并修订 `AGENTS.md` / `docs/TECH.md` |
| 2 | 前端入口：**基础 → 定时任务**，路由 `/basics/jobs` |
| 3 | 前端带**完整 CRUD**（新建/编辑/删除），类型下拉仅已注册 `task_type`；同类型仍只允许一条实例 |

## 需求理解

建设本机**通用定时任务基础设施**，调度与执行分离：

```text
APScheduler（何时）→ Redis Queue → arq Worker（执行）→ Handler → 业务 Service
PostgreSQL 持久化任务定义与执行记录
```

第一版注册业务类型 `NEWS_REFRESH`（AI 资讯更新）；handler 在资讯管道未落地前调用 stub `NewsService.refresh()`，写入 `result: { news_pipeline_pending: true }`，队列链路走通且状态为 SUCCESS。

定时触发与手动「立即执行」**同一条 Worker 路径**；FastAPI 路由只入队，不 await 业务。

## 功能范围

### 后端

- 数据表：`scheduled_task`、`task_execution`（Alembic 迁移）
- 种子任务：首次迁移/启动时写入「AI资讯更新」`NEWS_REFRESH`，默认 30 分钟、启用（若已存在则跳过）
- APScheduler 挂 FastAPI lifespan，从 DB 加载已启用任务
- Redis + arq Worker 独立进程（`python -m app.worker.worker`）
- 模块：`routers/task.py`、`scheduler/`、`jobs/news_job.py`、`worker/`、`models`
- API（Session 鉴权，全局一份任务，无 user_id 参数）：
  - `GET/POST/PUT/DELETE /api/tasks`
  - `POST /api/tasks/{id}/enable|disable|run`
  - `GET /api/tasks/{id}/executions`
  - `GET /api/tasks/types`（可选：返回已注册 task_type 列表，供前端下拉）
- 防重：同 `task_type` 同时只允许一个 RUNNING 实例
- 有限重试（约 3 次）+ 指数退避
- 环境变量：`REDIS_URL`
- 日志含 `task_id`、`run_id`、`task_type`、耗时、status

### 前端

- 入口：**基础 → 定时任务**，路由 `/basics/jobs`
- 页面：
  - 任务列表卡片（名称、间隔/Cron、启停、上次/下次执行）
  - 操作：立即执行、启用/停用、编辑、删除
  - **新建任务**按钮：名称 + 类型（下拉 NEWS_REFRESH 等）+ 调度（每 N 分钟 / 简单 Cron）
  - 最近执行历史（成功/失败）
- 样式遵循 `web/style.md`

### 文档

- 实施完成后更新 `docs/TECH.md`、`docs/PRD.md`、`AGENTS.md`

## 非目标

- 资讯 RSS/LLM/Top20 业务与页面（见 `PRF-NEWS.md`）
- Kafka / Celery / RabbitMQ / 多 Scheduler 集群
- 用户任意提交脚本或未注册 `task_type`
- 高级 Cron 表达式编辑器
- 分布式 Scheduler 锁

## 约束说明

- **同 task_type 唯一**：v1 每种已注册类型只允许一条 `scheduled_task` 记录（如 NEWS_REFRESH 只能建一条）
- **BackgroundTasks 保留**：文档解析等短任务仍用现有 BackgroundTasks
- **运行依赖**：本机 Redis + Worker 第二进程

## 验收标准（PRD-Job §15）

| ID | 标准 |
| --- | --- |
| AC-08 | 启动后 APScheduler 加载已启用任务 |
| AC-09 | 到点：Scheduler → Redis → Worker 能跑完一轮 |
| AC-10 | FastAPI 请求不因任务执行阻塞 |
| AC-11 | 「立即执行」只入队，由 Worker 执行 |
| AC-12 | 结束后 `task_execution` 为 SUCCESS 或 FAILED |
| AC-13 | 超时/失败可重试，超次数 FAILED |
| AC-14 | 同一时刻不能有两个 `NEWS_REFRESH` 执行实例 |
