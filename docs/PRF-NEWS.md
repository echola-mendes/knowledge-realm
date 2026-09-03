
# AI 资讯 — 需求文档

## 1. 需求概述

在「知域 → 工具」中新增 **AI 资讯**工具，为用户提供每日精选资讯。

首期支持 3 个资讯板块：

* **科技**
* **AI 技术**
* **金融**

系统后台定时采集多个公开资讯源，经过去重、分类、AI 摘要、重要性评分和热度计算后，生成各板块的**今日 Top 20**。

### 核心流程

```text
资讯源
  ↓
定时采集
  ↓
解析 / 清洗
  ↓
新闻去重
  ↓
AI 分类 + 摘要
  ↓
重要性评分
  ↓
热度计算
  ↓
每日 Top 20
  ↓
PostgreSQL
  ↓
AI 资讯前端
```

---

# 2. 功能范围

## 2.1 AI 资讯工具

在知域：

```text
工具
├── AI 资讯
├── AI 生图
└── 旅程
```

点击「AI 资讯」进入资讯首页。

---

## 2.2 三个资讯板块

```text
AI 资讯

[科技] [AI 技术] [金融]
```

### 科技

关注：

* 科技公司
* 芯片
* 半导体
* 互联网
* 消费电子
* 新能源
* 汽车科技
* 科技产业

### AI 技术

关注：

* 大模型
* Agent
* RAG
* AI 应用
* AI 编程
* 多模态
* AI 芯片
* AI 开源项目
* AI 公司动态

### 金融

关注：

* 宏观经济
* 股票
* 基金
* 外汇
* 黄金
* 债券
* 期货
* 银行
* 金融政策
* 全球市场

---

# 3. 首页需求

## 3.1 页面结构

```text
┌─────────────────────────────────────────────┐
│ AI 资讯                         🔍 搜索资讯 │
│ 每日精选科技、AI 技术与金融热点             │
├─────────────────────────────────────────────┤
│                                             │
│   科技       AI 技术       金融             │
│                                             │
├─────────────────────────────────────────────┤
│ 今日热榜                         2026-09-03 │
│                                             │
│ 01  新闻标题                                 │
│     AI 摘要……                               │
│     来源 · 2小时前             🔥 98         │
│                                             │
│ 02  新闻标题                                 │
│     AI 摘要……                               │
│     来源 · 3小时前             🔥 95         │
│                                             │
│ ...                                         │
│                                             │
│ 20  新闻标题                                 │
└─────────────────────────────────────────────┘
```

---

## 3.2 每条资讯展示

每条新闻至少展示：

* 排名
* 新闻标题
* AI 摘要
* 来源
* 发布时间
* 资讯分类
* 热度分

例如：

```text
01

美联储维持利率不变，市场关注后续降息路径

AI 摘要：
美联储本次会议维持利率政策不变，市场关注
后续通胀数据以及降息节奏。

金融 · 宏观经济
新浪财经 · 2小时前

🔥 98
```

---

# 4. Top20 规则

三个板块分别生成：

```text
科技      Top 20
AI 技术   Top 20
金融      Top 20
```

即：

```text
今日总榜
├── 科技 Top20
├── AI 技术 Top20
└── 金融 Top20
```

不是三个板块混在一起排名。

---

# 5. 新闻采集

## 5.1 采集方式

第一版优先：

```text
RSS
API
```

暂时不做复杂网页爬虫。

Python 使用：

```text
httpx
feedparser
```

获取资讯源。

---

## 5.2 资讯源配置

不要把 RSS 地址直接写死在 `collector.py`。

建议配置成：

```text
NEWS_SOURCES
```

例如：

```python
NEWS_SOURCES = [
    {
        "name": "来源A",
        "category": "technology",
        "type": "rss",
        "url": "...",
    },
    {
        "name": "来源B",
        "category": "ai",
        "type": "rss",
        "url": "...",
    },
    {
        "name": "来源C",
        "category": "finance",
        "type": "rss",
        "url": "...",
    },
]
```

