# Execution Plan：工具菜单 + 我的行程单

> 栈约束：FastAPI + Vue3；身份 Session；行程 HTML 仍走 MinIO；列表权威在 DB。

## Step A：工具导航壳

### 目标

侧栏加「工具」；工具页内二级菜单「旅程」→「我的行程单」空态。

### 方案

1. `App.vue`：`allLinks` 增加 `{ to: "/tools", label: "工具", icon: "tools", match: "tools" }`（放在知识洞察后、设置前）
2. `router.ts`：`/tools` 布局 + 子路由 `/tools/trips`；默认 redirect
3. `ToolsLayout.vue`：页内左侧二级导航（旅程可展开 → 我的行程单）
4. `MyTripsView.vue`：空态文案 + CTA「去对话规划」（`/chat?mode=agent`）
5. 样式对齐 `web/style.md`（12.5px、`--bg`/`--card`/`--muted`/`--teal`）
6. `docs/PRD.md` / `docs/TECH.md` 记工具 IA

### 验收

- [✅] 侧栏有「工具」入口，点进 `/tools` 落到行程单页
- [✅] 页内可见「旅程」展开项「我的行程单」
- [✅] 空态可见，CTA 跳转 Multi Agent 对话

---

## Step B：行程落库与列表

### 目标

`save_plan_html` 时写 `plan_record`；工具页拉取本人列表。

### 方案

1. Alembic `plan_record`：`id, user_id, conversation_id, title, origin, destination, depart_date, minio_key, url, payload(JSON), created_at`
2. Model + `GET /api/plans`（Session 用户）；可选 `GET /api/plans/{id}` 详情
3. `node_plan` 传入 `user_id` + `session`；save 时落库（无 MinIO 也写，url/key 可空）
4. 前端 `listPlans` + `MyTripsView` 渲染表格；有 url 可新开查看
5. 单测：落库归属、跨用户隔离、列表契约
6. 更新 PRD/TECH

### 验收

- [✅] save 后当前用户列表可见
- [✅] 用户 A 看不到用户 B 的行程
- [✅] 无 MinIO 时仍有记录（url 可空）
- [✅] 工具页展示真实列表或空态
