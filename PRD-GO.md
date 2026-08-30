# GoGo Agent 需求梳理与渐进式走通路线

> 本文回答三个问题：**这个项目有哪些需求？先走通哪条链路、再慢慢加什么？将来知域 Agent 重建差旅助手时砍什么、留什么？**
>
> 与 [README.md](README.md) 的分工：README 记录"已经做了什么"（架构与特性清单）；本文是"按什么顺序走通"的路线图，外加一份**删减项回填手册**——被裁剪的工程增强项逐条建档，将来遇到对应症状时按图索骥加回来，也是重点学习清单。

---

## 一、项目定位与本次梳理结论

**GoGo 智能差旅助手**：基于多 Agent 协作（AgentScope 1.0.12 / ReAct 模式）的企业差旅助手，覆盖 差旅申请 → 审批 → 行程规划 → 预订 →（未完成的）报销 全生命周期。

本次梳理的三条结论：

1. **知域 Agent 已有知识库 RAG 基建** → 链路 A（政策/景点问答）对知域而言**只导语料、不重建检索**。gogo-agent 侧链路 A 已能跑通，仅作验证，不作为建设重点。
2. **第一条完整链路 = 链路 B 差旅单闭环**：业务主轴、零第三方 Key 依赖、内部审批已完整可用（钉钉不是必要条件）。
3. **为知域重建做的裁剪全部是工程增强层**，不删减任何业务功能；每个裁剪项在第 6 章有一张"回填卡"，记录缺失症状与加回方式。

---

## 二、需求全景

### 2.1 五条垂直链路

| 链路 | 覆盖需求 | 状态 | 硬依赖 | 关键代码入口 |
|---|---|---|---|---|
| **A 智能问答** | 差旅政策/景点/指南 RAG 问答、天气、签证 | ✅（验证即可） | 仅 DashScope Key | `agent/InfoAgent.java`、`config/RagKnowledgeConfig.java` |
| **B 差旅单闭环** | 申请 → 冲突检测 → 内部审批 → 查询/取消 | ✅ | 无 | `agent/ItineraryManageAgent.java`、`agent/tools/TravelOrderWriteTools.java` |
| **C 行程规划** | 机/酒/火搜索比价 → 方案优化 → 六维审核 → 方案页 | ✅ | 机票可零 Key（flyai trial）；酒店需 rgh 登录或途牛 Key | `agent/ItineraryPlanAgent.java`、`agent/tools/ItineraryPlannerTool.java` |
| **D 预订执行** | HITL 确认 → 下单/取消 → 落库 → 支付链接 | ✅ | 途牛 Key（对话内配置） | `agent/BookingAgent.java`、`agent/hook/BookingPersistenceHook.java` |
| **E 报销** | 发票识别 → 报销单生成 | ❌ stub（`build()` 返回 null） | — | `agent/ReimbursementAgent.java`、`agent/tools/ReimbursementTools.java` |

### 2.2 横切能力（服务所有链路）

| 能力 | 说明 | 代码入口 |
|---|---|---|
| 意图识别与路由 | 三层意图（L1 规则 / L2 向量 / L3 LLM）+ 查询改写 + MasterAgent 路由 | `agent/intent/*`、`agent/MasterAgent.java`、`agent/service/AgentPipelineService.java` |
| HITL 人机交互 | Agent 主动提问并暂停等待（text/select/form/confirm 等） | `agent/tools/UserInteractionTools.java` |
| SSE 流式推送 | 12 类事件：message/thinking/progress/travel_data/plan_html/user_interaction/booking_result/done 等 | `controller/ChatController.java`、`agent/service/ChatSseNotifier.java` |
| 会话体系 | 历史持久化、自动标题、推荐问题、会话续跑 | `business/chat/`、`agent/hook/SessionPersistenceHook.java` |
| 长期记忆 | 百炼 AGENT_CONTROL 模式，偏好记录与召回 | `agent/memory/*` |
| 政策规则引擎 | 职级 × 城市等级的预算/舱位精确校验 | `business/policy/`、`agent/tools/PolicyTools.java` |

