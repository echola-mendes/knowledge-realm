# Execution Plan

> 栈约束：FastAPI + LangGraph + Postgres/pgvector + DashScope；无 Celery；身份 Session；代码扩 `server/app/p1/`（禁止 `p4/`）。

## Step 1：Master 入口骨架（薄意图 + knowledge 挂载）

### 目标

将 `/api/agent` 从「直连 p1 单图」改为「薄意图 → Master → 子能力」；本步只挂通 `knowledge` 与 `chat`，plan/booking 留 stub 返回「尚未开放」。

### 方案

**后端**

1. **`server/app/p1/intent.py`**
   - `classify_intent(query, *, task, history_tail) -> Literal["knowledge","plan","booking","chat"]`
   - 一次 LLM 结构化 JSON；`task=report` 强制 `knowledge`
   - 规划/预订关键词启发式可辅助，但以 LLM 标签为准

2. **`server/app/p1/master.py`**
   - `MasterState`：`messages`、`intent`、`task`、`knowledge_base_id`、`conversation_id`、`allow_web`、`answer`、`citations`、`usage`…
   - 节点：`node_intent` → `node_dispatch` →（`node_chat` | `node_knowledge` | `node_stub_plan` | `node_stub_booking`）→ `node_finalize`
   - `node_knowledge`：调用现有 `build_graph().invoke(initial_state(...))`，复用 checkpoint `thread_id=conversation_id`
   - stub 节点：固定文案，不调用供应商
   - `build_master_graph()` compile + 现有 Postgres checkpointer

3. **`server/app/routers/p1.py`**
   - `_agent_out` / `agent_stream` 改调 `build_master_graph()`
   - stream：先发 `{type:"intent", intent}`；knowledge 路径 token 流式仍从 final answer 字符推送（本步可保持现行为）；终态 `citations` 事件保留
   - `/api/agent/trace` 可后续对齐 Master（本步不阻塞，可暂保留旧图或标注 deprecated）

4. **schemas**（如需）：`AgentOut` 增加可选 `intent: str`

**测试**

- `server/tests/test_master_intent.py`：mock LLM，覆盖 knowledge / chat 路由；report 强制 knowledge
- 回归：`test_search_graph.py` 等 p1 单测不受影响

**文档**

- `artifacts/architecture.md` 已写入；Step 1 完成后在 `docs/TECH.md` 增「P4 Master 入口」小节

### 验收

- [ ] 单测：「知识库…」mock 为 `knowledge`，Master 调用 p1 图（断言 invoke 被调）
- [ ] 单测：「你好」mock 为 `chat`，不调用 p1 图
- [ ] 单测：`task=report` 强制 `knowledge`
- [ ] 契约：`POST /api/agent` 知识问答仍返回 answer + citations；`/api/chat` 未改
- [ ] 路径：plan/booking 意图命中 stub，不 500

---

## Step 2：TRAVEL-PLAN-1（flyai + plan Agent + SSE + MinIO + 前端卡片）

### 目标

落地 `itinerary_plan_agent` 与 travel tools；机票搜索走 flyai；方案页与卡片契约分离；MinIO 持久化方案页。

### 方案

**配置**

- `config.py` / `.env`：`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`（本机已有实例）
- `FLYAI_*`（或项目既有 flyai env 名，实施时对齐 flyai 文档）
- 酒店：可选 `HOTEL_*`；未配时 `search_hotels` 返回 `{kind:"placeholder", message:"…"}`

**供应商**

- `server/app/p1/travel/flyai.py`：`search_flights(**params) -> dict` 原样返回含 `itemList` 的结构（失败抛明确异常）
- `server/app/p1/travel/minio_store.py`：`put_plan_html(conversation_id, html) -> url`；`put_report_html(...)` 供 report 路径

**Tools & Agent**

- `server/app/p1/travel/tools.py`（或扩 `plan_agent.py` 内）：
  - `search_flights` — 调 flyai，SSE 侧推送 `travel_data.flights = itemList`
  - `search_hotels` — 占位或单源
  - `plan_itinerary` — 输入搜索结果 + 用户约束，输出：
    ```json
    {
      "options": [{"id","label","segments","total_price","notes"}],
      "comparison": [{"dimension","rows":[{"option_id","value"}]}],
      "recommendation": {"option_id","reason"},
      "total_price_summary": "..."
    }
    ```
  - `save_plan_html` — 由 plan 结构渲染 HTML → MinIO `plans/...` + SSE `plan_html`
- `server/app/p1/plan_agent.py`：ReAct 子 Agent；注册上述 tools；Master `node_plan` 替换 stub
- plan Agent 可读 `load_ltm_hits`；缺失日期/城市时对话补问（tool 返回 `need_fields` 由 Agent 继续问）

