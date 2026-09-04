
# AI 资讯功能需求文档

**需求名称：** 知域 AI 资讯
**版本：** V1.1
**状态：** 业务管道待开发（通用定时任务基建已就绪）
**所属模块：** 知域 → 工具 → AI资讯

> **V1.1 澄清说明：** 下文中带「已拍板」的规则为产品确认结论；实现须遵守。任务类型码与 [`PRD-Job.md`](PRD-Job.md) 对齐为 `NEWS_REFRESH`。

---

## 0. 已拍板决策摘要

| 主题 | 结论 |
| --- | --- |
| 数据源 | 默认提供一批合法公开 RSS（实现前再确认清单）；**配置文件可配置**，URL 不硬编码；第一版不做源管理 UI |
| 排行榜 | 任务写入 `news_daily_rank` 快照；API 默认读当天，支持 `?date=` 回看历史；前端第一版只展示当天 |
| 正文 | 仅用 RSS/API 自带字段；可为空；**不抓取原文网页全文** |
| 启用板块 | 在 **AI资讯页** 勾选科技/AI/金融；定时任务执行时自动读取；**定时任务页不配分类** |
| 热度 | `importance×45% + source_weight×25% + freshness×30%`；不做多源出现加分 |
| 时区 | `Asia/Shanghai` 自然日 |
| 立即执行 | 仅「基础 → 定时任务」页；AI资讯页不提供立即更新按钮 |
| 任务类型 | 代码：`NEWS_REFRESH`；界面展示名：「AI资讯更新」 |

---

## 1. 需求目标

在知域「工具」中新增 **AI 资讯**功能，用于聚合、处理和展示实时资讯。

第一阶段支持三个资讯分类：

* 科技
* AI
* 金融

AI 资讯采用「**一个入口 + 多个频道**」设计。

用户进入 AI 资讯后默认查看「全部」综合热榜，也可以切换到单独分类。

后台资讯更新使用项目现有的**通用定时任务系统**，AI 资讯只作为一种业务任务接入，不重新实现定时任务、Redis、Worker 等基础设施。

---

# 2. 功能范围

本次只实现：

```text
AI资讯
├── 全部
├── 科技
├── AI
└── 金融
```

包括：

1. 资讯采集
2. 资讯解析
3. 资讯去重
4. 资讯分类
5. AI 摘要
6. 热度/重要性评分
7. 分类 Top20
8. 综合 Top20
9. 资讯列表
10. 资讯详情
11. 原文跳转
12. 接入现有定时任务（NEWS_REFRESH）
13. 支持在定时任务页手动触发资讯更新
14. AI资讯页启用板块设置

---

# 3. 产品结构

```text
知域
└── 工具
    └── AI资讯
        ├── 全部
        ├── 科技
        ├── AI
        └── 金融
```

---

# 4. AI资讯首页

默认进入：

```text
全部
```

页面结构：

```text
AI资讯

[全部] [科技] [AI] [金融]

今日热榜                         2026-09-04

01  新闻标题
    AI摘要
    来源 · 2小时前                     热度 98

02  新闻标题
    AI摘要
    来源 · 3小时前                     热度 96

03  新闻标题
    AI摘要
    来源 · 4小时前                     热度 94

...
```

---

# 5. 分类频道

## 5.1 全部

将当天：

```text
科技
AI
金融
```

三个分类的资讯进行合并。

按照最终 `heat_score` 从高到低排序。

只展示：

```text
Top 20
```

---

## 5.2 科技

只展示：

```text
category = technology
```

当天热度最高的 20 条。

---

## 5.3 AI

只展示：

```text
category = ai
```

当天热度最高的 20 条。

---

## 5.4 金融

只展示：

```text
category = finance
```

当天热度最高的 20 条。

---

# 6. 分类设计

第一阶段固定三个分类：

```text
technology = 科技
ai         = AI
finance    = 金融
```

后端使用稳定枚举值，不直接使用中文作为数据库枚举值。

例如：

```python
TECHNOLOGY = "technology"
AI = "ai"
FINANCE = "finance"
```

后续如果增加分类，不应破坏现有数据结构。

---

# 7. 资讯数据来源

**已拍板。**