> 第 6 章的删减项全部来自"横切能力"中的工程增强部分，五条链路的业务功能不在裁剪之列。

### 2.3 Agent 关系链路图（按代码实测绘制）

```
用户（浏览器）
  │  SSE / REST
  ▼
ChatController ──────────────────────────────────────────┐
  │                                                      │ 管理员审批走纯 Web 页面
  ▼                                                      ▼ （不经过任何 Agent/LLM）
AgentPipelineService（编排入口）                 AdminApprovalPage → AdminApprovalController
  │
  ├─ ① L1 规则意图 IntentRuleMatcher（<50ms）
  │      未命中 → ② L2 向量意图 IntentVectorMatcher（<100ms）
  │                未命中 → QueryRewritingAgent 改写 → 重走 L1/L2/L3
  │                          ③ L3 LLM 兜底 IntentRecognitionAgent
  ▼
MasterAgent（总路由，挂百炼长期记忆）
  │   通过 SubAgentProvider 把子 Agent 包装成 4 个「工具」
  │   （forwardEvents(false)，子 Agent 事件不冒泡）
  │
  ├── itinerary_manage_agent ──→ ItineraryManageAgent
  │        ├─ TravelOrderWriteTools      建单 / 提交审批 / 修改 / 取消
  │        ├─ TravelOrderReadTools       差旅单查询
  │        ├─ TravelOrderConflictTools   时间重叠+跨城衔接冲突检测
  │        ├─ PolicyTools                差旅政策规则引擎
  │        └─ UserInteractionTools       HITL 主动提问（暂停等用户）
  │
  ├── itinerary_plan_agent ────→ ItineraryPlanAgent（挂百炼长期记忆）
  │        ├─ ItineraryPlannerTool       plan_itinerary：4 类代表方案
  │        ├─ ItineraryReviewTools       六维审核（review/ 包：完整性/时间/
  │        │                             出发目的地/预算/路径/交通 评审器）
  │        ├─ PlanHtmlTools              方案页（SSE 实时推送，MinIO 可选）
  │        ├─ Skills：tuniu-cli / flyai / rolling-go-hotel / flight-manager
  │        └─ Weather MCP
  │
  ├── info_agent ──────────────→ InfoAgent
  │        ├─ RAG ×3                     政策 / 景点 / 指南知识库
  │        ├─ PolicyTools                精确身份绑定通道（双通道之一）
  │        ├─ DestinationLiveTools       wttr.in 天气（免 Key 兜底）
  │        └─ Weather MCP / Orizn 签证 MCP
  │
  └── booking_agent ───────────→ BookingAgent
           ├─ Skill：tuniu-cli           下单 / 取消
           ├─ BookingPersistenceHook     下单结果自动落库 booking_record
           ├─ BookingRead/WriteTools     预订查询 / 取消
           └─ UserInteractionTools       下单前 HITL 确认

旁路（单次 LLM 调用，不进多轮推理）：
  ConversationTitleService        会话标题（管道完成后异步）
  QuestionRecommendationService   推荐问题（MasterAgent 完成后）

横切 Hook（所有 ReActAgent 共享，BaseSubAgent 统一装配）：
  ProgressNotifierHook(SSE 推送) / SessionPersistenceHook(会话持久化)
  ToolCircuitBreakerHook(熔断) / CliResultCompressHook(token 压缩)
  SkillContentCollapseHook(技能正文折叠) / DynamicTimeInjectionHook(时间注入) ...

外部依赖：DashScope LLM / MySQL / Redis（硬）
         途牛等第三方 API（要 Key）
         MinIO、百炼记忆、Weather/Orizn MCP（软，缺失自动降级）
```

图的两点说明（重建/学习时重要）：

