flyai Skill 参考（src/main/resources/skills/flyai/）
是什么：FlyAI——通过 flyai-cli（npm 包）调用飞猪（Fliggy）MCP 的机票/火车/景点搜索工具。README 里定位为机票搜索的备用数据源（tuniu → flight-manager → flyai 兜底链最后一环），最关键特性：免 API Key 即可试用（trial 模式），这就是阶段 2 行程规划能零 Key 走通的原因。

目录结构：


text
skills/flyai/
├── SKILL.md                        主说明（129 行）
└── references/                     每个子命令一份参数文档
    ├── keyword-search.md           一句话搜酒店/机票/门票/演出/赛事
    ├── ai-search.md                语义搜索（理解复杂意图）
    ├── search-flight.md            结构化机票搜索（深度比价用）
    ├── search-train.md             结构化火车票搜索
    └── search-poi.md               结构化景点搜索
运行要求：npm i -g @fly-ai/flyai-cli（依赖 node），命令输出单行 JSON 到 stdout、错误走 stderr。SKILL.md 明确要求调用前先读对应 reference 文档，不要凭其他命令的参数格式猜



##  Agent / RAG 调用关系

```text
用户（task=agent | report）
        │
        ▼
LangGraph
        │
        ▼
reason          ← 只做 LLM 决策（要不要搜、搜什么）；禁止在本节点执行 Tool
        │
        │ 决定：search_knowledge
        ▼
run_tool        ← 只执行 Tool
        │
        ▼
search_knowledge Tool
        │  禁止 HTTP
        ▼
search.py 函数
        │
        ▼
document_chunk + pgvector 余弦（库/标签/kind、阈值 0.30）
        │
        ▼
hits → State.citations
        │
        ├─ loop_count < 3 且 reason 还要搜 ─► 再进入 reason（Conditional Edge）
        ├─ loop_count >= 3 或已够用 ─► generate
        ▼
generate（task=agent 问答 或 task=report 成文）
        │
        ▼
SSE  POST /api/agent/stream（不经过 /api/chat/stream）
```

职责拆开（面试可按此说）：**reason 决策，run_tool 执行，Conditional Edge 控制是否继续循环。** Tool 只调 P0 检索函数，不走 HTTP。

**Research Report：** 仍走这张图。`task=report` 时 generate 侧按报告组织（可先大纲再写），**不新开 Graph、不新开 Agent 进程。**

图谱查询：**第一阶段不是 Tool。** P1.4 落库后，后续阶段才可加 `search_graph` Tool。

---

## 6. LangGraph 第一阶段（P1.3 才引入，不在 P1.1）

**State：** `knowledge_base_id`、`task`（`agent` \| `report`）、`messages`、`citations`、`loop_count`、`max_loops=3`。报告需要时加 `outline`。

**Node：** `reason`（只决策，不执行 Tool）、`run_tool`（只执行 Tool）、`generate`。

**Tool：** 至少 `search_knowledge`（强制）；摘要/对比 Chain 做成 Tool 可放在 P1.3，不提前 Graph 化 Chain 本身。

**Conditional Edge：** 继续搜 vs 生成。

**Loop：** `loop_count` 自增；`>= max_loops` 必须进入 `generate`。

**Streaming：** `POST /api/agent/stream`，event 尽量与 P0 引用字段对齐，便于前端点进阅读页。

**不做：** Checkpoint、HITL、Subgraph、Multi-Agent。


 Hybrid Search **不能只服务 Agent**，不要为 Agent 另写一套检索。

```text
Chat / 搜索页 / Agent search_knowledge
        │
        ▼
统一入口 search_chunks（内部流水线，调用方不变）
        │
        ├─ Vector Search（现有 pgvector 余弦）
        └─ Keyword Search（Elasticsearch BM25）
        │
        ▼
       RRF
        │
        ▼
     Rerank（分阶段，见 §3）
        │
        ▼
    相关性判断（分阶段，见 §3）
        │
        ▼
   返回最终检索结果
```


### 轻量 Task Planning（P2-Agent-6）

在的三种路由之上增加：复杂问句可先写入最多 3 条有序子任务。随后每一圈仍由**同一个** `reason` 只选 DIRECT / RAG / WEB 执行当前子任务，最后 generate 汇总。

```text
reason
  ├── DIRECT
  ├── RAG
  ├── WEB
  └── （仅首圈可写入）≤3 条子任务，不是子图、不是动态 DAG
```

不实现复杂 Planner、Multi-Agent、第二张 Graph。`max_loops=3` **保持不变**。子任务数量必须能在 3 圈内跑完。