# server/app 包结构评估与拆分路线图

**状态**：暂缓执行 — P4 功能稳定前不搬迁代码。  
**依据**：2026-09-01 架构评审；P4 将原 `app/p1/` 上移至 `app/` 根目录（见 `docs/TECH.md`、`artifacts/architecture.md`）。

---

## 结论

**直觉对一半：**

- **不合理**：`app/` 根目录 **36 个平铺 `.py`**，P0 文档管线、RAG、Agent、洞察等混在同一层，导航成本高。
- **合理**：保留 **`server/app` 作为 Python 包根** — FastAPI 常见约定；`pytest.ini` 的 `pythonpath = .`、测试 `from app.main import create_app`、Alembic `from app.models import Base` 均依赖此路径。

**当前决策**：暂不搬迁。P4 刚完成稳定化，此刻大规模改 import 收益 < 风险（全量替换 + 50+ 测试回归）。

---

## 现状

```
server/
  alembic/
  tests/          # 43 个 test_*.py，全部 from app.*
  app/
    main.py
    config.py db.py models.py schemas.py deps.py …   # 横切 + 36 平铺模块
    routers/      # HTTP 层（11 个路由）
    travel/       # 差旅供应商（flyai / minio / rate_limit / tools）
```

| 指标 | 数值 |
|---|---|
| `app/` 根目录 `.py` | 36 个，合计 ~6160 行 |
| 子包 | 仅 `routers/`、`travel/` |
| 高频 import | `app.config` 45 次、`app.db` 39 次、`app.main` 29 次 |

### 逻辑分组（物理路径暂扁平）

| 域 | 模块 |
|---|---|
| 横切 | `config` `db` `models` `schemas` `deps` `user` `passwords` |
| 文档入库 | `parse` `chunk` `index` `storage` `url_import` `chunk_settings` `chunk_label` |
| RAG / Chat | `search` `rerank` `es_bm25` `chat` `llm` |
| Agent | `graph` `master` `intent` `tools` `chains` `checkpoint` `ltm` `conversation_summary` `plan_agent` `booking_agent` |
| 其他服务 | `insights` `recommendations` `quality` `rag_eval` `kb` |
| 差旅 | `travel/*` |

---

## 什么算合理

1. **`app` 作应用包名** — `uvicorn app.main:app`，无需改启动命令。
2. **`routers/` 独立** — HTTP 与业务分离。
3. **`travel/` 子包** — 供应商边界清晰，是正确先例。
4. **横切模块放根目录** — `config` / `db` / `models` / `schemas` / `deps` 被全项目引用，暂留根目录可接受。

## 已成痛点

1. **认知负担**：打开 `app/` 无法一眼区分文档入库 / 检索 / Agent。
2. **命名歧义**：`app/search.py`（检索逻辑）vs `app/routers/search.py`（HTTP 路由）。
3. **Agent 域膨胀**：10+ 文件与 `parse.py`、`index.py` 同级。
4. **测试耦合**：任何包路径变更 = 全仓机械改 import。

---

## 何时值得拆（触发条件）

满足 **任意 2 条** 再动手：

- 新增第 3 个子 Agent 或新垂直域（如财务 Agent）
- `app/` 根目录模块数 > 40，或单文件持续 > 500 行需拆分
- 新人反复问「这个文件该放哪」
- 出现循环 import，需靠延迟 import 兜底

---

## 目标结构（未来）

**原则**：`app` 仍是唯一 Python 包；只在其内部按领域分子包；`routers/` 保持薄层。

```
server/app/
  main.py
  config.py db.py models.py schemas.py deps.py   # 横切，最后动
  routers/                                         # 不变
  ingest/        # parse chunk index storage url_import chunk_settings
  rag/           # search rerank es_bm25 chat llm
  agent/         # graph master intent tools chains checkpoint ltm
                 # conversation_summary plan_agent booking_agent
  travel/        # 已存在，保持
  services/      # insights recommendations quality rag_eval（可选）
```

**不建议**把业务上移到 `server/kb/`、`server/rag/` 等多顶层包 — Alembic / pytest / 启动命令全要改，与项目惯用布局冲突。

### 推荐拆分顺序

| 批次 | 内容 | 理由 |
|---|---|---|
| 1 | `app/agent/` | P4 膨胀最明显；`travel/` 保持独立（agent 调用 travel，不并入） |
| 2 | `app/ingest/` | P0 文档管线，边界清晰、变更频率低 |
| 3 | `app/rag/` | 检索与 chat 链 |
| 末 | `models` / `schemas` | 一动全仓抖，最后搬 |

每批：`git mv` + 机械替换 `from app.xxx` → `from app.<pkg>.xxx` + 跑受影响测试子集。

---

## 零成本改进（现在可做）

1. **新文件遵守约定**：Agent / 差旅新增代码不进 `app/` 根目录，直接进子包（未来 `app/agent/` 或现有 `app/travel/`）。
2. **避免根目录新增 `*_agent.py`**。
3. 本文件即逻辑分组文档；`docs/TECH.md` 文件说明表可按需引用此处。

---

## 搬迁风险备忘

| 风险 | 缓解 |
|---|---|
| 50+ 文件 import 遗漏 | `grep -r "from app\."` + pytest 全绿 |
| `search.py` 模块 vs 路由同名 | 拆 `app/rag/search.py` 时 router 可保持 `routers/search.py` |
| Alembic 引 `app.models` | `models` 暂留根目录直到最后一批 |
| Git blame 断裂 | `git mv` 保留历史；按批提交 |

---

## 决策记录

| 日期 | 决策 |
|---|---|
| 2026-09-01 | 认同分批拆分路线；P4 稳定前不执行搬迁；本文档归档判断与路线图 |



建议：
这个思路对。现在 server/app/ 根目录有三十多个模块（graph.py、master.py、chat.py、parse.py、index.py…），子包 mainly 只有 routers/、services/、travel/、worker/ 等，扁平 + 局部子包 混着用，后面加决策审计、操作审计会不知道该往哪挂。

先迁移再开 P0，能避免：

DecisionRecorder 写进 app/decision_recorder.py，迁完又要挪到 app/audit/ 或 app/decisions/
graph / master / plan_agent 路径一变，埋点 import 全要改两遍
Alembic 模型若和 models.py 拆包不同步，迁移期更难排错
迁移时可以和 PRD 对齐的分包方向（供你参考，不必一次做完）：

子包	可迁入的现有模块
app/agents/
graph.py、master.py、plan_agent.py、booking_agent.py、intent.py
app/chat/ 或 app/rag/
chat.py、chains.py、conversation_summary.py、ltm.py
app/ingest/
parse.py、index.py、chunk.py、url_import.py
app/search/
search.py、rerank.py、es_bm25.py
app/audit/（迁完再加）
decision/ + operations/ 的 recorder、models 薄封装
models.py / schemas.py 可以暂时留在根上，或按域拆成 app/models/ —— 这和审计表何时加有关，表结构可以等包稳定后再迁 Alembic。

和当前 PRD 的关系：

文档、监控占位页已经写好，不依赖包结构，可以留着。
P0 实现时，按 PRD 直接落在 app/audit/decision/（或你定的子包名）即可，一次到位。
你先把后端归到子包里；迁完如果愿意，可以把目标目录结构发我，我可以帮你对一下 PRD-DECISIONS 里的埋点路径该怎么写 import。