1. **子 Agent 之间的「关系」本质是工具调用关系，不是消息传递**。MasterAgent 把 4 个子 Agent 当成工具来调（`itinerary_manage_agent` 等就是工具名），全部在同一个 JVM 进程内，无跨进程通信。
2. **与 README 架构图的两处出入（以代码为准）**：①规划链路的六维审核实际走 `ItineraryReviewTools`（工具化评审器），`ItineraryReviewAgent` 这个 ReActAgent **未挂载主链路**，仅 `DebugAgentController` 调试入口在用；②`booking_agent` 与 `itinerary_plan_agent` 平级、直接挂在 MasterAgent 上，不是 Plan 的下级。

对知域重建的启示：必须复刻的骨架是「意图路由 → 业务子 Agent → 工具」主干 + HITL + SSE 推送；审核类能力直接以工具形态实现即可，不必做成独立 Agent。

---

## 三、依赖真相（已验证代码路径，决定走通顺序）

### 3.1 硬依赖（缺了起不来）

| 依赖 | 说明 |
|---|---|
| MySQL | 库 `gogo_travel`，建表+预置数据：`src/main/resources/db/schema.sql`。**无注册入口**，预置账号 `admin`(ADMIN)/`alice`/`bob`/`charlie`/`david`，密码均 `123456`（仅开发用） |
| Redis | `REDIS_HOST/REDIS_PORT/REDIS_PASSWORD` 环境变量；用于 Sa-Token 会话、中断广播、ApiKey 缓存、熔断状态 |
| DashScope Key | **Maven 构建期注入**：`application.yml` 中占位符 `@dashscope.api.key@` 由父 POM（`LLMentor/pom.xml`）resource filtering 解析。换环境改父 POM 或对应属性，改 yml 无效 |

### 3.2 软依赖（缺了自动降级，启动不受影响）

| 依赖 | 降级行为 |
|---|---|
| Weather MCP | init 失败返回 null bean，Agent 挂载时跳过；`query_weather`（wttr.in，免 Key）仍可兜底 ≤3 天天气预报 |
| Orizn 签证 MCP | 同上；签证问答回落到内部 RAG 知识库 |
| 百炼长期记忆 | factory 只校验 apiKey 非空（apiKey 来自父 POM，真实存在），library id 等仍是 `xxxxxxxx` 占位符 → 客户端带垃圾配置构造成功，运行期 `record/retrieve` **静默 no-op**（只有 WARN 日志）。容易误判"记忆功能坏了"，实际是没配 |
| MinIO | plan_html **实时 SSE 推送不受影响**（HTML 直接推前端渲染），仅历史会话回看方案页失效（`getPlanHtml` 404/500） |

### 3.3 真实阻塞点（需要动手动作）

1. **途牛 Key**：无 REST 接口、无前端页面，只能在**对话里粘贴**，由 `save_tuniu_api_key` 工具落库 `user_api_key`（`sk-` 前缀校验，AES 加密）。未配置时途牛 CLI 返回认证错误（exit 104/108），LLM 会看到错误并尝试其他数据源，不崩。
2. **酒店 rolling-go-hotel**：需本机安装 rgh CLI 并完成浏览器 OAuth 登录（多用户登录态由 `RghUserIsolationHook` + Redis TokenStore 隔离）。

### 3.4 已知坑（学习时留意）

| 坑 | 位置 | 后果 |
|---|---|---|
| flight-manager 的 `check/save_flight_api_key` 工具在代码中被注释，但 SKILL.md 仍指导 LLM 调用 | `agent/tools/ApiKeyTools.java`（注释块）、`resources/skills/flight-manager/SKILL.md` | LLM 会调到不存在的工具；该 Skill 实际无 Key 配置入口 |
| 钉钉回调 Controller 无鉴权（仅标记 todo 待完善） | `controller/ApprovalCallbackController.java` | **切勿暴露公网**；内部审批完全不依赖它 |
| 意图"单意图直跳"已回滚 | `AgentPipelineService`（@Deprecated） | 调度一律走 MasterAgent，README 3.9 的直跳描述已过时 |
| 用户无注册功能 | `db/schema.sql` 预置 | 加用户只能改 SQL |