第一阶段优先使用：

* RSS
* Atom
* 官方公开 API
* 合法公开资讯 API

暂不要求实现复杂网页爬虫，**也不抓取原文网页全文**（见 §18）。

资讯来源必须配置化，**禁止把 URL 硬编码在业务代码中**。

默认配置文件：

```text
server/config/news_sources.yaml
```

可用 `.env` 的 `NEWS_SOURCES_PATH` 覆盖路径。第一版默认 8 个启用源（科技 3 + AI 4 + 金融 1），另含关闭的 Reuters 备选。

字段说明：

* `type`：`rss` | `atom` | `api`
* `category`：该源的默认分类（`technology` / `ai` / `finance`）
* `weight`：来源权重 0～100，参与热度计算
* `enabled`：是否参与采集

科技 / AI / 金融来源分别配置、分别维护。改 yaml 即可增删源。  
**第一版不做「源管理」前端页面。**

---

# 8. 资讯采集流程

完整流程：

```text
资讯来源（按启用板块过滤）
   ↓
采集
   ↓
解析
   ↓
标准化（含来源默认分类）
   ↓
去重
   ↓
保存原始资讯
   ↓
LLM摘要
   ↓
重要性评分
   ↓
热度计算
   ↓
更新当日排行榜快照
```

---

# 9. 资讯去重

第一阶段采用两级去重。

## 9.1 URL去重

相同 URL 视为重复资讯。

数据库应保证 URL 唯一。

**已拍板：** 同一 URL 再次出现时不重复入库；可更新与热度/时间相关的字段；**不重复调用 LLM**（标题未变更时）。

---

## 9.2 标题 Hash 去重

对标题进行标准化：

```text
去除首尾空格
合并连续空白
统一大小写
去除明显无意义符号
```

然后计算 Hash。

例如：

```text
SHA256(normalized_title)
```

相同 Hash 视为重复。

**已拍板：** URL 不同但标题 Hash 冲突时，**跳过**入库，记入任务结果的 `skipped_dup`。

字段名：模型中的标题 Hash 存为 `content_hash`（历史命名，实际为标题标准化后的 Hash）。

---

# 10. 暂不实现语义去重

第一阶段不使用 Embedding 做新闻语义去重。

暂不实现：

```text
Embedding
    ↓
向量相似度
    ↓
判断是否为同一事件
```

后续资讯规模扩大后再考虑。

---

# 11. 资讯分类

**已拍板（第一版）。**

资讯分类**一律来自来源配置的默认分类**，不调用 LLM 改分类。

例如：

```text
AI Source
    ↓
category = ai
```

最终只允许：

```text
technology
ai
finance
```

后续若开放 LLM 辅助分类，非法返回必须 fallback 到来源默认分类，不能直接写入数据库。第一版不做。

---

# 12. AI摘要

每条资讯生成简洁中文摘要。

要求：

* 忠于原文
* 不添加原文不存在的信息
* 不编造事实
* 不夸大
* 保留核心事件
* 适合直接展示给用户

建议摘要长度控制在：

```text
50～120字
```

具体长度可以根据现有 LLM 能力调整。

---

# 13. 重要性评分

LLM 对资讯进行重要性评分：

```text
1～10
```

参考：

| 分数   | 含义     |
| ---- | ------ |
| 9-10 | 重大行业事件 |
| 7-8  | 重要行业动态 |
| 5-6  | 一般行业资讯 |
| 3-4  | 低重要性资讯 |
| 1-2  | 信息价值较低 |

评分只是热度计算的一个输入，不直接作为最终排行榜分数。

---

# 14. 热度评分

**已拍板。**

最终生成：

```text
heat_score
```

范围：

```text
0～100
```

第一版公式（权重集中在 `scorer.py`，允许后续调参，禁止散落）：

```text
importance_norm = (importance_score - 1) / 9 * 100   # importance 1～10
source_norm     = source_weight                        # 源配置 0～100
freshness_norm  = 新鲜度档位百分比 * 100               # 见 §15

heat_score = clamp(0, 100,
  0.45 * importance_norm
+ 0.25 * source_norm
+ 0.30 * freshness_norm
)
```