**SSE Hook**

- `agent_stream` 在 Master/plan 执行中转发：`progress`、`travel_data`、`plan_html`
- 终态 `citations` 可携带 `travel_summary` / `plan_minio_url`

**knowledge report → MinIO**（同一步顺带）

- `node_knowledge` 在 `task=report` 完成后调用 `put_report_html`

**前端**

- `web/src/types/travel.ts`：`FlyaiFlightItem` 对齐 flyai `itemList[]` 字段（实施时对照 flyai 响应定稿）
- `web/src/components/TravelResultCard.vue`：渲染 itemList 单项；样式 `style.md`
- `web/src/components/HotelPlaceholderCard.vue`（或内联）：占位提示
- `web/src/components/PlanItineraryPanel.vue`：渲染 recommendation / comparison / total_price
- `ChatView.vue`：解析 SSE 新事件；agent 模式展示卡片 + 方案页 iframe/内嵌 HTML

**测试**

- `test_flyai_client.py`：mock httpx，断言 parse itemList
- `test_plan_itinerary.py`：mock LLM，输出 schema 合法
- `test_minio_store.py`：mock minio client，key 前缀 `plans/`

### 验收

- [ ] 单测：flyai mock 返回 itemList，tool 原样透出
- [ ] 单测：`plan_itinerary` 输出含 recommendation / comparison / total_price
- [ ] 单测：`save_plan_html` key 为 `plans/{conversation_id}/...`
- [ ] 路径：「下周二上海往返经济舱」→ plan → 前端展示 TravelResultCard（itemList）
- [ ] 路径：方案页展示推荐/对比/总价（非 flyai  raw 字段）
- [ ] 路径：酒店未配 → 占位卡片，无伪造房型
- [ ] 路径：MinIO 可用时方案页可回看 URL；不可用时 SSE 仍成功且提示

---

## Step 3：TRAVEL-BOOK-1（HITL + booking_record + 限流）

### 目标

落地 `booking_agent`；写操作 HITL；预订落库；本人查询/取消；写限流 30/min。

### 方案

**数据**

- Alembic：`booking_record` 表
  - `id, user_id, kind(flight|hotel), vendor, external_id, payload(JSON), status, pay_url, created_at, updated_at`
- `MasterState` / session 级 `pending_action`：`{tool, args, summary, confirmed: bool|null}`

**Agent & Tools**

- `server/app/p1/booking_agent.py`：
  - `book_flight` / `book_hotel` — 执行前检查 HITL；未确认返回 `pending_action` 描述
  - `list_bookings` — `WHERE user_id = session_user`
  - `cancel_booking` — HITL 后调供应商 + 更新 status
- `server/app/p1/travel/flyai.py` 扩展 book/cancel（或 stub 支付链接）
- Master `node_booking` 替换 stub；写工具 Hook 落库 `booking_record`

**HITL 流程**

1. booking Agent 生成 `pending_action` → SSE `{type:"hitl", ...}`
2. 前端展示确认/拒绝卡片
3. 新请求或同会话续聊带 `hitl_confirm: true|false`（schema 扩展 `AgentRequest`）→ Master 注入 confirmed 后继续

**限流**

- `server/app/p1/travel/rate_limit.py`：进程内 sliding window，用户维度 30 write/min（book/cancel）；超限 429

**前端**

- `ChatView.vue`：HITL 卡片；确认后重发或专用 confirm API（择一，实施时最小改动）
- 「我的预订」：对话内 list_bookings 结果卡片

**测试**

- 未确认 book 无 DB 行
- 确认后 book 有行且 user_id 正确
- 用户 A 不可查用户 B 订单
- 限流第 31 次写操作 429

### 验收

- [ ] 单测：未 HITL 确认时 `book_*` 不写库
- [ ] 单测：确认后 `booking_record` 落库且 `user_id` 为 Session 用户
- [ ] 单测：跨用户 `list_bookings` / cancel 404 或空
- [ ] 单测：30/min 限流触发 429
- [ ] 路径：对话「订这个」→ HITL 卡片 → 确认 → 预订结果 + 可选 pay_url
- [ ] 路径：取消经 HITL 后 status 更新

---

## 执行顺序

1. **Step 1** → 提出人确认 → **Step 2** → 确认 → **Step 3**
2. 每 Step 全部 `[✅]` 后再进入下一步
3. Phase 4 完成后：沉淀 `memory.md`、同步 `docs/TECH.md` / `docs/PRD.md`（按 AGENTS.md）