---

## 四、渐进式走通路线图（起点 = 链路 B）

> 每阶段给出"走通标准"——可照着操作验收的场景脚本。依赖核对见第 7 章。

### 阶段 1：链路 B 差旅单闭环（第一条完整链路，零第三方 Key）

**前置**：MySQL/Redis/后端/前端就绪，DashScope Key 可用。

**走通标准**：
1. `alice / 123456` 登录，输入"下周二到周四去上海出差"→ ItineraryManageAgent 通过 HITL 卡片补全缺失信息 → 冲突检测通过 → 创建差旅单并提交审批；
2. 换 `admin / 123456` 登录，在 AdminApprovalPage 看到待审单，点同意；
3. 回到 alice 会话，"查一下我的差旅单" → 状态为已通过；再建一张测试差旅单走取消流程；
4. 全程 SSE 进度面板、时间轴消息、会话历史、推荐问题均正常。

**代码导航**：`agent/ItineraryManageAgent.java` → `agent/tools/TravelOrderWriteTools.java`（建单/提交）→ `agent/tools/TravelOrderConflictTools.java`（冲突）→ `business/approval/service/ApprovalService.java`（落审批记录）→ `controller/AdminApprovalController.java`（审批决策）→ `business/order/TravelOrderService.java` 的 `decideAndSyncOrder`（状态同步）。

### 阶段 2：链路 C 行程规划（机票半边可零 Key 走通）

**前置**：阶段 1 通过；可选安装 rgh CLI（酒店搜索）。

**走通标准**：
1. 输入"帮我规划下周二去上海、周四返回的行程，经济舱"→ 路由到 ItineraryPlanAgent；
2. 途牛无 Key 报认证错误后，自动落到 **flyai（免 Key trial 模式）**→ 前端出现机票 `travel_data` 卡片；
3. `plan_itinerary` 输出去×住×返 4 类代表方案对比 → ItineraryReviewAgent 给出六维审核意见（完整性/时间/出发目的地/预算/偏好/路径）；
4. 方案页通过 `plan_html` 事件**实时渲染**（此时可不配 MinIO）；
5. 故意制造搜索全挂（如断网），确认熔断/降级话术生效、对话不崩。

**代码导航**：`agent/ItineraryPlanAgent.java` → `resources/skills/flyai/`（免 Key 备源）→ `agent/tools/ItineraryPlannerTool.java`（`plan_itinerary`）→ `agent/ItineraryReviewAgent.java` + `resources/prompts/review/` → `agent/tools/PlanHtmlTools.java`。

### 阶段 3：链路 D 预订闭环

**前置**：在对话中粘贴途牛 Key（先 `check_tuniu_api_key` 确认未配置，再发 Key 由 `save_tuniu_api_key` 保存）。获取入口：https://open.tuniu.com/mcp/login 。

**走通标准**：
1. 确认某个方案后 BookingAgent 执行下单 → 前端 `BookingResultCard` 展示下单结果与支付链接；
2. `booking_record` 表出现对应记录（`BookingPersistenceHook` 对 LLM 透明落库）；
3. "查一下我的预订" → `query_booking_record` 按 userId 租户隔离返回；
4. 取消一张测试预订 → 状态同步成功。

**代码导航**：`agent/BookingAgent.java` → `resources/skills/tuniu-cli/` → `agent/hook/BookingPersistenceHook.java` → `agent/tools/BookingReadTools.java` / `BookingWriteTools.java`。

### 阶段 4：记忆与体验

**前置**：`application.yml` 中百炼 `memory-library-id/ak/sk/workspace/index` 换成真实值。

**走通标准**：
1. 对 Agent 说"我出差喜欢靠窗、高楼层"→ 触发 `record_to_memory`；
2. **新开会话**发起规划 → Agent 主动 `retrieve_from_memory` 召回偏好并体现在方案/审核意见中；
3. 会话标题自动生成、推荐问题按场景出现（澄清题不硬塞"确定"）。