**第一版不做「多来源出现」加分**（无语义去重，无法可靠聚类同一事件）。

LLM 重要性评分失败时：`importance_score = 5`（中间档），仍计算热度并入库。

---

# 15. 新鲜度

新闻越新，热度越高。

建议：

```text
0～1小时       100%
1～3小时         90%
3～6小时         75%
6～12小时        55%
12～24小时       30%
超过24小时       不进入当日热榜
```

具体权重允许后续调整。

不要将这些数值散落在代码中，应配置化或集中定义。

**已拍板补充：**

* 「当天」按时区 `Asia/Shanghai` 的自然日计算。
* RSS 无 `published_at` 时，用采集时间 `collected_at` 作为发布时间参与新鲜度与入榜判定。
* 进入当日热榜须同时满足：发布时间落在该榜单日，且相对「现在」未超过 24 小时（超过 24 小时不入当日热榜）。

---

# 16. 每日排行榜

维护三个分类排行榜：

```text
科技 Top20
AI Top20
金融 Top20
```

同时生成：

```text
综合 Top20
```

说明：

* 分类榜：该分类当天候选按 `heat_score` 取 Top20。
* 综合榜：当天三个分类的资讯**合并后**按 `heat_score` 取 Top20（不是把三个 Top20 简单拼接）。
* 三个分类榜合计一天最多展示 `20 × 3 = 60` 条；综合榜另计最多 20 条展示位。

---

# 17. 排行榜刷新

不是每天只执行一次。

资讯更新任务每次执行后，都重新计算当天排行榜。

例如：

```text
08:00
 ↓
采集资讯
 ↓
更新 Top20

08:30
 ↓
采集新资讯
 ↓
重新计算 Top20

09:00
 ↓
再次更新
```

因此用户看到的是：

> **当天持续更新的实时热榜。**

---

# 18. 资讯详情

点击资讯进入详情。

展示：

```text
标题

来源
发布时间
分类

AI摘要

资讯正文（可为空）

[查看原文]
```

「查看原文」打开原始资讯 URL。

**已拍板：正文策略**

* 正文**仅**使用 RSS/Atom/API 返回的 content / summary 类字段。
* 无正文时 `content = null`，详情仍展示标题、摘要、来源、发布时间与原文链接。
* **第一版不使用 trafilatura 或其它方式抓取原文网页全文。**

前端路由建议：

```text
/tools/news          # 热榜列表
/tools/news/:id      # 详情
```

前端样式遵循项目 [`style.md`](style.md)。空态展示「暂无资讯」；列表展示榜单日期。

---

# 19. 金融资讯特殊约束

金融资讯只提供：

```text
资讯事实
信息摘要
热点聚合
```

禁止 LLM 输出：

```text
买入建议
卖出建议
股票推荐
投资建议
收益承诺
价格预测
```

例如：

❌

> 建议投资者买入 NVIDIA。

✅

> NVIDIA 发布最新财报，营收较上一季度有所增长。

---

# 20. 定时任务接入

项目已经存在独立的通用定时任务功能（见 [`PRD-Job.md`](PRD-Job.md)）。

**本需求不重新实现定时任务系统**（不重做 APScheduler / Redis / Worker / 通用任务管理）。

AI资讯注册的任务类型：

```text
task_type = NEWS_REFRESH
展示名   = AI资讯更新
```

任务执行时调用 AI 资讯更新业务（`NewsService.refresh`）。

---

# 21. 启用板块：在 AI资讯页配置（已拍板）

**板块启用不在定时任务页配置。**

用户在：

```text
工具 → AI资讯
```

页面上勾选要启用的板块：

```text
☑ 科技
☑ AI
☑ 金融
```

默认全部启用。持久化到独立资讯设置（如 `news_settings.enabled_categories`），与 `scheduled_task.schedule_config`（调度间隔）分离。

定时任务页选择类型 `NEWS_REFRESH`（展示「AI资讯更新」）时：

* 只配置名称、调度方式、间隔/Cron、启用开关
* **不展示**分类多选

---

# 22. 为什么把板块放在资讯页

不要要求用户创建三个定时任务：

```text
科技资讯任务 / AI资讯任务 / 金融资讯任务
```