后续增加资讯源时，不需要修改业务逻辑。

---

# 6. 定时任务

采用 **APScheduler**。

第一版：

```text
每 30 分钟执行一次
```

流程：

```text
news_job
   ↓
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
service
   ↓
数据库
```

### 为什么不是每天凌晨执行？

因为资讯是实时产生的。

例如：

```text
09:00 采集
12:00 采集
15:00 采集
18:00 采集
21:00 采集
```

因此用户下午打开知域时，看到的是**当天实时更新后的 Top20**。

---

# 7. 新闻解析

`parser.py`

负责统一不同资讯源的数据结构。

无论来源是什么，最终转换成统一对象：

```python
NewsItem(
    title=...,
    url=...,
    source=...,
    content=...,
    published_at=...,
    category=...
)
```

统一字段后，后面的去重、AI 处理和评分不关心新闻来自哪里。

---

# 8. 新闻去重

`dedup.py`

需要避免：

```text
来源 A：
英伟达发布新一代 AI 芯片

来源 B：
英伟达推出新款 AI 芯片

来源 C：
英伟达最新 AI 芯片正式发布
```

被当成三条完全不同的新闻。

第一版采用两级去重：

### 一级：URL 去重

```text
url 唯一
```

### 二级：标题 Hash

对标题进行清洗：

```text
标题
 ↓
去空格
 ↓
去特殊字符
 ↓
统一大小写
 ↓
hash
```

数据库：

```text
content_hash
```

建立唯一索引。

### 后续

如果需要解决“不同标题但实际上是同一事件”，再增加：

```text
Embedding 相似度去重
```

MVP 暂时不做。

---

# 9. AI 新闻处理

`summarizer.py`

LLM 负责：

### 9.1 分类

只允许：

```text
technology
ai
finance
```

例如：

```json
{
  "category": "finance"
}
```

---

### 9.2 摘要

生成约：

```text
50～100 字
```

的中文摘要。

要求：

* 不改变原始事实
* 不自行补充不存在的信息
* 不加入投资建议
* 保留核心事件
* 简洁易读

---

### 9.3 重要性

LLM 给出：

```text
importance_score: 1~10
```

例如：

```text
9  全球重大事件
8  行业重大事件
7  重要公司动态
5  一般行业新闻
3  普通资讯
```

---

# 10. 热度计算

不要完全依赖 LLM。

最终：

```text
heat_score =
    来源权重
  + 时间衰减
  + 重要性
  + 多来源报道数量
```

例如：

```text
heat_score =
    importance × 40%
  + source_weight × 20%
  + freshness × 25%
  + coverage × 15%
```

最终归一化：

```text
0 ~ 100
```

然后：

```text
ORDER BY heat_score DESC
LIMIT 20
```

---

# 11. 时间衰减

越新的新闻，热度越高。

例如：

```text
刚发布       100%
1小时         95%
3小时         85%
6小时         70%
12小时        50%
24小时        20%
```

避免昨天的新闻长期霸榜。

---

# 12. 数据库设计

建议新增两张表。

## news

```text
news
├── id
├── title
├── source
├── url
├── content
├── summary
├── category
├── importance_score
├── heat_score
├── published_at
├── content_hash
├── created_at
└── updated_at
```

---

## news_daily_rank

保存每日榜单。

```text
news_daily_rank
├── id
├── news_id
├── rank_date
├── category
├── rank
├── score
└── created_at
```

例如：

```text
2026-09-03 | finance    | 1 | 98
2026-09-03 | finance    | 2 | 95
2026-09-03 | technology | 1 | 96
2026-09-03 | ai         | 1 | 99
```

这样可以保留历史榜单。

---

# 13. API

新增：

```text
/api/news
```

## 获取今日 Top20

```http
GET /api/news/hot
```

参数：

