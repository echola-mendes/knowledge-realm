---
name: html-plan
description: 将机酒方案推荐结果组合为带内联 CSS 的单文件 HTML，通过 save_plan_html 工具推送至前端 iframe 渲染。用于 itinerary_plan_agent 完成方案规划（及可选审核）后，将方案以结构化 HTML 展示给用户。语言无关，Python/Java Agent 均可使用。
---

# 机酒行程方案 → HTML 渲染

## 触发条件

当你（itinerary_plan_agent）已完成以下步骤：
1. 调用 `search_flights` / `search_hotels` 检索候选
2. 调用 `plan_itinerary` 生成多套方案
3. （可选）调用 `review_itinerary` 完成审核

此时需要将完整方案展示给用户。知域主链路由 `save_plan_html` → `render_plan_html` **确定性套模板**生成（对齐 `reference.html` 结构）；若走 LLM 拼装，须先读取同目录 `reference.html`，**完整保留 `<style>` 不变**，只替换 `<body>` 数据。

## 参考模板

**必须先读取 `reference.html`**，它包含：
- 完整的内联 CSS（禁止修改或删减）
- 7 个内容区块的 HTML 骨架与类名约定
- 上海→杭州的示例数据（替换为真实数据即可）

生成时规则：
1. 复制 `reference.html` 全文作为起点
2. 只改 `<title>`、`<body>` 内的文案和数据
3. `<style>` 块一字不改
4. 无数据的区块（如无天气、无倒计时）直接删除对应 DOM 节点，不要留空占位

## 方案内容结构（倒金字塔，必守顺序）

严格按以下顺序输出——推荐方案置顶，审核结论紧随其后，评估足迹放在最末：

| 顺序 | 区块 | CSS 类 |
|------|------|--------|
| 1 | 标题头（路线、日期、事由、可选倒计时） | `.header` `.meta` `.alert-warning` |
| 2 | **推荐方案**（理由 + 天气 + 费用表） | `.recommend-reason` `.weather-box` `table` |
| 3 | 审核结论（2–3 行） | `.audit-conclusion` |
| 4 | 方案对比表 | `table.comparison-table` |
| 5 | 方案明细（每套一个 `.plan-item`） | `.recommended` / `.warning` / `.failed` |
| 6 | 下一步操作（≤3 条） | `.next-steps` |
| 7 | Agent 行为说明（最末，≤6 条） | `.agent-actions` > `.action-item` |

### 内容示例（Markdown 结构参考，实际输出为 HTML）

```markdown
## 🗂️ 差旅行程方案（上海 → 杭州，2026-07-16 去 / 2026-07-18 返）

### 🏆 推荐方案 · 综合最佳
> **为什么是它**：综合分最高，总价最低、总耗时最短。
> **🌤️ 天气提醒**：上海 多云 28-35°C；杭州 小雨 26-33°C。

| 环节 | 详情 | 费用 |
|------|------|------|
| 🛫 去程 | 东航 MU5678，虹桥 07:30 → 萧山 09:45，经济舱 | ¥620 |
| 🛬 返程 | 东航 MU5679，萧山 20:10 → 虹桥 22:20，经济舱 | ¥620 |
| 🏨 酒店 | 全季酒店（西湖店），大床房，2 晚 | ¥826 |
| **合计** | **耗时 4h05m ｜ 评分 时80/价90/偏70/体85/综85** | **¥1313** |

### 📋 方案对比
（多列对比表，推荐行标注 ✅推荐）

### 🔍 方案明细
（每套方案独立条目，含去程/返程/酒店/评分/未通过原因）

### 👉 下一步
（确认方案 / 调整条件）

### 🧭 为你做了什么（最末）
（候选数量、组合方案数、筛选逻辑、审核情况；禁止贴供应商体验模式/开放平台营销原文）
```

## 数据要求

- **禁止编造**：航班号、时间、票价、酒店名、房型、晚数、总价、耗时、评分等**必须逐字取自工具返回**（`plan_itinerary`、`search_flights`、`search_hotels`、审核报告）；数据源中不存在的字段留空或删除对应节点，不得脑补。
- **禁止编造偏好**：仅当 `user_memory` 或用户本轮对话明确表达了偏好时，才可描述"匹配了您的偏好"；否则不得声称方案符合未表达的航司、时段、直飞等偏好。
- **禁止暴露内部名称**：HTML 中不得出现工具函数名、Agent 名、内部字段名等 `snake_case`（如 `plan_itinerary`、`combo_count`、`total_budget`）；统一改写为中文自然语（"候选搜索""总时长""总预算""方案总数"）。

