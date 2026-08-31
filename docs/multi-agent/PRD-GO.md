# GoGo Agent 蓝本 — 知域重建对照

> 本文回答三个问题：**GoGo 代码里有什么？知域个人出行 Agent 做哪几条、绝对不做哪几条？工程增强项何时按需加回？**
>
> 与 [README.md](README.md) 的分工：README 记录 GoGo「已经做了什么」；本文是知域重建的**范围边界 + 架构对照 + 工程删减回填手册**。实施规格以 [PRD-P4.md](PRD-P4.md) 为准。

---

## 一、定位

| 维度 | GoGo（Java 参考实现） | 知域（FastAPI + LangGraph，按 P4 重建） |
|---|---|---|
| 产品形态 | 企业差旅全生命周期 | **个人出行**（规划 / 定制 / 搜订机酒） |
| 用户身份 | 预置员工 + ADMIN 审批 | **Session 当前用户**，无企业 RBAC |
| 写操作确认 | 内部审批页 + 预订 HITL | **仅本人 HITL**（下单/取消） |
| 统一入口 | `ChatController` → 管道 → Master | `/api/agent`（及 stream）→ 薄意图 → Master |
| 子能力数量 | Master 挂 **4** 个业务工具（见 §三） | Master 挂 **3** 个：`knowledge` / `plan` / `booking` |

**三条结论（知域视角）：**

1. **链路 A（RAG）**：知域已有 `p1/graph.py`，**只导语料、不重建检索**；并入 `knowledge` 子能力，不另起 `info_agent`。
2. **第一条完整链路 = C 规划 + D 预订**（个人 HITL）；GoGo 的链路 B（企业差旅单）**不在知域范围**。
3. **裁剪分两类**：① **业务项**（企业/报销等）→ §二「绝对不做」，禁止回写 P4；② **工程增强**（熔断/压缩/三层意图等）→ §六回填手册，有症状再加。

---

## 二、知域范围边界

### 2.1 做（对齐 GoGo 骨架，非 1:1 集成）

| 能力 | 知域落地（P4） | GoGo 对照 |
|---|---|---|
| 多 Agent 骨架 | Supervisor + Agents-as-Tools；`forwardEvents(false)` | `MasterAgent` + `SubAgentProvider` |
| 薄意图 | 一次结构化：`knowledge \| plan \| booking \| chat` | L1/L2/L3 + 改写（知域本批不做） |
| 知识问答 | `knowledge` ← 现有 `p1/graph.py` | `InfoAgent`（RAG×3 + MCP） |
| 行程规划 | `itinerary_plan_agent`：搜机酒、`plan_itinerary`、`save_plan_html` | `ItineraryPlanAgent` |
| 预订执行 | `booking_agent`：HITL → `book_*` / `cancel_*` / `list_bookings` | `BookingAgent` |
| SSE 进度与卡片 | `progress` / `travel_data` / `plan_html` 等 | `ProgressNotifierHook` + `ChatSseNotifier` |
| 预订落库 | `booking_record` + Hook | `BookingPersistenceHook` |
| 对象存储 | MinIO：行程方案页 + `task=report` 知识报告（软依赖） | `PlanHtmlTools` + p1 报告链路 |
| 长期偏好 | 现有 `user_memory` LTM | 百炼 AGENT_CONTROL（知域不用） |
| HITL | `pending_action` + 确认卡片（本人） | `UserInteractionTools` + 预订确认 |

### 2.2 绝对不做（禁止回写 P4 / implementation-plan）

> 以下项在知域**无挂载点**或**与产品定位冲突**；学习 GoGo 代码时可浏览，**不得**作为 P4/P5 默认需求。

