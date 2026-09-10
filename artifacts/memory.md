# Memory

## 完成记录

| 子需求 | 日期 | 结果 | 验收 |
|---|---|---|---|
| 通用定时任务（PRD-Job） | 2026-09-04 | APScheduler+Redis+arq+任务页；NEWS_REFRESH handler 仍 stub | 全 ✅ |
| AI资讯（PRD-NEWS） | 2026-09-04 | news 表/管道/API/前端热榜；NEWS_REFRESH 接真实 refresh；源 yaml | 全 ✅ |
| AI决策审计（Trace.md V1.1） | 2026-09-06 | decision_run/span 表 + DecisionRecorder(app/audit/) + chat/knowledge 埋点 + 3 查询 API + 决策审计前端页 | 全 ✅ |
| 检索同节扩窗（PRD_Chunk_V0） | 2026-09-08 | search_chunks 返回前同 heading 扩窗 + original_content；不改表/debug | 全 ✅ |
| 父子切块落库（PRD_Chunk_V1） | 2026-09-08 | document_chunk role/parent_id；索引写 parent+child；检索仅 child + parent 组装/V0 降级 | 全 ✅ |
| 知识 Agent 编排优化（Sufficiency V0） | 2026-09-09 | knowledge_flow：analyze/Simple·Complex/decompose/sufficiency/rewrite/merge/gap/generate；审计 step+IO；详情页可读 | 全 ✅ |
| 局部邻居扩窗 + 双条件过滤（Chunk V3） | 2026-09-09 | search_chunks 门槛后 ±1 + 双条件；SearchHit 两字段；审计 assembly；Merge 按 chunk_id；TECH/PRD 同步 | 全 ✅ |
| ReAct graph.py 标准 Tool Calling 重构 | 2026-09-10 | tools 包+registry+configurable；graph=agent⇄tools；task=react 审计/SSE；agent knowledge 不接审计 | 全 ✅ |

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

### LangGraph config 注入要求注解严格为 RunnableConfig

日期：2026-09-06　来源：AI决策审计

问题：节点参数写成 `config: RunnableConfig | None = None` 后 LangGraph 不再注入 config（spans 全丢）。

解法：注解必须是 `RunnableConfig` 本体；需要测试直接调用时可加默认值 `= None`。

### 审计 run 行须随主事务落库（savepoint）

日期：2026-09-06　来源：AI决策审计

问题：Recorder 用独立 session 在主事务提交前写 `decision_run`，引用未提交 conversation 触发 FK 违反（被吞异常后静默丢链）。

解法：`start_run` 用 `session.begin_nested()`（savepoint）在主会话落 run 行，随主事务一起提交；spans 与终态仍走独立会话。

### 同节扩窗挂在 rerank 门槛之后

日期：2026-09-08　来源：检索同节扩窗 V0

问题：同节 child 被切散，只命中一块时上下文不完整。

解法：仅 `search_chunks` 返回前 `_expand_same_heading`；键 `(document_id, heading)`；整块预算 4000；`search_debug` 不扩窗；`original_content` 默认空串保兼容。

### Parent-Child：短节无空父、组装在门槛后

日期：2026-09-08　来源：父子切块落库 V1

问题：索引时既要 section 全文作 parent，又要避免短节多写空父行；检索侧仍要兼容未 reindex 数据。

解法：长节才写 `role=parent`（无 embedding、不进 ES）+ children；短节仅一行 `role=child`/`parent_id=null`。召回 `role=child AND embedding IS NOT NULL`；`search_chunks` 门槛后 `_assemble_parent_context`（同父去重、超预算整块回退），无 parent → V0 扩窗；`search_debug` 不组装。增量对齐键含 `role`/parent 结构。

### knowledge_flow：MAX_LOOPS 只计补充检索

日期：2026-09-09　来源：知识 Agent 编排优化（Sufficiency V0）

问题：若把每 Qi 初始检索也算进 `MAX_LOOPS`，与多 Qi 分解冲突。

解法：初始每 Qi 各检 1 次不计入；仅 Rewrite 后再检递增 `loop_count`；Simple 跳过 decompose，成功时 `search_knowledge`=1。

### task=knowledge 与 Master knowledge 分流

日期：2026-09-09　来源：知识 Agent 编排优化（Sufficiency V0）

问题：Design 要求不改 Master，但要替换知识 Agent 的 reason→run_tool。

解法：`_invoke_knowledge_graph` 改 `build_knowledge_flow_graph()`；Master `node_knowledge` 仍挂旧 `graph.py`。

### 审计详情：step + input/output 与 chat 双形态

日期：2026-09-09　来源：知识 Agent 编排优化（Sufficiency V0）

问题：knowledge 用 `decision.step/input/output`，chat 仍是 tool/summary。

解法：`DecisionAuditView` 有 step 时标题用 STEP_LABELS 并分区展示输入/输出；否则整段 pretty，chat 口径不变。

### V3 组装：邻居二次打分勿复用锚点 Rerank 分

日期：2026-09-09　来源：局部邻居扩窗 V3

问题：未命中邻居没有「原 Rerank 分」；若用全局 0.5 门槛会把邻居几乎全灭。

解法：仅锚点过 `RELEVANCE_MIN_SCORE`；邻居用更低的 `EXPAND_QUERY_MIN`（默认 0.3）+ `EXPAND_ANCHOR_MIN`（0.6）双条件；有 Rerank Key 时对去重邻居批量二次 `score_documents`，无 Key / 失败则 query–chunk 余弦。Merge 去重键改为 `chunk_id`，与「同父多命中保留多条」一致。

### Agent Tool：禁止闭包，用 configurable

日期：2026-09-10　来源：ReAct Tool Calling 重构

问题：闭包捕获 `session`/`user_id` 使 Tool Schema 污染、难测、与 knowledge_flow 复用冲突。

解法：`@tool` 仅业务参数；执行时从 LangGraph `configurable` 读 runtime；`tools_for(allow_web, enable_graph)` 门控 bind 子集。

### task=react 审计/SSE 与共用图解耦

日期：2026-09-10　来源：ReAct Tool Calling 重构

问题：`graph.py` 同时被 `task=react` 与 Master knowledge 调用，不能把审计/新 SSE 绑死在图内。

解法：审计 `decision_recorder` 与 react 专用 SSE（`_stream_react_graph`）仅在 react 路由注入；Master knowledge 共用图但不传 recorder；stream 另保留 `token`/`citations` 兼容旧前端。

---

## 2026-09-10：ReAct graph.py 标准 Tool Calling 重构完成

- `app/agent/tools/`：knowledge/graph/web/text2sql + registry；旧 import 薄 re-export
- `graph.py`：`bind_tools` + `ToolNode` + `tools_condition`；无手写 JSON action
- `task=react`：多库检索 A1；`mode=react` + tool_call/tool_result span；SSE 中间事件 + token/citations 兼容
- Master knowledge / knowledge_flow / booking / plan 边界未改；文档已同步 architecture/PRD/TECH/Trace
- 契约：`test_react_sse.py` 等；临时文件 prd-sub / execution-plan 保留待下轮清空
