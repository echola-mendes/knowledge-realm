可以。下面这份我建议直接作为 **AI 资讯 + 通用定时任务基础设施的完整需求文档**，后续可以交给 Cursor 按文档开发。

# AI 资讯与定时任务系统需求文档

**版本：V1.0**
**模块：知域 → 工具 → AI资讯**
**状态：待开发**

---

# 1. 需求背景

在「知域 → 工具」中新增 **AI资讯**，用于聚合科技、AI技术、金融领域的实时资讯，并通过 LLM 对资讯进行分类、摘要、重要性判断和热度排序。

同时建设一个**通用定时任务基础设施**，AI资讯更新作为第一个定时任务。

系统需要满足：

* 定时自动采集资讯
* 自动去重
* LLM 分类、摘要、重要性判断
* 生成三个分类的每日 Top 20
* 支持手动立即执行
* 支持查看任务执行历史
* 任务执行不能阻塞 FastAPI
* 后续能够扩展其他后台任务

---

# 2. 核心原则

## 2.1 调度与执行分离

定时任务系统必须遵循：

```text
Scheduler
    ↓
Redis Queue
    ↓
Worker
    ↓
Business Service
```

其中：

* **APScheduler**：只负责「什么时候执行」
* **Redis**：负责任务队列
* **Worker**：负责真正执行任务
* **Service**：负责业务逻辑
* **PostgreSQL**：负责业务数据和任务执行记录

禁止：

```text
APScheduler
    ↓
直接执行 NewsService
```

---

# 3. 技术架构

## 3.1 技术选型

| 模块      | 技术             |
| ------- | -------------- |
| Web API | FastAPI        |
| 定时调度    | APScheduler    |
| 队列      | Redis          |
| Worker  | arq            |
| HTTP    | httpx          |
| LLM     | 项目现有 LLM 服务    |
| 数据库     | PostgreSQL     |
| ORM     | 项目现有方案         |
| RSS     | RSS/Atom       |
| 日志      | Python logging |

---

# 4. 总体架构

```text
                         ┌──────────────┐
                         │   Frontend   │
                         └──────┬───────┘
                                │
                                ↓
                         ┌──────────────┐
                         │   FastAPI    │
                         │              │
                         │ News API     │
                         │ Task API     │
                         └──────┬───────┘
                                │
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ↓                       ↓
              News Query              APScheduler
                                            │
                                      enqueue task
                                            ↓
                                     ┌────────────┐
                                     │   Redis    │
                                     │   Queue    │
                                     └─────┬──────┘
                                           │
                                           ↓
                                     ┌────────────┐
                                     │   Worker   │
                                     │    arq     │
                                     └─────┬──────┘
                                           │
                                           ↓
                                    News Service
                                           │
                  ┌────────────────────────┼─────────────────────┐
                  ↓                        ↓                     ↓
             RSS / API                   LLM               PostgreSQL
                  │                        │                     │
                  ↓                        ↓                     ↓
               采集                     分类/摘要             持久化
                                         评分
                                           │
                                           ↓
                                      Top20 排名
```

---

# 5. AI资讯功能

## 5.1 入口

产品：

```text
知域
 └── 工具
      └── AI资讯
```

---

# 6. AI资讯分类

第一版固定三个分类：

```text
科技
AI技术
金融
```

内部枚举：

```python
technology
ai
finance
```

暂不允许用户自定义分类。

---

# 7. AI资讯首页

页面：

```text
AI资讯

[ 科技 ] [ AI技术 ] [ 金融 ]

今日热榜
2026-09-03

01  新闻标题
    AI摘要内容……
    XXX来源 · 2小时前              🔥98

02  新闻标题
    AI摘要内容……
    XXX来源 · 3小时前              🔥95

...

20  新闻标题
    AI摘要内容……
    XXX来源 · 12小时前             🔥71
```

---

# 8. 单条资讯展示

每条资讯至少展示：

* 排名
* 标题
* AI 摘要
* 来源
* 发布时间
* 热度
* 分类