**代码导航**：`agent/memory/TravelPreferenceLongTermMemory*.java`、`agent/config/TravelAgentConfig.java`、`business/chat/service/ConversationTitleService.java`、`agent/service/QuestionRecommendationService.java`。

### 阶段 5：补缺与远期（延后项，非删减）

按优先级：
1. **报销本地版**：发票手工录入/上传 → 报销单生成 → 落库（`ReimbursementTools` + `resources/skills/reimbursement/` 已有素材，缺的是把 `ReimbursementAgent.build()` 的 null 补成真 Agent）；A2A 发票识别后置；
2. **钉钉审批**：outbound 提交 + 回调签名校验（当前回调无鉴权）；
3. **修 flight-manager key 工具**：把 `ApiKeyTools.java` 中被注释的 `check/save_flight_api_key` 恢复并与 SKILL.md 对齐；
4. AgentScope-Java 2.0 重构、可观测性（README todo 2/3）。

---

## 五、知域 Agent 重建蓝本

定位：知域中的"AI 客服差旅功能"。以 gogo-agent 业务需求为蓝本重建，**不是**服务化集成。

### 5.1 不用做

- **RAG 检索基建**：知域已有，只需导入三份语料（`src/main/resources/dataset/` 下 `business_travel_policy.docx` 差旅政策、`business_travel_guidelines.docx` 差旅指南、`tourist_attraction.xlsx` 景点），按知域自身解析管线适配格式。

### 5.2 重建顺序（对齐第 4 章阶段）

1. **第一步 = 链路 B 的业务本质**：差旅单 CRUD + 冲突检测（时间重叠 + 跨城衔接）+ 审批状态机 + 意图路由（**单次 LLM 结构化输出**即可，不需要三层短路）；
2. **第二步 = 链路 C/D 本质**：搜索比价 → 方案对比 → HITL 确认 → 预订 → 订单落库；**建议保留 flyai 这类免 Key 备源**，成本低、保住供应商故障时的可用性。

### 5.3 必须保留（业务体验底座）

SSE 流式 + 进度/结果卡片（用户对 Agent 的信任来自"看得见它在干嘛"）、会话历史、HITL 交互卡。

### 5.4 砍掉但要有补偿

| 裁剪项 | 补偿方案 |
|---|---|
| token 压缩 hooks | 简单轮数截断 + 只保留最近 N 轮工具结果 |
| MinIO 方案页 | 前端直接渲染 JSON/Markdown 方案，去掉对象存储后反而无损 |

其余工程增强的完整取舍见第 6 章。

### 5.5 用户与审批架构（已定：方案 A——账号即企业账号）

**决策**：知域面向单一企业内部使用，用户账号即企业员工身份（预置员工账号，或对接企业用户目录/SSO），**不做**「独立注册 + 企业绑定」的 SaaS 模式（方案 B，仅作备忘）。判断依据：账号系统可以独立，但「这个用户是哪家企业的什么员工」这一身份声明必须来自企业侧——方案 A 通过让账号本身就是企业身份来满足，省去绑定流程与 SaaS 化成本。

由此确定六点：

