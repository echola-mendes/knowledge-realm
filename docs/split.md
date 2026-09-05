# server/app 包结构评估与拆分路线图

**状态**：批 1–3 已于 2026-09-05 执行完毕（`agent/` → `ingest/` → `rag/`，三次独立提交，全量回归通过）；此后新域代码直接落目标子包（审计落 `app/audit/`）。  
**依据**：2026-09-01 架构评审；2026-09-05 复核边界（checkpoint / chains / search+chat）。  
**相关**：`docs/TECH.md`、`docs/PRD-DECISIONS.md`、`docs/PRD-OPERATIONS.md`。

---

## 结论

- **不合理**：`app/` 根目录大量平铺 `.py`，文档入库 / RAG / Agent / 洞察混层，导航成本高。
- **合理**：保留 **`server/app` 作为唯一 Python 包根** — `uvicorn app.main:app`、pytest `from app.*`、Alembic `from app.models` 均依赖此路径。
- **不建议**上移到 `server/kb/`、`server/rag/` 等多顶层包。

---

## 现状

```
server/
  alembic/
  tests/          # 全部 from app.*
  app/
    main.py
    config.py db.py models.py schemas.py deps.py …   # 横切 + 大量平铺模块
    routers/      # HTTP 薄层
    travel/       # 差旅供应商
    news/         # AI 资讯
    jobs/ scheduler/ worker/ services/
```

| 指标 | 数值（约） |
|---|---|
| `app/` 根目录 `.py` | ~36 个 |
| 已有子包 | `routers/` `travel/` `news/` `jobs/` `scheduler/` `worker/` `services/` |

### 逻辑分组（物理路径暂扁平处）

| 域 | 模块 |
|---|---|
| 横切 | `config` `db` `models` `schemas` `deps` `user` `passwords` `llm` |
| 文档入库 | `parse` `chunk` `index` `storage` `url_import` `chunk_settings` `chunk_label` |
| RAG / Chat | `search` `rerank` `es_bm25` `chat` `conversation_summary` |
| Agent | `graph` `master` `intent` `tools` `checkpoint` `ltm` `plan_agent` `booking_agent` |
| 混合 / 暂留根 | `chains`（被 index/insights 与对话摘要共用） |
| 其他服务 | `insights` `recommendations` `quality` `rag_eval` `kb` `message_ui` `news_service` |
| 差旅 / 资讯 / 任务 | `travel/*` `news/*` `jobs/` `scheduler/` `worker/` |

---

## 什么算合理

1. **`app` 作应用包名** — 无需改启动命令。
2. **`routers/` 独立** — HTTP 与业务分离。
3. **域子包先例** — `travel/`、`news/` 边界清晰，新域照此办。
4. **横切留根** — `config` / `db` / `models` / `schemas` / `deps` / `llm` 被全项目引用，暂留根可接受。

## 已成痛点

1. 打开 `app/` 无法一眼区分入库 / 检索 / Agent。
2. `app/search.py` vs `app/routers/search.py` 命名歧义。
3. Agent 域膨胀后与 `parse`/`index` 同级。
4. 任意路径变更 = 全仓改 import + 测试回归。
5. 决策/操作审计若先写在根目录，拆包后还要再迁一遍。

---

## 何时值得拆（触发条件）

满足 **任意 2 条** 再动手搬迁既有文件：

- 新增第 3 个子 Agent 或新垂直域
- `app/` 根目录模块数 > 40，或单文件持续 > 500 行需拆分
- 新人反复问「这个文件该放哪」
- 出现循环 import，需靠延迟 import 兜底
- **即将落地 `audit` P0**（避免 recorder 先落根再搬）

---

## 目标结构

**原则**：`app` 仍是唯一包；内部按领域分子包；`routers/` 保持薄层；包名单数域名（与 `travel/` / `news/` 一致）。

```
server/app/
  main.py
  config.py db.py models.py schemas.py deps.py
  user.py passwords.py llm.py          # 横切 / 广引用，暂留根
  chains.py                            # 暂留根（或多批后再进 rag/）
  kb.py insights.py recommendations.py quality.py rag_eval.py
  message_ui.py news_service.py        # 后续可并入 agent/travel 或 news/

  routers/                             # 不变
  travel/                              # 已存在
  news/                                # 已存在
  jobs/ scheduler/ worker/ services/   # 已存在

  agent/       # 批 1
  ingest/      # 批 2
  rag/         # 批 3（search + chat 同批，避免 import 改两遍）
  audit/       # 新代码直接落此（decision / operations），不先写根目录
```