例如：

```text
01
OpenAI 发布新模型……

新模型重点提升长上下文和工具调用能力……

OpenAI · 2小时前
🔥 98
```

点击资讯后进入详情。

---

# 9. 资讯详情

详情至少包含：

```text
标题

来源
发布时间

AI摘要

正文/原始内容

原文链接
```

点击「原文链接」跳转来源网站。

---

# 10. 资讯采集

## 10.1 数据来源

第一版优先使用：

```text
RSS / Atom
官方 API
公开资讯 API
```

不优先使用复杂网页爬虫。

---

# 11. 资讯采集流程

```text
RSS/API
   ↓
请求数据
   ↓
解析
   ↓
标准化
   ↓
URL去重
   ↓
标题Hash去重
   ↓
保存原始资讯
   ↓
LLM处理
   ↓
分类
   ↓
摘要
   ↓
重要性
   ↓
热度计算
   ↓
更新Top20
```

---

# 12. 新闻标准数据模型

统一转换成：

```python
NewsItem
```

包含：

```text
title
source
url
content
published_at
category
summary
importance_score
heat_score
content_hash
```

---

# 13. 新闻去重

第一版使用两级去重。

## 13.1 URL去重

相同 URL：

```text
直接认为重复
```

数据库建立唯一约束。

---

## 13.2 标题 Hash

对标题进行标准化：

```text
去除空格
统一大小写
去除无意义符号
```

然后：

```text
SHA256(normalized_title)
```

保存：

```text
content_hash
```

相同 Hash 认为重复。

---

# 14. 暂不做语义去重

第一版不使用 Embedding 做新闻语义去重。

暂时不做：

```text
新闻A embedding
新闻B embedding
      ↓
向量相似度
      ↓
判断是否重复
```

原因：

* 增加复杂度
* 增加 Embedding 成本
* 第一版 URL + 标题去重已经足够

后续资讯量变大后再增加。

---

# 15. LLM处理

每条新闻进入 LLM 处理流程。

LLM 负责：

### 15.1 分类

只能输出：

```text
technology
ai
finance
```

---

### 15.2 摘要

生成简洁中文摘要。

要求：

* 事实准确
* 不添加原文不存在的信息
* 不夸大
* 不编造
* 重点突出

---

### 15.3 重要性评分

输出：

```text
1～10
```

示例：

```text
10 = 行业重大事件
8  = 重要行业动态
6  = 一般行业新闻
3  = 较低价值信息
1  = 信息价值很低
```

---

# 16. 金融资讯约束

金融类别只提供：

```text
事实
新闻摘要
信息聚合
```

不得生成：

```text
买入建议
卖出建议
投资建议
股票推荐
收益预测
```

例如：

❌

> 建议买入 NVIDIA。

✅

> NVIDIA 发布季度业绩，公司营收同比增长……

---

# 17. 热度计算

每条新闻计算：

```text
heat_score
```

范围：

```text
0～100
```

建议综合：

```text
重要性
+
来源权重
+
时间新鲜度
+
跨来源出现次数
```

---

# 18. 新鲜度衰减

可以采用：

| 发布时间    |         新鲜度 |
| ------- | ----------: |
| 0～1小时   |        100% |
| 1～3小时   |         90% |
| 3～6小时   |         75% |
| 6～12小时  |         55% |
| 12～24小时 |         30% |
| >24小时   | 不参与当日 Top20 |

具体权重允许后续调整。

---

# 19. 每日 Top20

每个分类维护：

```text
科技 Top20
AI技术 Top20
金融 Top20
```

即：

```text
3 × 20 = 60
```

条当前排行榜。

---

# 20. Top20不是每天只生成一次

采用：

> **持续刷新当前日期 Top20**

例如：

```text
14:00
    ↓
科技 Top20

14:30
    ↓
采集新资讯
    ↓
重新计算
    ↓
科技 Top20

15:00
    ↓
再次刷新
```

因此用户看到的是：

> **当天实时更新的 Top20**