1. **申请人身份可信**：不需要企业码/绑定流程。gogo-agent 的账号模式（`user_account` + `user_profile` 预置员工）直接平移；
2. **审批人**：同一系统内的 ADMIN 角色登录知域，在审批页操作（AdminApprovalPage 模式平移）。「对话内审批」作为可选增强：admin-only 工具 + HITL 二次确认 + 后端 `isAdmin()` 强校验——审批决策必须由人发起，LLM 只当执行器，不能靠提示词约束；
3. **审批留痕必须补**：gogo-agent 的 `approval_record` 表只有申请人（`user_id`）、状态、备注、时间，**没有「审批人是谁」字段**。重建时加 `approver_id` + 审批时间，这是合规与报销凭证的依据；
4. **审批态一致性**：沿用 gogo-agent 的处理——修改差旅单时自动撤销旧审批单并重新发起审批；取消已审批单要求二次确认（force）；
5. **审批人触达（后续可选）**：起步靠管理员登录知域；之后可做钉钉/企微消息推送 + 带签名校验的回调，把审批送到管理员已有的工具里（gogo-agent 的 `ApprovalCallbackController` 是无鉴权的 inbound 半截，重建时需补 outbound 提交侧 + 签名校验）；
6. **表结构预留**：即便方案 A 假设单企业，仍建议在用户/差旅单/审批单表预留 `company_id` 字段——成本为零，将来若转多企业（方案 B）不用动表。

---

## 六、删减项档案（回填手册）

> 每项一张卡：**作用 → 代码位置 → 缺失症状（= 何时需要加回）→ 加回方式与成本 → 学习要点**。
> 使用方法：遇到问题先来本章按症状查表，命中再决定是否加回；未命中症状说明暂时不需要。

### 6.1 三层意图识别 + 查询改写

- **作用**：L1 关键词规则（<50ms）→ L2 向量相似（<100ms）→ L3 LLM 兜底，命中即短路；仅 L1/L2 未命中才触发查询改写，省 1-2 次 LLM 调用。
- **代码位置**：`agent/intent/IntentRuleMatcher.java`、`IntentVectorMatcher.java`、`IntentRecognitionRouter.java`、`agent/QueryRewritingAgent.java`、`resources/intent-seed.yml`（L2 种子语料）、`agent/service/AgentPipelineService.java`（条件触发编排）。
- **缺失症状**：每轮对话固定多 1-2 次 LLM 调用，首字延迟与成本成为痛点时，就是加回的信号。
- **加回方式与成本**：中。先加 L1 规则层（纯代码、无依赖），再按积累的真实问法补 `intent-seed.yml`，最后视情况上 L2 向量层。
- **学习要点**：分层短路设计；种子语料与规则层的去重校验（`IntentRouterSeedExamplesTest`）；改写从"必经"改"条件触发"的编排思路。

### 6.2 工具熔断 ToolCircuitBreakerHook

- **作用**：工具维度熔断三态（关闭/打开/半开），失败达阈值后快速失败并指数退避，支持显式关闭工具组。
- **代码位置**：`agent/hook/ToolCircuitBreakerHook.java`、`agent/circuitbreaker/`（Redis 状态存储）。
- **缺失症状**：外部 API 挂掉时，Agent 每轮 ReAct 循环仍反复重试该工具——响应变慢、token 空烧、用户看到连环报错。
- **加回方式与成本**：低-中。逻辑自包含（Hook + Redis 计数），可直接参考现成实现平移。
- **学习要点**：熔断三态状态机、半开探测、指数退避；Hook 拦截工具调用的切入点。

### 6.3 多 Skill 兜底链

- **作用**：同一能力挂多个供应商，主源失败自动切换（机票：tuniu → flight-manager → flyai；酒店：rolling-go-hotel 等），多源结果格式归一化后统一展示。
- **代码位置**：`resources/skills/`（5 个 skill）、`src/SKILL对比.md`（各供应商配额与兜底顺序）、前端 `TravelResultCard.tsx`（多数据源归一化展示）。
- **缺失症状**：只接一个供应商后，对方故障/配额耗尽/无 Key 时该类搜索直接不可用。
- **加回方式与成本**：低（保留 flyai 免 Key 备源几乎零成本）到高（多接一家供应商）。
- **学习要点**：Skill 化的外部能力封装、供应商对比维度（配额/稳定性/覆盖面）、结果归一化。

### 6.4 token 压缩 hooks（CliResultCompressHook + SkillContentCollapseHook）