| 类别 | 具体项 | GoGo 代码（仅参考） | 知域替代 / 说明 |
|---|---|---|---|
| **企业差旅** | 差旅单申请 / 修改 / 取消 | `ItineraryManageAgent`、`TravelOrderWriteTools` | 对话内补问 + plan/booking HITL |
| **企业差旅** | 内部审批、审批页、审批状态机 | `AdminApprovalController`、`ApprovalService` | 本人确认卡片，无 `/approvals` |
| **企业差旅** | 差旅单冲突检测（重叠/跨城） | `TravelOrderConflictTools` | — |
| **企业差旅** | 职级 × 城市等级预算/舱位引擎 | `PolicyTools`、`business/policy/` | 口头偏好 + `user_memory` |
| **企业差旅** | 企业角色 / RBAC / EasyNextAdmin | `user_account` 角色、管理后台 | Session 单用户 |
| **企业集成** | 钉钉 / 企微 outbound + 审批回调 | `ApprovalCallbackController` | — |
| **报销** | 发票识别、报销单生成 | `ReimbursementAgent`（stub）、`ReimbursementTools` | P5 亦默认不做 |
| **Agent** | `itinerary_manage_agent` | Master 四工具之一 | 不注册 |
| **Agent** | 独立 `info_agent` | `InfoAgent` | 并入 `knowledge`（p1） |
| **Agent** | `ItineraryReviewAgent`（独立 ReAct） | 仅 Debug 入口；线上走 Tool | 需要时做 `ItineraryReviewTools` 类工具，不做 Agent |
| **Agent** | `ReimbursementAgent` | `build()` 返回 null | — |
| **基建** | 百炼长期记忆 | `agent/memory/*` | `user_memory` LTM |
| **基建** | Celery 异步任务队列 | — | `BackgroundTasks` 或同步；不上 Celery |
| **本批** | 火车票 | Plan Skill 扩展 | P4 不做 |
| **本批** | 三层意图 L1/L2/L3 + 查询改写 | `IntentRuleMatcher` 等 | 薄意图；P5 有症状再上 L1 规则 |

### 2.3 可用基建（非绝对不做）

| 项 | 知域用法 |
|---|---|
| **Redis** | **可用**。熔断状态、ApiKey 缓存、写操作限流、多实例中断广播等；会话/Checkpoint 仍以 Postgres 为主，**不为对齐 GoGo 强行上 Redis**，有场景再用 |
| **MinIO** | **可用**（软依赖）。行程方案页（`plan_html`）+ 知识报告（`task=report`）；key 前缀分离，见 P4 §8.2 |

### 2.4 本批不做、P5 有条件（见 PRD-P4 §11）

工具熔断、Token 压缩、多源兜底链、供应商 Key 加密落库、L1 意图规则等——**不是「永远不做」**，记入 §六；无对应症状时不提前建设。

---

## 三、架构对照（以代码实测为准）

### 3.1 GoGo 运行时拓扑（4 业务工具）

```
用户 → ChatController → AgentPipelineService
                          │
        ┌─────────────────┼─────────────────┐
        │ 意图管道（知域本批不照搬）          │
        │ L1 规则 → L2 向量 → 改写 → L3 LLM │
        └─────────────────┬─────────────────┘
                          ▼
                   MasterAgent
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
manage_agent      plan_agent          info_agent
（知域删除）            │                    │
                   review=Tool          booking_agent
                   （非独立 Agent）      （与 plan 平级）
```

**必读两点：**

1. 子 Agent 之间是 **Master 的工具调用**，同进程、无互发消息（知域同样采用 Agents-as-Tools）。
2. `booking_agent` 与 `itinerary_plan_agent` **平级**挂在 Master 上；`ItineraryReviewAgent` **未挂主链路**，六维审核走 `ItineraryReviewTools`。

### 3.2 知域 P4 拓扑（3 业务工具）

```
/api/agent(/stream)
  → 薄意图（knowledge | plan | booking | chat）
  → MasterAgent
       ├── knowledge          ← p1/graph.py
       ├── itinerary_plan_agent
       └── booking_agent
```

### 3.3 GoGo「9 个 ReActAgent」与知域映射

| GoGo ReActAgent | 主链路？ | 知域 |
|---|---|---|
| QueryRewritingAgent | 管道，条件触发 | 本批不做（薄意图） |
| IntentRecognitionAgent | 管道，L3 兜底 | 本批不做 |
| MasterAgent | ✅ | MasterAgent |
| ItineraryManageAgent | ✅ Master 工具 | **删除** |
| ItineraryPlanAgent | ✅ Master 工具 | `itinerary_plan_agent` |
| BookingAgent | ✅ Master 工具 | `booking_agent` |
| InfoAgent | ✅ Master 工具 | `knowledge`（p1） |
| ItineraryReviewAgent | ❌ 仅 Debug | Tool 形态，按需 |
| ReimbursementAgent | ❌ stub | **删除** |

另：会话标题、推荐问题在 GoGo 为**单次 LLM 的 `@Service`**，不计入上述 9 个，知域可沿用同类旁路。

### 3.4 横切能力对照

| 能力 | GoGo | 知域 P4 |
|---|---|---|
| HITL | `UserInteractionTools` | `pending_action` + 确认卡片 |
| SSE | 12 类事件 | 本批：`progress` / `travel_data` / `plan_html` + 预订结果 |
| 会话持久化 | `SessionPersistenceHook` | 现有会话/消息表 |
| 预订落库 | `BookingPersistenceHook` | 本批必做 |
| 政策规则引擎 | `PolicyTools` | **绝对不做** |
| 长期记忆 | 百炼 AGENT_CONTROL | `user_memory` |