也不要把板块勾选塞进任务表单。

正确分工：

```text
AI资讯页     → 启用哪些板块（业务偏好）
定时任务页   → 多久跑一次（调度）
Worker 执行  → 自动读取当前启用板块并更新
```

---

# 23. 定时任务执行逻辑

```text
AI资讯更新（NEWS_REFRESH）
    ↓
读取 news_settings.enabled_categories
    ↓
仅采集/处理已启用分类对应来源
    ↓
去重 / 摘要 / 评分 / 热度
    ↓
保存数据库
    ↓
重写当日 news_daily_rank（启用分类 + all）
```

若资讯页只启用 AI：

```text
☑ AI
☐ 科技
☐ 金融
```

则本次任务只更新 AI 分类及相关排行；未启用分类不采集、不重写其当日分类榜。

---

# 24. 手动执行

复用现有定时任务的「立即执行」。

```text
基础 → 定时任务 → AI资讯更新 → 立即执行
    ↓
同一条 Worker 路径
    ↓
读取当前启用板块并更新
```

**已拍板：** AI资讯页**不**提供「立即更新」按钮；**不要**在 AI 资讯模块另建一套任务机制。

---

# 25. 后端目录

遵循现有项目规范（`routers/` + 单文件 `models.py`），示例：

```text
server/
└── app/
    ├── routers/
    │   └── news.py
    │
    ├── news/
    │   ├── collector.py
    │   ├── parser.py
    │   ├── dedup.py
    │   ├── scorer.py
    │   ├── summarizer.py
    │   └── service.py
    │
    └── models.py          # 增加 News / NewsDailyRank / NewsSettings 等
```

Worker 侧：充实现有 `worker/handlers/news_handler.py` → 调用 `NewsService.refresh(categories=...)`，categories 来自 `news_settings`，不是任务表单。

不要为了本需求重复创建已有基础设施。

---

# 26. 模块职责

## `collector.py`

负责：

```text
请求 RSS/API
获取原始资讯
处理网络异常
```

不负责：

```text
LLM
数据库业务逻辑
排行榜
```

---

## `parser.py`

负责：

```text
RSS/Atom/API
    ↓
统一 NewsItem
```

负责字段标准化。

---

## `dedup.py`

负责：

```text
URL去重
标题Hash去重
```

---

## `summarizer.py`

负责：

```text
LLM摘要
LLM重要性评分
```

第一版不做 LLM 分类辅助（见 §11）。

---

## `scorer.py`

负责：

```text
热度计算
新鲜度计算
来源权重
最终 heat_score
```

---

## `service.py`

负责完整业务编排：

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
数据库
 ↓
排行榜
```

---

## `routers/news.py`

只负责：

```text
HTTP请求
参数校验
调用Service
Response
```

不要在 API 中写采集、LLM、评分等业务逻辑。

---

# 27. 数据模型

## 27.1 `news`

```text
id
title
summary
content              # 可为 null
url                  # 唯一
source
category             # technology | ai | finance
published_at
collected_at
importance_score
heat_score
content_hash         # 标准化标题 Hash，唯一
created_at
updated_at
```

## 27.2 `news_settings`

```text
id                   # 单行或 key-value
enabled_categories   # JSON 数组，如 ["technology","ai","finance"]
updated_at
```

默认三分类全开。由 AI资讯页读写。

---

# 28. 新闻排行榜数据

**已拍板：** 必须落库快照表 `news_daily_rank`；列表 API **读快照**，不实时全表排序作为主路径。

字段：

```text
id
news_id
rank_date            # Asia/Shanghai 自然日
category             # technology | ai | finance | all
rank                 # 1～20
score                # 写入时的 heat_score
created_at
```

每次资讯任务成功后：覆写（或删后插）**当日**相关 `category`（本次启用的分类 + `all`）的 rank 行。  
历史日快照保留，供 `?date=` 回看。

---

# 29. API

身份只来自 Session（与现有一致）。

## 获取热榜

```http
GET /api/news/hot
GET /api/news/hot?category=technology
GET /api/news/hot?date=2026-09-03
GET /api/news/hot?category=ai&date=2026-09-03
```

* 无 `category` 时等价 `category=all`
* `category` 合法值：`all` | `technology` | `ai` | `finance`；非法 → 400
* 无 `date` 时为上海时区「今天」
* 数据来自 `news_daily_rank` 快照

前端第一版只请求当天；历史日 API 先就绪。

---

## 获取资讯详情

```http
GET /api/news/{id}
```

---

## 启用板块设置

```http
GET /api/news/settings
PUT /api/news/settings
```

Body 示例：

```json
{ "enabled_categories": ["technology", "ai", "finance"] }
```

至少启用一个分类；非法枚举 → 400。

---

# 30. 推荐 `/api/news/hot` 返回结构

```json
{
  "date": "2026-09-04",
  "category": "all",
  "items": [
    {
      "id": 1,
      "rank": 1,
      "title": "新闻标题",
      "summary": "AI生成摘要",
      "category": "ai",
      "source": "来源",
      "published_at": "2026-09-04T09:30:00",
      "heat_score": 98
    }
  ]
}
```

---

# 31. 数据不足时的处理

如果某个分类当天不足 20 条：

例如：

```text
科技：20
AI：20
金融：8
```

则：

```text
金融只展示8条
```

不能使用其他分类资讯补足金融榜。

综合榜则按照已有资讯正常排序。

---

# 32. 资讯处理失败

单条资讯处理失败：

```text
第37条失败
 ↓