- **作用**：MCP/CLI 结果去重压缩 + 历史技能正文折叠为占位符，显著压降多轮 reasoning 的输入 token。
- **代码位置**：`agent/hook/CliResultCompressHook.java`、`agent/hook/SkillContentCollapseHook.java`。
- **缺失症状**：长会话/复杂规划中上下文持续膨胀——成本上升，重则超模型窗口报错。过渡替代：轮数截断 + 只保留最近 N 轮工具结果。
- **加回方式与成本**：中。依赖宿主框架的 Hook 机制与消息结构访问能力。
- **学习要点**：上下文工程——结构化字段裁剪、黑名单字段、正文折叠时机；`DynamicTimeInjectionHook` 配合百炼隐式缓存的前缀稳定技巧（同类思路）。

### 6.5 百炼长期记忆

- **作用**：AGENT_CONTROL 模式自动注册 `record_to_memory` / `retrieve_from_memory`，Agent 自主决定记什么、何时召回（跨会话差旅偏好）。
- **代码位置**：`agent/memory/TravelPreferenceLongTermMemoryFactory.java`、`TravelPreferenceLongTermMemory.java`、`agent/config/TravelAgentConfig.java`、`application.yml`（memory 配置段）。
- **当前替代**：知域重建用一张 `user_preference` 表 + 请求注入，功能等价且无外部依赖。
- **缺失症状**：想要"Agent 自主管理记忆"（而非固定字段注入）的智能化效果时加回。
- **加回方式与成本**：低（SDK 化），但需开通百炼记忆库并配真实 id。
- **学习要点**：AGENT_CONTROL vs 系统注入两种记忆模式；请求级召回缓存；静默降级设计（factory 只校验 apiKey）。

### 6.6 MinIO 方案页存储

- **作用**：行程方案 HTML 持久化到对象存储，历史会话可回看方案页。
- **代码位置**：`agent/tools/PlanHtmlTools.java`（上传）、`controller/MyTravelController.java`（回读）、`config/MinioConfig.java`。
- **缺失症状**：实时展示不受影响；历史会话点开方案页 404/500。替代：前端直接渲染方案数据（JSON/Markdown），彻底去对象存储。
- **加回方式与成本**：低。docker 起 MinIO + 4 个环境变量即可；或用替代方案则永久免除。
- **学习要点**：软依赖设计（init 全 catch、失败仍推 SSE 实时事件）；大 HTML 的存取与 iframe 渲染。

### 6.7 API Key 加密 SecretCipher

- **作用**：`user_api_key` 表中第三方凭证 AES-128 加密存储 + Redis 缓存。
- **代码位置**：`apikey/`（`SecretCipher`、`ApiKeyService`）、配置 `app.api-key-encrypt-secret`（有默认值）。
- **缺失症状**：开发期无感知；**上线/多人使用前必须加回**——明文存用户第三方凭证不可接受。
- **加回方式与成本**：低。现成实现，注意密钥的配置管理（不要进 git）。
- **学习要点**：对称加密存用户凭证、密钥轮换、缓存与 DB 回退策略。

### 6.8 全链路敏感信息脱敏 SensitiveMasker

- **作用**：日志（logback converter）与前端输出中手机号/身份证/银行卡/邮箱/API Key 自动脱敏。
- **代码位置**：`config/sensitive/`、`src/test/java/.../SensitiveMaskerTest.java`（410 行，现成学习样本）。
- **缺失症状**：功能无感知；合规与演示泄露风险（日志/界面露出真实手机号等）。
- **加回方式与成本**：低。上线或公开演示前启用即可。
- **学习要点**：logback 自定义 converter 做日志脱敏的模式；脱敏规则的测试写法。

### 6.9 Redis 集群中断广播

- **作用**：多实例部署时，"停止生成"通过 Redis Pub/Sub 广播，任意节点都能中断目标 Agent 的 ReAct 循环。
- **代码位置**：中断广播相关见 `agent/session/`、`agent/registry/`（`AgentExecutionRegistryHook` 消费）。
- **缺失症状**：单机部署无感知；多实例时"停止"按钮只能停掉本实例收到的会话。
- **加回方式与成本**：低-中。仅在水平扩容时需要。
- **学习要点**：跨节点事件广播、优雅中断在 ReAct 循环内的检查点设计。