而不是凌晨一次性生成。

---

# 21. 定时任务系统

这是一个独立的基础设施模块。

AI资讯只是第一个任务。

未来可以扩展：

```text
NEWS_REFRESH
KNOWLEDGE_SYNC
REPORT_GENERATE
AGENT_TASK
...
```

---

# 22. 定时任务模型

建立：

```text
scheduled_task
```

字段：

```text
id
name
task_type
schedule_type
schedule_config
enabled
last_run_at
next_run_at
created_at
updated_at
```

---

# 23. task_type

第一版：

```text
NEWS_REFRESH
```

未来：

```text
KNOWLEDGE_SYNC
REPORT_GENERATE
AGENT_TASK
```

---

# 24. schedule_type

支持：

```text
INTERVAL
CRON
```

例如：

```text
INTERVAL
{
    "minutes": 30
}
```

或者：

```text
CRON
{
    "hour": 8,
    "minute": 0
}
```

---

# 25. 前端定时任务配置

普通用户不需要直接写 Cron。

提供：

```text
执行方式

○ 每N分钟
○ 每天
○ 每周
○ 高级 Cron
```

例如：

```text
AI资讯更新

执行频率：
[ 每 30 分钟 ▼ ]

状态：
● 已启用
```

高级用户才使用 Cron。

---

# 26. AI资讯默认任务

系统初始化：

```text
任务名称：
AI资讯更新

任务类型：
NEWS_REFRESH

执行频率：
每30分钟

状态：
启用
```

---

# 27. 定时任务执行流程

```text
APScheduler
     ↓
到达执行时间
     ↓
创建 task_execution
     ↓
Redis enqueue
     ↓
Worker 获取任务
     ↓
执行 NewsService
     ↓
成功 / 失败
     ↓
更新 task_execution
```

---

# 28. Redis的职责

Redis 第一版只承担：

### 任务队列

```text
Scheduler
    ↓
Redis
    ↓
Worker
```

第二阶段可以增加：

### 分布式锁

例如：

```text
news:refresh:lock
```

用于防止多个 NEWS_REFRESH 同时执行。

Redis 暂时不作为主要业务数据库。

---

# 29. Worker

Worker 使用：

```text
arq
```

独立进程运行。

例如：

```bash
python -m app.worker.worker
```

Worker 负责：

```text
获取 Redis 任务
      ↓
识别 task_type
      ↓
调用对应 handler
      ↓
执行任务
      ↓
记录结果
```

---

# 30. Worker Handler

例如：

```text
worker/
└── handlers/
    └── news_handler.py
```

处理：

```text
NEWS_REFRESH
```

调用：

```text
news/service.py
```

---

# 31. FastAPI不能执行新闻任务

禁止：

```python
@app.post(...)
async def xxx():
    await news_service.refresh()
```

也禁止：

```text
APScheduler
    ↓
NewsService
```

应该：

```text
API
 ↓
enqueue
 ↓
Redis
 ↓
Worker
```

---

# 32. 手动执行

后台任务页面提供：

```text
[立即执行]
```

点击之后：

```text
POST /api/tasks/{id}/run
```

接口不能直接执行新闻任务。

而是：

```text
API
 ↓
Redis
 ↓
Worker
```

因此：

> 定时触发和手动触发最终走同一套 Worker。

---

# 33. 防止重复执行

需要防止：

```text
14:00任务还没结束
        ↓
14:30再次触发
```

建议使用：

```text
Redis Lock
```

或者任务执行状态判断。

策略：

```text
已有 NEWS_REFRESH RUNNING
        ↓
新的 NEWS_REFRESH
        ↓
跳过本次
```

避免多个新闻任务同时进行大量 LLM 调用。

---

# 34. 任务执行记录

建立：

```text
task_execution
```

字段：

```text
id
task_id
started_at
finished_at
status
result
error_message
created_at
```

状态：

```text
PENDING
RUNNING
SUCCESS
FAILED
```

---

# 35. 执行记录示例