---

## 四、知域渐进走通路线（起点 = 链路 C）

> 依赖核对见 §七。GoGo 本地验证若需跑通企业链路 B，见**附录 A**（非知域交付范围）。

### 阶段 1：TRAVEL-PLAN-1（链路 C）

**走通标准：**

1. 「下周二去上海、周四返回，经济舱」→ 意图 `plan` → `itinerary_plan_agent` → 方案卡片；
2. 途牛无 Key 时落到 **flyai trial** 或明确备源失败提示；
3. `plan_itinerary` 输出可对比多套方案；口头改偏好不丢日期/城市；
4. SSE 可见 `plan_html`；MinIO 已配可历史回看，未配时实时可用；
5. `/api/chat` 可保留；知识问答复用 `/api/agent` → `knowledge`；`task=report` 可回看 MinIO

**GoGo 代码导航**：`ItineraryPlanAgent.java` → `skills/flyai/` → `ItineraryPlannerTool.java` → `PlanHtmlTools.java` → `ItineraryReviewTools.java`（工具，非 Review Agent）。

### 阶段 2：TRAVEL-BOOK-1（链路 D）

**走通标准：**

1. 意图 `booking` → `booking_agent` → 本人 HITL 确认后才 `book_*`；
2. 成功写入 `booking_record`；透出支付链接（若有）；
3. `list_bookings` 仅当前用户；`cancel_booking` 须 HITL；
4. 供应商 Key 不出现在前端与仓库明文。

**GoGo 代码导航**：`BookingAgent.java` → `skills/tuniu-cli/` → `BookingPersistenceHook.java` → `BookingReadTools` / `BookingWriteTools`。

### 阶段 3：统一入口与 knowledge 挂载

1. `/api/agent` + 薄意图 + Master 注册 `knowledge`（p1）；
2. 寒暄 / `chat` 由 Master 直接回复；
3. 子能力 `forwardEvents(false)`，事件不冒泡打乱前端。

### 阶段 4：体验与记忆（可选增强）

1. 读 `user_memory` 注入规划偏好；
2. 会话标题、推荐问题（旁路单次 LLM，不必 ReActAgent）。

---

## 五、GoGo 依赖真相（学习 / 本地跑通参考）

### 5.1 硬依赖（GoGo 本体）

| 依赖 | 说明 |
|---|---|
| MySQL | `gogo_travel` + `schema.sql` 预置账号 |
| Redis | Sa-Token、熔断、中断广播、ApiKey 缓存（**知域可用**，见 §2.3） |
| DashScope Key | 父 POM resource filtering 注入 |

### 5.2 软依赖

| 依赖 | 降级行为 |
|---|---|
| Weather / Orizn MCP | init 失败跳过；RAG / wttr.in 兜底 |
| 百炼长期记忆 | 占位符时 `record/retrieve` 静默 no-op |
| MinIO | 实时 SSE 不受影响；仅历史方案页回看失效 |

### 5.3 阻塞点与坑

| 项 | 说明 |
|---|---|
| 途牛 Key | 对话内 `save_tuniu_api_key` 落库加密 |
| rgh 酒店 CLI | 需 OAuth；多用户靠 Redis 隔离 |
| flight-manager Key 工具 | 代码注释与 SKILL.md 不一致 |
| 意图单意图直跳 | 已回滚，一律走 Master |

---

## 六、工程增强删减档案（回填手册）

> **仅含工程层**；§二「绝对不做」的业务项不在此表。用法：按症状查表，命中再加回。

### 6.1 三层意图 + 查询改写

- **作用**：L1 规则 → L2 向量 → L3 LLM；未命中才改写。
- **代码**：`agent/intent/*`、`QueryRewritingAgent.java`、`AgentPipelineService.java`
- **症状**：每轮固定多 1–2 次 LLM，首字延迟/成本成为痛点。
- **知域**：P4 用薄意图；P5 可先 L1 规则（`intent-seed` 思路），不必 L3 独立 Agent。

### 6.2 工具熔断 ToolCircuitBreakerHook

- **作用**：工具维熔断三态，失败阈值后快速失败。
- **代码**：`agent/hook/ToolCircuitBreakerHook.java`、`agent/circuitbreaker/`
- **症状**：外部 API 挂掉时 ReAct 反复重试，token 空烧。
- **知域**：进程内三态或 **Redis** 存状态均可（多实例时建议 Redis）。