### 6.10 TransmittableThreadLocal 上下文传播

- **作用**：Reactor 线程切换/线程池跳转时，用户身份等上下文不丢失（SSE + 异步编排场景）。
- **代码位置**：依赖 `com.alibaba:transmittable-thread-local`，使用处散布在上下文持有工具类（如 `AgentSessionContextHolder`）。
- **缺失症状**：换成自定义线程池/新框架后出现用户身份错乱、上下文丢失类 bug。
- **加回方式与成本**：低。引入依赖 + 包装线程池。
- **学习要点**：ThreadLocal 在响应式/线程池场景的坑与 TTL 的装修模式。

### 6.11 延后而非删减（业务功能，按阶段 5 推进）

| 项 | 现状 | 去向 |
|---|---|---|
| 钉钉审批 | 回调 inbound 存在但无鉴权、无 outbound | 阶段 5-2：补提交侧 + 签名校验 |
| 报销 | `ReimbursementAgent.build()` 返回 null | 阶段 5-1：先本地版（手工录入→报销单），A2A 发票识别后置 |
| flight-manager Key 配置 | 工具被注释，SKILL.md 失配 | 阶段 5-3：恢复工具 |
| AgentScope 2.0 重构 / 可观测性 | README todo | 更远期 |

---

## 七、各阶段依赖核对清单

### 阶段 0（环境基座，一次性）
- [ ] MySQL：建库 `gogo_travel`，执行 `src/main/resources/db/schema.sql`（含预置账号 admin/alice/...，密码 123456）
- [ ] Redis：`REDIS_HOST/REDIS_PORT/REDIS_PASSWORD`
- [ ] DashScope Key：配置在**父 POM**（`LLMentor/pom.xml`）的属性，经 resource filtering 注入——改 `application.yml` 无效
- [ ] 后端 8080 启动；前端默认 `http://localhost:8080`，零配置（跨域已 `@CrossOrigin`）

### 阶段 1（链路 B）
- [ ] 以上基座即可，无新增依赖

### 阶段 2（链路 C）
- [ ] 可选：rgh CLI 安装 + 浏览器 OAuth 登录（酒店搜索）
- [ ] 可选：MinIO（仅历史回看需要；实时展示不需要）
- [ ] 可选：`WEATHER_MCP_ENDPOINT`、`ORIZN_MCP_*`（均有降级，不配不影响走通）
- [ ] 机票搜索预期行为：途牛无 Key 报认证错误 → 自动落 flyai（免 Key）

### 阶段 3（链路 D）
- [ ] 对话内粘贴途牛 Key（`save_tuniu_api_key`，sk- 前缀；申请入口 https://open.tuniu.com/mcp/login ）
- [ ] `booking_record` 表已随 schema.sql 建好

### 阶段 4（记忆与体验）
- [ ] 百炼：开通记忆库，替换 `application.yml` 中 `memory-library-id / ak / sk / workspace / index` 占位符（注意：未替换前是**静默 no-op**，只有 WARN 日志，属正常现象而非故障）

### 阶段 5（补缺）
- [ ] 报销本地版：无新增外部依赖
- [ ] 钉钉：企业应用凭证 + 回调签名密钥（务必给回调加鉴权）
- [ ] flight-manager：修 `ApiKeyTools` 注释块并核对 SKILL.md

---

## 附：与 README 第七章 todo 的对应

| README todo | 本文去向 |
|---|---|
| 1、A2A 接入发票识别、自动报销 | 阶段 5-1（先本地版，A2A 后置） |
| 2、AgentScope-Java 2.0 重构 | 阶段 5-4（更远期） |
| 3、可观测性 | 阶段 5-4（更远期） |