```text
AI资讯更新

✓ 14:30
成功
采集 86 条
去重后 61 条
处理 61 条
更新 Top20

✓ 14:00
成功
采集 73 条
去重后 54 条

✕ 13:30
失败
RSS timeout
```

---

# 36. 重试机制

Worker 对外部请求失败进行有限重试。

例如：

```text
第一次失败
 ↓
等待
 ↓
第二次
 ↓
失败
 ↓
第三次
 ↓
失败
 ↓
任务 FAILED
```

采用指数退避。

不要无限重试。

---

# 37. 超时控制

以下操作必须有 timeout：

```text
RSS 请求
HTTP API
LLM 请求
数据库操作
```

例如：

```text
RSS timeout = 10s
LLM timeout = 60s
```

具体值可以根据现有项目统一配置。

---

# 38. Job Payload

Redis 中建议传递：

```json
{
  "task_id": 1,
  "task_type": "NEWS_REFRESH",
  "run_id": "xxx"
}
```

其中：

```text
task_id
```

用于定位定时任务。

```text
run_id
```

用于定位一次具体执行。

这样 Worker 不需要自己猜是哪一次执行。

---

# 39. API设计

## 新闻

```http
GET /api/news/hot
```

返回当天三个分类。

---

```http
GET /api/news/hot?category=technology
```

---

```http
GET /api/news/{id}
```

---

# 40. 首页接口

推荐：

```http
GET /api/news/hot
```

返回：

```json
{
  "date": "2026-09-03",
  "technology": [],
  "ai": [],
  "finance": []
}
```

这样前端首页一次请求即可。

---

# 41. 任务API

```http
GET /api/tasks
```

查询任务。

```http
POST /api/tasks
```

创建任务。

```http
PUT /api/tasks/{id}
```

修改任务。

```http
DELETE /api/tasks/{id}
```

删除任务。

```http
POST /api/tasks/{id}/enable
```

启用。

```http
POST /api/tasks/{id}/disable
```

禁用。

```http
POST /api/tasks/{id}/run
```

立即执行。

```http
GET /api/tasks/{id}/executions
```

查看执行历史。

---

# 42. 数据库

## news

```text
id
title
source
url
content
summary
category
importance_score
heat_score
published_at
content_hash
created_at
updated_at
```

索引建议：

```text
url UNIQUE
content_hash INDEX
category INDEX
published_at INDEX
heat_score INDEX
```

---

# 43. news_daily_rank

```text
id
news_id
rank_date
category
rank
score
created_at
```

唯一约束：

```text
(rank_date, category, rank)
```

或者根据最终实现采用适合的唯一索引。

---

# 44. scheduled_task

```text
id
name
task_type
schedule_type
schedule_config
enabled
last_run_at
next_run_at
created_at
updated_at
```

---

# 45. task_execution

```text
id
task_id
started_at
finished_at
status
result
error_message
created_at
```

---

# 46. Python目录结构

建议：

```text
server/
└── app/
    ├── api/
    │   ├── news.py
    │   └── task.py
    │
    ├── news/
    │   ├── collector.py
    │   ├── parser.py
    │   ├── dedup.py
    │   ├── summarizer.py
    │   ├── scorer.py
    │   └── service.py
    │
    ├── scheduler/
    │   ├── scheduler.py
    │   ├── task.py
    │   └── executor.py
    │
    ├── worker/
    │   ├── worker.py
    │   ├── queue.py
    │   └── handlers/
    │       └── news_handler.py
    │
    ├── jobs/
    │   └── news_job.py
    │
    ├── models/
    │   ├── news.py
    │   └── task.py
    │
    └── ...
```

---

# 47. 各模块职责

### `api/news.py`

只负责：

```text
HTTP
参数校验
调用 NewsService
返回 Response
```

---

### `api/task.py`

负责：

```text
任务CRUD
启用/禁用
立即执行
执行历史
```

---

### `scheduler/scheduler.py`

负责：

```text
启动 APScheduler
注册任务
删除任务
更新任务
```