### 迁入明细（已定）

| 批次 | 新子包 | 迁入模块 | 理由 / 边界 |
| --- | --- | --- | --- |
| 1 | `app/agent/` | `graph` `master` `intent` `tools` `plan_agent` `booking_agent` **`checkpoint`** （可选 `ltm`） | P4 最胀；`checkpoint` 只被 graph/master 用，**不进 chat** |
| 2 | `app/ingest/` | `parse` `chunk` `index` `storage` `url_import` `chunk_settings` `chunk_label` | P0 文档管线，边界最干净 |
| 3 | `app/rag/` | `search` `rerank` `es_bm25` `chat` （可选 `conversation_summary`） | **search 与 chat 同批**；禁止拆成 `search/` + `chat/` 两包两批 |
| 不动 | 根目录 | `main` `config` `db` `models` `schemas` `deps` `user` `passwords` `llm` `kb` `insights` `recommendations` `quality` `rag_eval` `news_service` `message_ui`；**`chains` 暂留根** | `chains` 被 index/insights 与对话共用，勿塞进 chat；`llm` 被 news/agent/rag 共用 |
| 后续 | `app/audit/` | 决策审计 / 操作审计的 recorder 与薄封装 | PRD-DECISIONS / PRD-OPERATIONS 新代码一次到位 |
| 末 | （可选） | `models` / `schemas` 按域拆 | 一动全仓抖，最后再考虑 |

### 明确否决的分法

| 否决 | 原因 |
|---|---|
| `checkpoint` → `chat/` | 实为 LangGraph 持久化，调用方是 agent |
| `chains` → `chat/` | 文档富化 / 打标签也在用，不全是对话 |
| 单独 `app/search/` + 单独 `app/chat/` 分两批 | `chat` 依赖 `search`，import 改两遍 |
| 包名 `app/agents/`（复数） | 与现有 `travel/` `news/` 单数域名不一致 → 用 **`app/agent/`** |

### 推荐拆分顺序与操作

| 批次 | 内容 | 理由 |
|---|---|---|
| 1 | `app/agent/` | 膨胀最明显；`travel/` 保持独立（agent 调用 travel，不并入） |
| 2 | `app/ingest/` | 边界清晰、变更频率相对低 |
| 3 | `app/rag/` | 检索 + chat 一次迁完 |
| 新功能 | `app/audit/` | 不搬旧代码；P0 审计直接新建 |
| 末 | `models` / `schemas` | 最后搬 |

每批：`git mv` + 机械替换 `from app.xxx` → `from app.<pkg>.xxx` + 跑受影响测试子集。

---

## 零成本改进（现在可做）

1. **新文件遵守约定**：Agent 进 `app/agent/`（若批 1 未建，先建空包再写）；差旅进 `travel/`；资讯进 `news/`；审计进 `audit/`。
2. **避免根目录新增 `*_agent.py`、`*_recorder.py`。**
3. 监控/文档占位页不依赖包结构，可继续迭代。
4. 本文件为逻辑分组与搬迁契约；`docs/TECH.md` 引用此处。

---

## 搬迁风险备忘

| 风险 | 缓解 |
|---|---|
| 全仓 import 遗漏 | `rg "from app\."` + pytest 全绿 |
| `search` 模块 vs 路由同名 | 逻辑进 `app/rag/search.py`；HTTP 仍 `routers/search.py` |
| Alembic 引 `app.models` | `models` 暂留根直到最后一批 |
| Git blame 断裂 | `git mv`；按批提交 |
| 审计埋点路径改两遍 | 先定本路线，再写 `audit/`；PRD-DECISIONS 按 `app.audit.*` 写 import |

---

## 决策记录

| 日期 | 决策 |
|---|---|
| 2026-09-01 | 认同分批拆分；P4 稳定前不急于搬迁；归档判断与路线图 |
| 2026-09-05 | 定稿目标包：`agent/` + `ingest/` + `rag/`；`checkpoint` 归 agent；`chains` 暂留根；否决 search/chat 分拆两批；审计新代码落 `app/audit/` |
| 2026-09-05 | 批 1–3 执行完毕（提交 `45e74b7` / `3698b40` / `ff04603`）：`git mv` 保留历史，全仓 import 机械替换（含 `from app import x` 与 monkeypatch 字符串两种次要风格），受影响测试逐批通过；全量回归与搬迁前对照，失败集均为预存的顺序相关波动，零新增回归 |