记录错误
 ↓
继续处理第38条
```

不能因为一条新闻失败导致整个任务立即终止。

如果整个数据源不可用：

```text
RSS timeout
```

应记录任务错误。

---

# 33. LLM失败处理

第一版不做 LLM 分类；分类始终来自来源配置。

摘要失败：

```text
保留原始资讯
summary = null
```

重要性评分失败：

```text
importance_score = 5
```

不能因为单条 LLM 失败导致整个资讯任务全部失败。

任务成功时 `task_execution.result` 建议包含：

```json
{
  "categories": ["ai"],
  "fetched": 40,
  "saved": 12,
  "summarized": 10,
  "failed": 2,
  "skipped_dup": 16
}
```

---

# 34. 配置要求

资讯来源不要写死。

建议：

```text
NEWS_SOURCES
NEWS_MAX_ITEMS
NEWS_TOP_K=20
NEWS_HTTP_TIMEOUT
NEWS_LLM_TIMEOUT
```

如果项目已有统一配置系统，则使用现有配置方式。

不要重复创建配置体系。

---

# 35. 前端交互

AI资讯首页：

```text
┌─────────────────────────────────────┐
│ AI资讯                              │
│                                     │
│ 启用板块：☑科技 ☑AI ☑金融            │
│                                     │
│ [全部] [科技] [AI] [金融]            │
│                                     │
│ 今日热榜                 09月04日    │
│                                     │
│ 01  新闻标题                         │
│     AI摘要……                        │
│     AI · 2小时前               98   │
│                                     │
│ 02  新闻标题                         │
│     AI摘要……                        │
│     科技 · 3小时前              96   │
│                                     │
│ ...                                 │
└─────────────────────────────────────┘
```

* 「启用板块」写入 `/api/news/settings`，影响后续定时任务采集范围。
* 「全部/科技/AI/金融」是浏览频道切换，只改列表查询参数，不改变启用设置。
* 样式遵循 [`style.md`](style.md)。

---

# 36. 前端状态

浏览频道切换只改变查询参数：

```text
category
```

不需要重新设计页面。与「启用板块」设置无关。

例如：

```text
全部 → /api/news/hot

科技 → /api/news/hot?category=technology

AI → /api/news/hot?category=ai

