# 知域 — 操作审计需求文档（PRD-OPERATIONS）

**版本：** V1.0  
**模块：** 知域 → 监控 → 操作审计  
**状态：** 待开发（占位页已接入；数据与 API 待实现）  
**关联：** AI 决策审计见 [`PRD-DECISIONS.md`](PRD-DECISIONS.md)；定时任务执行记录见 [`PRD-Job.md`](PRD-Job.md)。

---

## 1. 需求背景

除 AI 问答决策链外，知域还存在大量**人与系统对数据的操作**：文档上传/导入、解析、切片、向量化、图谱抽取、URL 刷新、知识库与标签变更、登录登出、预订确认等。当前仅有文档 `status` 与定时任务 `task_execution`，**无统一操作台账**，无法按时间/操作人/对象追溯「这条数据怎么进来的、哪一步失败」。

本模块建设**项目级操作审计中心**（参考企业审计中心 UI）：列表台账 + 详情链路时间线，覆盖文档处理流水线与敏感操作。与决策审计并列，同属侧栏「监控」二级菜单。

---

## 2. 目标与非目标

### 2.1 目标

- 关键操作与后台流水线**审计级留痕**：谁、何时、做了什么、作用对象、来源 IP、结果、耗时。
- 文档处理 **pipeline trace**：导入 → 解析 → 切片 → 向量化 →（可选）摘要/标签/图谱抽取，同 `pipeline_trace_id` 串联。
- 监控 → 操作审计：列表、筛选、详情；文档详情页可跳转「处理记录」。
- 与 `task_execution`（定时任务）**并入展示**，不重复造调度历史页。
- **可扩展**：新业务能力通过注册 `action` 枚举 + 埋点写入，不改审计核心表。

### 2.2 非目标（本期不做）

- 全量 API 访问日志（数据量大，作 P2 可选 Tab）。
- AI 决策链详情（见 PRD-DECISIONS）。
- 多用户 RBAC / 审计员角色（本机个人库，Session 隔离即可）。

---

## 3. 产品入口

```text
侧栏「监控」
  ├── 决策审计   /monitoring/decisions   ← PRD-DECISIONS（优先实现）
  └── 操作审计   /monitoring/operations  ← 本文
```

**文档详情页（P1）**：「查看处理记录」→ `/monitoring/operations?resource=document&id=...` 或详情抽屉。

---

## 4. 与决策审计的关系

| 维度 | 操作审计 | 决策审计 |
| --- | --- | --- |
| 记什么 | 人/系统对资源的操作与流水线 | AI 如何决策与作答 |
| 典型事件 | 上传 PDF、向量化成功 | reason 选 RAG、引用 chunk |
| 主表 | `audit_event` | `decision_run` / `decision_span` |
| 实现顺序 | **第二批**（PRD-DECISIONS P0 完成后） | **第一批** |

**数据源策略：**

- Phase 1：**分表**，职责清晰；监控侧栏两个二级菜单各读各的 API。
- Phase 2（可选）：`audit_event.category = 'ai_decision'` 且 `ref_id → decision_run.id`，供「监控总览」统一检索；详情仍分 API。
- **共享**：前端「时间线 + 链路图」组件、`trace_id` 命名规范、列表页布局（对齐审计中心截图）。

---

## 5. 审计分类（页面 Tab）

操作审计页内 Tab（不必各占侧栏二级菜单）：

| Tab | 内容 |
| --- | --- |
| **操作审计** | 文档导入、重处理、向量化、图谱抽取、设置变更等 |
| **登录审计** | 登录、登出、失败尝试 |
| **敏感变更** | 删文档、删知识库、chunk 设置、预订写操作确认 |
| **异常审计** | 解析/向量化失败、任务 FAILED、AI 降级（可从决策审计同步摘要） |
| **接口访问** | （P2 可选）高频 API 采样 |

---

## 6. 数据模型

### 6.1 `audit_event`（主表）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | |
| `user_id` | UUID | 操作人；系统任务可为 null + `actor=system` |
| `actor` | enum | user / system / scheduler |
| `category` | enum | operation / auth / sensitive / anomaly / pipeline / api |
| `action` | string | 见 §6.2 |
| `resource_type` | string | document / knowledge_base / chunk / task / user / … |
| `resource_id` | string | 对象 ID |
| `summary` | text | 列表展示用事件标题 |
| `detail` | JSONB | 扩展元数据 |
| `result` | enum | success / failure / partial |
| `error_message` | text | 失败原因 |
| `source_ip` | string | |
| `request_uri` | string | 触发 API |
| `duration_ms` | int | |
| `pipeline_trace_id` | UUID | 同一次文档流水线共享 |
| `parent_event_id` | UUID | 可选，嵌套步骤 |
| `ref_id` | UUID | 可选，关联 decision_run 等 |
| `created_at` | timestamptz | |

索引：`(user_id, created_at)`、`(action, created_at)`、`(resource_type, resource_id)`、`(pipeline_trace_id)`、`(category, result)`。