**不写业务代码。**

---

### `scheduler/executor.py`

负责：

```text
task_type
    ↓
对应 Job
```

但最终只负责：

```text
enqueue
```

---

### `jobs/news_job.py`

负责：

```text
NEWS_REFRESH
    ↓
Redis
```

不执行新闻业务。

---

### `worker/worker.py`

Worker 入口。

---

### `worker/queue.py`

统一封装：

```text
enqueue
```

避免业务代码到处直接操作 Redis。

---

### `worker/handlers/news_handler.py`

真正执行：

```text
NewsService.refresh()
```

---

### `news/service.py`

新闻业务总编排：

```text
collector
 ↓
parser
 ↓
dedup
 ↓
summarizer
 ↓
scorer
 ↓
database
 ↓
ranking
```

---

# 48. 进程结构

开发环境：

```text
Terminal 1
uvicorn app.main:app

Terminal 2
python -m app.worker.worker
```

如果 Scheduler 集成在 FastAPI：

```text
FastAPI
 └── APScheduler
```

Worker：

```text
独立进程
```

---

# 49. 单实例要求

第一版默认：

```text
1个 FastAPI
1个 Scheduler
1个 Worker
```

如果未来：

```text
FastAPI × 3
```

不能让三个实例都执行 APScheduler。

否则：

```text
实例A → NEWS_REFRESH
实例B → NEWS_REFRESH
实例C → NEWS_REFRESH
```

会重复执行。

因此未来扩容时需要：

```text
独立 Scheduler
```

或者：

```text
分布式调度锁
```

第一版暂不实现，但架构必须预留。

---

# 50. 配置

环境变量建议：

```text
REDIS_URL=
NEWS_REFRESH_INTERVAL=
NEWS_LLM_TIMEOUT=
NEWS_HTTP_TIMEOUT=
NEWS_MAX_ITEMS=
NEWS_TOP_K=20
```

以及项目现有 LLM 配置。

不要把 Redis、LLM 等配置硬编码。

---

# 51. 日志

任务执行至少记录：

```text
task_id
run_id
task_type
开始时间
结束时间
耗时
采集数量
去重数量
LLM处理数量
Top20数量
错误信息
```

例如：

```text
[NEWS_REFRESH]
task_id=1
run_id=abc
collected=86
deduplicated=61
processed=61
duration=32.4s
status=SUCCESS
```

---

# 52. 错误处理

单条新闻处理失败：

```text
不能导致整个任务失败
```

例如：

```text
100条新闻

第37条 LLM失败
        ↓
记录错误
        ↓
继续处理38～100
```

最终：

```text
成功处理 99
失败 1
```

任务仍然可以：

```text
SUCCESS
```

但 result 中记录失败数量。

如果整个 RSS 服务不可用：

```text
任务 FAILED
```

---

# 53. 前端定时任务页面

建议放在：

```text
设置 / 系统管理
    ↓
定时任务
```

**不要放到「工具 → AI资讯」里面。**

因为：

```text
AI资讯 = 业务功能

定时任务 = 系统基础设施
```

---

# 54. 定时任务页面

```text
定时任务

┌────────────────────────────────────┐
│ AI资讯更新       每30分钟   ●启用  │
│                                    │
│ 上次执行：14:30                    │
│ 下次执行：15:00                    │
│                                    │
│ [立即执行] [停用]                  │
└────────────────────────────────────┘
```

下面：

```text
最近执行

14:30   ✓ 成功   86 → 61 → Top20
14:00   ✓ 成功   73 → 54 → Top20
13:30   ✕ 失败   RSS timeout
```

---

# 55. AI资讯与任务系统的边界

非常重要：

```text
工具
└── AI资讯
     ├── 新闻展示
     ├── 新闻详情
     └── Top20
```

而：

```text
系统
└── 定时任务
     ├── AI资讯更新
     ├── 知识库同步
     ├── Report生成
     └── Agent任务
```