```text
category
limit
```

例如：

```http
GET /api/news/hot?category=finance&limit=20
```

---

## 获取三个板块

首页推荐：

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

前端切换 Tab 不需要再次请求。

---

## 获取资讯详情

```http
GET /api/news/{id}
```

返回：

```json
{
  "id": 1,
  "title": "...",
  "summary": "...",
  "content": "...",
  "source": "...",
  "url": "...",
  "category": "finance",
  "published_at": "...",
  "heat_score": 96
}
```

点击新闻后可以跳转原始来源。

---

# 14. 项目目录

按照你现在 Python 服务的结构，建议：

```text
server/
└── app/
    ├── api/
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
    ├── jobs/
    │   └── news_job.py
    │
    └── models/
        └── news.py
```

职责严格保持：

| 文件                 | 职责               |
| ------------------ | ---------------- |
| `api/news.py`      | HTTP API         |
| `collector.py`     | 获取 RSS/API 原始数据  |
| `parser.py`        | 解析、标准化新闻         |
| `dedup.py`         | 新闻去重             |
| `summarizer.py`    | LLM 分类、摘要、重要性    |
| `scorer.py`        | 热度计算、排序          |
| `service.py`       | 串联完整业务流程         |
| `jobs/news_job.py` | APScheduler 定时执行 |
| `models/news.py`   | 数据库模型            |

**不要让 `news_job.py` 自己实现新闻业务逻辑。**

应该：

```python
async def news_job():
    await news_service.refresh()
```

业务全部进入：

```text
news/service.py
```

---

# 15. 完整执行流程

```text
APScheduler
     │
     │ 每30分钟
     ↓
news_job.py
     │
     ↓
service.py
     │
     ├── collector.py
     │      ↓
     │    RSS/API
     │
     ├── parser.py
     │      ↓
     │    标准 NewsItem
     │
     ├── dedup.py
     │      ↓
     │    删除重复新闻
     │
     ├── summarizer.py
     │      ↓
     │    AI 分类
     │    AI 摘要
     │    AI 重要性
     │
     ├── scorer.py
     │      ↓
     │    热度计算
     │
     └── PostgreSQL
            ↓
       news_daily_rank
            ↓
       /api/news/hot
            ↓
          前端
```

---

# 16. MVP 明确不做

第一版明确排除：

* ❌ 用户订阅
* ❌ 新闻收藏
* ❌ 评论
* ❌ 点赞
* ❌ 个性化推荐
* ❌ 新闻推送
* ❌ 新闻全文爬取平台
* ❌ Embedding 新闻去重
* ❌ 多 Agent
* ❌ 新闻向量库
* ❌ 新闻问答
* ❌ 投资建议
* ❌ 股票买卖建议

尤其是**金融资讯只做信息聚合和摘要，不做投资建议**。

---

# 17. 后续扩展

MVP 稳定后，再考虑：

```text
AI 资讯
│
├── 科技
├── AI 技术
├── 金融
│
├── 🔍 AI 搜索
├── ⭐ 收藏
├── 📌 关注主题
├── 🤖 AI 解读
└── 🔗 Agent Tool
```

其中我认为对你的「知域」最有价值的是最后一个：

```text
Agent
  ↓
search_news()
  ↓
AI资讯
  ↓
金融 / 科技 / AI
  ↓
返回最新新闻
```

这样 AI 资讯就不只是一个孤立的工具，而是可以成为**知域 Agent 的外部实时知识 Tool**。

### 最终 MVP 边界

```text
                知域
                 │
                工具
                 │
             ┌───┴────┐
             ↓        ↓
          AI资讯     AI生图
             │
       ┌─────┼─────┐
       ↓     ↓     ↓
      科技   AI技术  金融
       │     │     │
      Top20 Top20 Top20
       │     │     │
       └─────┼─────┘
             ↓
        每30分钟更新
             ↓
          PostgreSQL
```


