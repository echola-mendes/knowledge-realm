# 当前子需求

## 1. 目标

基于 `docs/multi-agent/PRD-P4.md`，在知域现有 Agent 能力之上落地**个人出行多 Agent**：统一入口 `/api/agent`（与 `task=agent|report` 同一入口）→ 薄意图 → Master（Supervisor）→ 三个子能力（`knowledge` / `plan` / `booking`），完成行程规划、定制方案、搜订机酒（本人 HITL 确认）。

## 2. 背景

- **现有**：`/api/agent` / `/api/agent/stream` 已存在，但直接调用 `app/graph.py` 单图（知识检索 + report），无薄意图、无 Master、无差旅子 Agent。
- **现有**：`app/graph.py` 含 `reason → run_tool → generate` 循环；`user_memory` LTM 可注入；`ChatView.vue` 支持 chat/agent/report 三模式。
- **缺失**：Supervisor 骨架、意图分类、机酒搜索 Tool、方案页 SSE/MinIO、`booking_record`、HITL `pending_action`、供应商集成（flyai 等）。
- **蓝本**：`docs/multi-agent/PRD-GO.md` 仅作对照；知域按 P4 重建，不是集成 gogo Java 服务。

## 3. 功能范围

### 3.1 入口骨架（P4 Step 1）

1. `/api/agent`（及 stream）改为：**薄意图节点 → MasterAgent → 子能力**；与 `task=agent|report` **同一入口**，禁止并行第二条 travel API。
2. 薄意图：一次结构化分类 → `knowledge | plan | booking | chat`；与 Master 职责分离。
3. Master：Supervisor + Agents-as-Tools；将现有 `app/graph.py` 挂为 **`knowledge` 子能力**（非第二入口）。
4. `chat` 寒暄由 Master 直接回复；`task=report` 仍走 knowledge，报告完成后写 MinIO（`reports/{conversation_id}/...`）。

### 3.2 行程规划 TRAVEL-PLAN-1（P4 Step 2）

1. `itinerary_plan_agent`：Tool 含 `search_flights` / `search_hotels` / `plan_itinerary` / `save_plan_html`。
2. 对话补问缺失要素；口头偏好可改方案且不丢日期/城市；可读 `user_memory`。
3. **机票方案卡片契约**：SSE `travel_data` 中 flights 段以 **flyai `search-flight` 的 `itemList` 原结构** 为前端契约，对齐现网 `TravelResultCard`（Step 2 新建组件）。
4. **方案页契约**：`plan_html` / `plan_itinerary` 输出含 **推荐 / 对比 / 总价**，不直接绑 flyai 字段。
5. **酒店卡片**：独立契约；无供应商时占位提示，**不伪造房型**。
6. `save_plan_html`：SSE 推送 `progress` / `travel_data` / `plan_html`；MinIO 落 `plans/{conversation_id}/...`（本机已有 MinIO）。
7. 机票 flyai trial；酒店 Key 未配则降级提示。

### 3.3 搜订机酒 TRAVEL-BOOK-1（P4 Step 3）

1. `booking_agent`：Tool 含 `book_flight` / `book_hotel` / `list_bookings` / `cancel_booking`。
2. **HITL**：`pending_action`；未确认拦截写操作；`ChatView` 确认卡片（`style.md`）。
3. 确认后写 `booking_record`；透出支付链接（若有）。
4. 写操作限流 **30/min**（本步实施）。
5. Hook：预订落库。

## 4. 非目标

- 企业差旅单、内部审批、钉钉/企微、报销、职级×城市政策引擎
- 独立 `info_agent` / `itinerary_manage_agent`
- 三层意图 L1/L2/L3、百炼记忆、Celery、火车票
- 改 `/api/chat` 为 LangGraph；并行第二条 travel REST API
- 新建 `server/app/p4/` 目录（**已否决**；p1 包已于 2026-08-31 上移，代码平铺 `server/app/`）
- 熔断/Token 压缩等 Hook（P5）

## 5. 业务规则

| 规则 | 说明 |
|---|---|
| 身份 | 只来自 Session；禁止请求参数 `user_id` |
| 入口 | Agent 模式只走 `/api/agent`；差旅与 `task=agent` 同一入口 |
| 代码组织 | 扩展现有 `server/app/`（intent / master / plan / booking / travel） |
| 意图 ≠ Master | 意图只出标签；Master 只调度 + 整合 |
| 写操作 | 搜索/出方案只读；下单/取消须本人 HITL |
| Key | 供应商 Key 仅 `.env` |
| MinIO | 本机已部署；连接失败时 SSE 仍可用并提示 |

## 6. 输入与输出

**输入：** 用户自然语言（Session）；`knowledge_base_id`、`conversation_id`、`task`（agent/report）、`allow_web`。

**输出：**

- knowledge：answer + citations；report 另写 MinIO `reports/...`
- plan：机票 `itemList` 卡片 + `plan_itinerary` 方案页 + MinIO `plans/...`
- booking：HITL 卡片 → 预订结果 + `booking_record`

## 7. 涉及模块

| 层级 | 模块 |
|---|---|
| 入口 | `server/app/routers/master.py` — 仍挂 `/api/agent`、`/api/agent/stream` |
| 编排 | `server/app/intent.py`、`master.py`、`plan_agent.py`、`booking_agent.py` |
| 知识 | `server/app/graph.py` — 包装为 knowledge 子图 |
| 供应商 | `server/app/travel/flyai.py`；酒店占位 |
| 对象存储 | `server/app/travel/minio_store.py` + `config.py` MinIO env |
| 数据 | `models.py`：`booking_record`（Step 3）；Alembic |
| 前端 | `ChatView.vue`、`TravelResultCard.vue`（新建）、plan 方案页渲染、HITL 卡片 |
| 文档 | `docs/TECH.md` — Agent 架构变更同步 |

## 8. 验收标准

### Step 1 入口骨架
- [ ] 知识问答复用 `/api/agent` → `knowledge` → app/graph.py 图
- [ ] 「你好」→ `chat` → Master 直接回复
- [ ] `/api/chat` 未改 LangGraph；无第二条 travel API

### Step 2 TRAVEL-PLAN-1
- [ ] 规划话术 → `plan` → 机票卡片（itemList 契约）
- [ ] 改偏好不丢日期/城市；方案页含推荐/对比/总价
- [ ] SSE + MinIO 方案页可回看；酒店未配占位不伪造

### Step 3 TRAVEL-BOOK-1
- [ ] HITL 确认后下单；未确认无 `booking_record`
- [ ] 仅本人可查/取消；跨用户 404
- [ ] 写操作 30/min 限流生效

## 9. 已确认（提出人 2026-08-31）

1. ✅ 三步实施，每步确认后再进下一步
2. ✅ 阶段一：机票 flyai + 酒店占位/单源待定
3. ✅ 本机已有 MinIO（配置 env，失败降级提示）
4. ✅ 机票卡片 = flyai `search-flight.itemList`；方案页 = `plan_itinerary` 推荐/对比/总价；酒店卡片另定
5. ✅ 写限流 30/min 放在 Step 3
6. ✅ **否** 新建 `p4/`；差旅与 `task=agent` 同一 `/api/agent` 入口，代码平铺 `server/app/`（原 p1 包已上移）