AI资讯**使用**定时任务系统，但不拥有定时任务系统。

---

# 56. MVP范围

第一版必须实现：

### AI资讯

* [x] 科技
* [x] AI技术
* [x] 金融
* [x] RSS/API采集
* [x] URL去重
* [x] 标题Hash去重
* [x] LLM分类
* [x] LLM摘要
* [x] LLM重要性
* [x] 热度计算
* [x] 三分类 Top20
* [x] 资讯详情
* [x] 原文链接

### 定时任务

* [x] APScheduler
* [x] Redis
* [x] arq Worker
* [x] NEWS_REFRESH
* [x] 每30分钟
* [x] 手动执行
* [x] 启用/禁用
* [x] 执行记录
* [x] 失败记录
* [x] 重试
* [x] timeout
* [x] 防重复执行

---

# 57. MVP明确不做

第一版不要做：

```text
❌ Kafka
❌ Celery
❌ RabbitMQ
❌ XXL-JOB
❌ 多 Scheduler 集群
❌ Embedding 语义去重
❌ 多 Agent
❌ 用户自定义新闻分类
❌ 个性化推荐
❌ 投资建议
❌ 复杂网页爬虫
```

---

# 58. 后续扩展

架构需要支持未来增加：

```text
NEWS_REFRESH
     ↓
KNOWLEDGE_SYNC
     ↓
REPORT_GENERATE
     ↓
AGENT_TASK
     ↓
KB_AUTO_UPDATE
```

Worker 结构：

```text
handlers/
├── news_handler.py
├── knowledge_handler.py
├── report_handler.py
└── agent_handler.py
```

无需修改 Redis/Scheduler 核心架构。

---

# 59. 核心验收标准

## AI资讯

### AC-01

进入：

```text
知域 → 工具 → AI资讯
```

能够看到：

```text
科技 / AI技术 / 金融
```

---

### AC-02

每个分类最多显示：

```text
20条
```

---

### AC-03

新闻能够展示：

```text
标题
摘要
来源
时间
热度
```

---

### AC-04

同一 URL 不得重复出现。

---

### AC-05

同标题资讯经过标准化后不得重复。

---

### AC-06

LLM 只能将资讯归入三个合法分类。

---

### AC-07

金融资讯不得生成投资建议。

---

# 60. 定时任务验收

### AC-08

启动系统后：

```text
APScheduler
```

能够正常加载启用任务。

---

### AC-09

到达执行时间：

```text
Scheduler
 ↓
Redis
 ↓
Worker
```

任务能够正常执行。

---

### AC-10

FastAPI 请求不会因为新闻任务执行而阻塞。

---

### AC-11

手动点击：

```text
立即执行
```

也必须进入 Redis Worker。

---

### AC-12

任务执行结束后：

```text
task_execution
```

能够记录：

```text
SUCCESS / FAILED
```

---

### AC-13

RSS/LLM超时能够：

```text
重试
```

超过次数后：

```text
FAILED
```

---

### AC-14

同一时间不能存在两个：

```text
NEWS_REFRESH
```

执行实例。

---

# 61. 最终架构结论

整个功能最终确定为：

```text
                 知域
                  │
          ┌───────┴───────┐
          │               │
        工具            系统管理
          │               │
        AI资讯           定时任务
          │               │
          └───────┬───────┘
                  │
              NEWS_REFRESH
                  │
             APScheduler
                  │
                  ↓
                Redis
                  │
                  ↓
              arq Worker
                  │
                  ↓
             NewsService
                  │
        ┌─────────┼─────────┐
        ↓         ↓         ↓
      RSS/API    LLM    PostgreSQL
        │         │         │
        └─────────┼─────────┘
                  ↓
             热度计算
                  ↓
            Top20 × 3
                  ↓
               API
                  ↓
               前端
```

**一句话定稿：**

> **AI资讯是第一个业务定时任务；APScheduler 负责调度，Redis 负责队列，arq Worker 负责执行，NewsService 负责业务，PostgreSQL 负责持久化。**