### 6.2 `action` 枚举（可扩展注册）

**文档流水线：**

`document.upload` | `document.import_url` | `document.parse` | `document.chunk` | `document.vectorize` | `document.enrich` | `document.graph_extract` | `document.reindex` | `document.refresh_url` | `document.delete`

**知识库与配置：**

`knowledge_base.create` | `knowledge_base.delete` | `chunk_settings.update` | …

**认证：**

`auth.login` | `auth.logout` | `auth.login_failed`

**任务：**

`task.run` | `task.execution_success` | `task.execution_failed`（可与 `task_execution` 双写或视图聚合）

**敏感：**

`booking.confirm` | `booking.cancel` | …

新增 action：在 `app/audit/registry.py` 注册展示名与 severity，**不改表结构**。

### 6.3 文档流水线示例

```text
pipeline_trace_id = pt-abc
  [operation] document.upload        success  120ms   doc-xxx
  [pipeline]  document.parse           success  2.3s    pages=15
  [pipeline]  document.chunk           success  0.5s    chunks=42
  [pipeline]  document.vectorize       success  8.1s    model=...
  [pipeline]  document.enrich          success  3.2s    tags=3
  [pipeline]  document.graph_extract   success  5.0s    entities=12
```

---

## 7. 埋点位置（后端）

| 位置 | 事件 |
| --- | --- |
| `routers/documents.py` 上传/导入/删除 | upload, import_url, delete |
| `parse.py` 开始/成功/失败 | parse |
| `index.py` / `chunk.py` | chunk, vectorize |
| `chains.enrich_document_after_ready` | enrich |
| 图谱抽取 API | graph_extract |
| `routers/auth.py` | login, logout |
| `scheduler` / `task_execution` 完成回调 | task.* |
| `booking_agent` 写操作 | booking.confirm 等 |

统一入口：

```python
from app.audit import record_event

record_event(
    action="document.vectorize",
    resource_type="document",
    resource_id=str(doc_id),
    result="success",
    pipeline_trace_id=trace_id,
    duration_ms=elapsed,
    user_id=...,
)
```

FastAPI 中间件（P2）：可选记录 `api.access` 采样。

---

## 8. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/audit/events` | 分页列表；筛选 category、action、result、关键词、时间、resource |
| GET | `/api/audit/events/{id}` | 单条详情 |
| GET | `/api/audit/pipelines/{trace_id}` | 流水线时间线（多 event 聚合） |
| GET | `/api/documents/{id}/audit` | 文档维度快捷查询 |

鉴权：Session；仅返回当前 `user_id` 相关事件（本机个人库）。

---

## 9. 前端

### 9.1 列表（对齐审计中心截图）

列：审计时间、操作人、事件（模块/动作 + 耗时）、审计对象、来源 IP、结果、操作（详情）。

筛选：关键词（模块/动作/操作人/URI/IP）、结果、时间范围；列设置（localStorage）。

计数：当前页/总数；异常/失败数徽章。

### 9.2 详情

- 时间线：pipeline 各步顺序、输入输出摘要、错误栈（dev）。
- 跳转：文档阅读页、相关 `task_execution`。

### 9.3 样式

遵循 `web/style.md` §工具/基础页；与决策审计列表共用布局组件（P1 抽 `MonitoringTable`）。

---

## 10. 与定时任务的关系

- `task_execution` 继续作为 Worker 执行事实来源。
- 操作审计在任务完成时 **写入 `audit_event`**（或 DB 视图 `audit_event` UNION 查询 `task_execution`），监控页统一入口。
- 不在「基础 → 定时任务」重复做审计 UI；任务页保留执行历史简表，详情链到操作审计。

---

## 11. 实施分期

| 阶段 | 交付 | 依赖 |
| --- | --- | --- |
| **P0** | 占位页；`audit_event` 表；`record_event`；登录 + 文档上传/删除 | 无 |
| **P1** | 解析/向量化/图谱流水线埋点；列表+详情；文档页跳转 | parse/index 改造 |
| **P2** | 敏感变更 Tab；task 聚合；接口访问采样 | PRD-Job 已上线 |
| **P3** | 与决策审计共享组件；异常 Tab 联动 decision degraded | PRD-DECISIONS P2 |

**说明：** 优先 PRD-DECISIONS；操作审计 P0 可与决策 P0 并行占位，**数据写入建议从 PRD-DECISIONS P0 完成后开始**，避免两套基础设施同时抢焦点。

---

## 12. 技术约束

- FastAPI + PostgreSQL + Alembic；禁止 Celery。
- 写审计失败**不得阻断**主业务（try/except + 日志）；与决策 Recorder 降级策略一致。
- 本机 `127.0.0.1`；Session 身份。

---

## 13. 版本说明

- **V1.0**：本文档；监控二级菜单「操作审计」占位；实现排在 PRD-DECISIONS P0 之后。