## 样式速查

| 元素 | CSS 类 | 说明 |
|------|--------|------|
| 页面容器 | `.card` | 白底圆角卡片，max-width 900px |
| 二级标题 | `.section-title` | 18px 加粗，带 emoji |
| 推荐原因 | `.recommend-reason` | 左蓝边框 `#3b82f6`，浅灰底 |
| 天气 | `.weather-box` > `.weather-item` | 两列响应式，移动端单列 |
| 价格 | `.price` | 红色 `#dc2626` 加粗 |
| 审核结论 | `.audit-conclusion` | 选中态浅蓝底 `#eff6ff`、蓝字 `#2563eb` |
| 对比表 | `.comparison-table` | 13px，横向滚动 |
| 方案明细 | `.plan-item` | 加 `.recommended` / `.warning` / `.failed` |
| 状态标签 | `.badge-success` / `.badge-warning` / `.badge-danger` | 绿/黄/红 |
| 备注 | `.plan-note.success` / `.warn` / `.fail` | 对应状态色 |
| Agent 行为 | `.agent-actions` > `.action-item` | 2~3 列网格 |
| 下一步 | `.next-steps` | 蓝色底 `#eff6ff` |

### 状态颜色

- **通过/推荐**：`#eff6ff` / `#2563eb` / `#bfdbfe`（对齐对话列表 `.list-item.on`）
- **隐患/警告**：`#fffbeb` / `#a16207` / `#fde68a`
- **未通过/错误**：`#fef2f2` / `#b91c1c` / `#fecaca`

## 工作流

### Step 1：组装方案数据

从工具返回中提取：用户请求、推荐方案、全部方案对比、审核结论、天气摘要、候选数量、组合方案数。

### Step 2：基于 reference.html 生成 HTML

读取 `reference.html`，保留 `<style>` 不变，替换 `<body>` 内容为真实数据。

### Step 3：调用 save_plan_html

```
save_plan_html(html="<完整 HTML 字符串>", title="上海 → 杭州 差旅行程方案")
```

工具行为（语言无关）：
1. 将 HTML 上传至对象存储（如 MinIO，key 前缀 `plans/`）
2. 通过 SSE 推送 `plan_html` 事件：`{ "type": "plan_html", "html": "...", "title": "..." }`
3. 前端在 iframe 中用 `srcDoc` 渲染

调用成功后，只输出一句简短确认（如"方案已生成，请查看下方完整方案展示"），**不要重复输出方案正文**。

## 输出质量检查清单

- [ ] `<style>` 与 `reference.html` 完全一致
- [ ] 所有价格使用 `.price` 样式
- [ ] 推荐方案使用 `.plan-item.recommended`
- [ ] 隐患/未通过方案分别用 `.warning` / `.failed`
- [ ] 对比表保留表头，移动端可横向滚动
- [ ] 数据全部来自工具返回，未编造
- [ ] HTML 中无 snake_case 内部名称
- [ ] 已调用 `save_plan_html`
- [ ] 区块顺序为推荐→对比→明细→下一步→Agent；无支付链接/体验模式营销

## 禁止事项

- 不要把 CSS 拆成独立 `.css` 文件；必须单文件 HTML。
- 不要修改 `<style>` 块中的任何规则。
- 不要自创「行程概览 / 关键提醒 / 操作建议 / 支付链接」版式——那是预订结果，不是方案页。
- 不要把「Agent 为你做了什么」放在页面顶部；评估足迹必须在最末。
- 不要把供应商「体验模式 / 开放平台 / API Key」营销文案原样塞进方案页。
- 不要用「搜索结果第一套/首个方案」作为推荐理由；须基于总价/标签等可解释依据。
- 不要删除方案中的费用信息或修改事实数据。
- 不要编造未提供的天气、审核结论。
- 不要在调用 `save_plan_html` 后再输出方案 Markdown 正文。