金融 → /api/news/hot?category=finance
```

登录态走现有 Session，与其它工具页一致。

---

# 37. 不做无限滚动

第一版只展示：

```text
Top20
```

不做：

```text
无限滚动
分页加载1000条
```

AI资讯第一阶段定位是：

> **热点资讯聚合，而不是完整新闻数据库浏览器。**

---

# 38. 验收标准

### AC-01

进入：

```text
知域 → 工具 → AI资讯
```

能够正常打开。

### AC-02

默认显示：

```text
全部
```

### AC-03

存在：

```text
全部 / 科技 / AI / 金融
```

四个频道。

### AC-04

全部频道最多20条。

### AC-05

三个分类分别最多20条。

### AC-06

资讯包含：

```text
标题
摘要
来源
发布时间
分类
热度
```

### AC-07

相同 URL 不重复。

### AC-08

相同标准化标题不重复。

### AC-09

资讯能够生成 AI 摘要。

### AC-10

资讯能够计算热度。

### AC-11

金融资讯不会生成投资建议。

### AC-12

AI资讯能够通过现有：

```text
定时任务 → AI资讯
```

自动更新。

### AC-13

AI资讯页可勾选启用：

```text
☑ 科技
☑ AI
☑ 金融
```

设置可持久化；定时任务页不展示分类多选。

### AC-14

在资讯页取消某分类启用后，下一次（含立即执行）`NEWS_REFRESH` **不会**更新该分类。

### AC-15

在「基础 → 定时任务」手动执行 AI资讯更新后能够正常更新资讯。

### AC-16

单条新闻处理失败不会导致其他新闻全部失败。

### AC-17

热榜数据来自 `news_daily_rank`；`GET /api/news/hot?date=` 可读取历史日快照。

### AC-18

无 RSS 正文时详情仍可打开，`content` 可为空，且不抓取原文网页。

---

# 39. 明确不修改的内容

本需求**不得重新实现**通用定时任务基础设施。

不要重复开发：

```text
❌ APScheduler
❌ Redis Queue
❌ Worker
❌ 通用任务执行器
❌ 通用任务管理
❌ 通用任务状态
```

允许的最小衔接：

```text
✓ 使用已有 task_type = NEWS_REFRESH
✓ Handler 调用 NewsService，并读取 news_settings.enabled_categories
✓ 不在 scheduled_task 上增加分类多选字段
```

AI资讯负责：

```text
资讯设置（启用板块）
↓
资讯采集 / 摘要 / 评分 / 排行榜
↓
News API + 前端
```

---

# 40. 开发原则

Cursor 开发时遵循：

1. **先读取现有项目结构和现有定时任务实现。**
2. 不假设定时任务模块的接口，必须根据现有代码接入。
3. 不重复创建已有基础设施。
4. API、Service、采集、LLM、评分职责分离。
5. 不把业务逻辑写进 API。
6. 配置统一使用项目现有配置机制。
7. 数据库迁移遵循项目现有迁移方式。
8. 前端 API 调用遵循项目现有 API 层规范。
9. 第一阶段不增加语义去重、Kafka、Celery 等额外基础设施。
10. 优先实现 MVP，不提前过度设计。

---

# 41. 最终业务模型

最终只需要记住这一套：

```text
                    知域
                     │
                    工具
                     │
                   AI资讯
                     │
          ┌──────────┼──────────┐
          ↓          ↓          ↓
         科技         AI         金融
          │          │          │
          └──────────┼──────────┘
                     ↓
                  资讯池
                     ↓
             去重 / 摘要 / 评分
                     ↓
          ┌──────────┼──────────┐
          ↓          ↓          ↓
       科技Top20   AI Top20   金融Top20
          └──────────┼──────────┘
                     ↓
                  综合Top20
```

配置与调度分工：

```text
AI资讯页：启用板块 ☑科技 ☑AI ☑金融
      ↓
news_settings
      ↓
通用定时任务 NEWS_REFRESH（只配调度）
      ↓
Worker 读取启用板块 → 更新资讯与排行榜
```

---

# 42. 边角规则（已拍板）

1. 时区：`Asia/Shanghai`。
2. 无 `published_at`：用 `collected_at`。
3. 同 URL：不重复入库；可更新热度/时间相关字段；不重复 LLM。
4. 标题 Hash 冲突（URL 不同）：跳过，计 `skipped_dup`。
5. LLM 重要性失败：`importance_score = 5`。
6. 第一版不让 LLM 改分类。
7. 「立即执行」仅在定时任务页。
8. 任务类型码 `NEWS_REFRESH`，展示名「AI资讯更新」。
9. 第一版不做源管理 UI；源在配置文件维护。
10. 前端第一版热榜只展示当天；历史日由 API 支持、UI 可后补。