### 6.3 多 Skill 兜底链

- **作用**：机票 tuniu → flight-manager → flyai；酒店多源归一化。
- **代码**：`resources/skills/`、`SKILL对比.md`
- **症状**：单供应商故障/无 Key 时搜索不可用。
- **知域**：P4 保留 flyai；多源 P5 按需。

### 6.4 Token 压缩 hooks

- **作用**：CLI 结果压缩 + Skill 正文折叠。
- **代码**：`CliResultCompressHook`、`SkillContentCollapseHook`
- **症状**：长规划会话超窗或成本飙升；过渡方案：截断最近 N 轮。

### 6.5 百炼长期记忆

- **作用**：`record_to_memory` / `retrieve_from_memory` 跨会话偏好。
- **知域替代**：`user_memory` 表 + 请求注入；**不接入百炼**。

### 6.6 MinIO 对象存储

- **作用**：大对象持久化，历史回看。
- **知域**：P4 **做**（软依赖）。**两类对象**：① 行程方案页 `plans/...`；② 知识报告 `task=report` → `reports/...`（与方案页 key 前缀分离）。

### 6.7 API Key 加密 SecretCipher

- **作用**：`user_api_key` AES 加密 + 缓存。
- **知域**：上线/多用户前必须做（Postgres + 应用层 AES）；解密缓存可用 Redis 或进程内；P4 可 `.env`。

### 6.8 敏感信息脱敏 SensitiveMasker

- **作用**：日志与前端脱敏。
- **症状**：合规与演示泄露风险。

### 6.9 Redis（缓存 / 熔断 / 中断广播）

- **作用**：熔断计数、ApiKey 解密缓存、写操作限流、多实例「停止生成」Pub/Sub。
- **知域**：**可用**；单机可进程内替代，水平扩展或多实例时建议启用。

### 6.10 TransmittableThreadLocal

- **作用**：Reactor/线程池下上下文传播。
- **症状**：异步场景用户身份错乱。

---

## 七、知域各阶段依赖核对

### 阶段 0（环境）

- [ ] Postgres + pgvector、Session、现有 p1 可用
- [ ] 机票 flyai trial 可走通
- [ ] MinIO 可选（方案页 + `task=report` 回看）
- [ ] Redis 可选（限流/熔断/多实例；无则进程内降级）
- [ ] 酒店供应商 Key 或占位降级

### 阶段 1（TRAVEL-PLAN-1）

- [ ] `/api/agent` 骨架 + 薄意图 + Master + plan 子能力
- [ ] SSE：`progress` / `travel_data` / `plan_html`
- [ ] `save_plan_html`（MinIO 软依赖）

### 阶段 2（TRAVEL-BOOK-1）

- [ ] `booking_agent` + HITL + `booking_record`
- [ ] `BookingPersistenceHook` 等价落库

### 阶段 3（knowledge 统一入口）

- [ ] p1 挂为 `knowledge`；`/api/chat` 行为不变

---

## 附录 A：GoGo 企业链路 B（知域不交付，仅代码学习）

GoGo 本地若需验证企业差旅单闭环：

1. `alice` 建单 → HITL 补全 → 冲突检测 → 提交审批；
2. `admin` 在 `AdminApprovalPage` 审批；
3. 查询/取消差旅单。

**代码路径**：`ItineraryManageAgent` → `TravelOrderWriteTools` → `TravelOrderConflictTools` → `ApprovalService` → `AdminApprovalController`。

此项**不得**作为知域 P4/P5 默认 backlog。

---

## 附录 B：与 README 的差异（以本文为准）

| README 描述 | 实测 / 知域 |
|---|---|
| 架构图 Plan 下挂 Booking | Booking 与 Plan **平级** |
| 架构图含 Review Agent 下级 | 线上为 **ReviewTools**，Review Agent 仅 Debug |
| 9 个 ReActAgent 均为主链路 | 仅 **4** 个为 Master 业务工具；2 个管道 + 1 stub + 1 未挂载 |
| 第一条链路 = 差旅单 B | 知域第一条 = **规划 C + 预订 D** |
| 阶段 5 报销 / 钉钉 | 知域 **绝对不做**（§二） |

---

## 附：文档索引

| 文档 | 用途 |
|---|---|
| [PRD-P4.md](PRD-P4.md) | 知域实施规格、验收、P5 回填表 |
| [README.md](README.md) | GoGo 已实现特性清单 |
| 本文 | 蓝本对照、绝对不做边界、工程删减手册 |
