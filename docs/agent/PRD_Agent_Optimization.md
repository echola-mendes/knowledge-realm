可以。下面我按**“直接交给 Cursor 执行的需求文档”**来写，不写成泛泛的 Agent 理论，而是严格基于你目前知域已经有的：

* P0 单链 RAG
* P1 Agent
* `search_chunks` Retrieval Tool
* Vector + BM25 + RRF + Rerank
* V0/V1 Context Expansion / Parent-Child
* LangGraph
* `max_loop=3`
* Agent Trace / Debug
* Citation / Knowledge Gap

并且明确**不重构现有 P0 RAG 主链路**。

你可以直接保存为：

```text
PRD-Agent-Optimization.md
```

---

# 知域 Agent 优化需求文档

## 1. 需求概述

### 1.1 需求名称

**Agentic RAG Agent 优化**

### 1.2 背景

当前知域已经具备基础 RAG 与 Agent 能力：

```text
P0 RAG
    ↓
Vector / BM25 / RRF / Rerank
    ↓
Context Expansion
    ↓
LLM Answer
```

P1 Agent 在此基础上通过 LangGraph 调用 `search_chunks` Tool，实现多轮检索。

当前 Agent 的主要流程接近：

```text
User Query
    ↓
Agent
    ↓
Reason
    ↓
search_chunks
    ↓
Reason
    ↓
search_chunks
    ↓
...
    ↓
Answer
```

目前主要存在以下问题：

1. Agent 的 `max_loop=3` 只能防止无限循环，没有真正的**证据充分性停止条件**。
2. 对包含多个问题、比较、多个知识点的问题，没有明确的**Query Decomposition**机制。
3. 检索证据不足时，没有针对具体缺失问题进行定向重检索。
4. Agent 可能重复搜索相同或高度相似的 Query。
5. 简单问题也可能进入 Agent 多轮流程，造成额外 LLM 调用、Token 和延迟。
6. 多个子问题产生的 Evidence 缺少统一的汇总、去重和组织机制。
7. 检索始终无足够证据时，需要明确输出 Knowledge Gap，而不是让 LLM 根据常识补全。
8. Agent 的检索次数、LLM 调用次数、Token、延迟等效率指标需要进一步完善。
9. 当前 Chunking 默认仍主要依赖固定切分，其他策略为占位，但本需求**不以一次性实现所有切分策略为目标**。

---

# 2. 需求目标

本次优化的核心目标：

> **让 Agent 从“循环调用 RAG Tool”升级为“根据问题结构和证据覆盖度进行检索决策的 Agent”。**

最终流程：

```text
User Query
    ↓
Agent Query Analysis
    ↓
判断 Simple / Complex
    │
    ├── Simple
    │      ↓
    │  search_chunks
    │      ↓
    │    Answer
    │
    └── Complex
           ↓
      Decomposition
           ↓
       Q1 / Q2 / Q3
           ↓
   search_chunks(Qi)
           ↓
      Evidence Pool
           ↓
   Evidence Sufficiency
       /          \
   Enough       Insufficient
      │               │
      │          Rewrite Qi
      │               │
      │       search_chunks(Qi')
      │               │
      └───────┬───────┘
              ↓
        Evidence Merge
              ↓
          Final Answer
          /          \
    Citations      Knowledge Gap
```

---

# 3. 非目标

本次优化**不做以下事情**：

### 3.1 不替换 P0 RAG

现有：

```text
search_chunks
```

继续作为统一 Retrieval Tool。

不得在 Agent 内重新实现：

* Vector Search
* BM25
* RRF
* Rerank
* Context Expansion
* Parent-Child Retrieval

Agent 只负责：

```text
query → search_chunks → hits
```

---

### 3.2 不重构现有 P0 Chat

保持现有：

```text
/api/chat
/api/chat/stream
```

语义和行为不变。

普通 RAG 不应强制进入 Agent。

---

### 3.3 不一次性实现所有 Chunking Strategy

本需求不要求本阶段完整实现：

```text
fixed
paragraph
recursive
semantic
```

其中切分策略属于独立 Retrieval / Ingestion 能力。

如果需要优化，优先级为：

```text
Recursive > Semantic
```

但不能因为本需求而大规模重构 Chunking。

---

### 3.4 不引入无限 Agent Loop

必须继续存在：

```text
MAX_LOOPS = 3
```

但它只作为**安全上限**，不能作为唯一停止条件。

---

### 3.5 不增加 Multi-Agent

本阶段不因为 Agent 优化而增加新的 Agent：

```text
Planner Agent
Retriever Agent
Reviewer Agent
Writer Agent
```

先把单 Agent 的闭环做好。

---

# 4. Agent 总体架构

优化后的 Agent：

```text
                         User Query
                             │
                             ▼
                    ┌─────────────────┐
                    │  Query Analysis │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
                 Simple            Complex
                    │                 │
                    │          Decomposition
                    │                 │
                    │          ┌──────┼──────┐
                    │          ▼      ▼      ▼
                    │         Q1     Q2     Q3
                    │          │      │      │
                    │          ▼      ▼      ▼
                    │       search_chunks
                    │          │      │
                    │          └──┬───┘
                    │             ▼
                    │       Evidence Pool
                    │             │
                    │             ▼
                    │      Evidence Sufficiency
                    │          /          \
                    │       enough      insufficient
                    │          │             │
                    │          │        Rewrite Qi
                    │          │             │
                    │          │       search_chunks
                    │          │             │
                    └──────────┴─────────────┘
                               │
                               ▼
                         Evidence Merge
                               │
                               ▼
                         Final Answer
                          /         \
                     Citation    Knowledge Gap
```

---

# 5. 功能需求

## 5.1 Query Analysis

### 需求

Agent 首先判断当前 Query 是否需要复杂 Agent 流程。

至少区分：

```text
SIMPLE
COMPLEX
```

### SIMPLE

典型：

```text
Kafka 是什么？
什么是 MVCC？
PostgreSQL 默认端口是多少？
```

处理：

```text
Query
 ↓
search_chunks
 ↓
Answer
```

不进行 Decomposition。

---

### COMPLEX

典型：

```text
Kafka 为什么能够保证 Partition 内消息顺序？
```

或者：

```text
比较 Kafka 和 RabbitMQ 的消息模型、
消费模式、顺序保证和适用场景。
```

或者：

```text
什么是 MVCC？它解决什么问题？
MySQL 和 PostgreSQL 分别如何实现？
```

进入：

```text
Decomposition
```

---

## 5.2 Query Decomposition

### 需求

对于 Complex Query，将用户问题拆分为若干独立的 Sub Question。

示例：

```text
用户：
比较 Kafka 和 RabbitMQ 的消息模型、
消费模式、顺序保证和适用场景。
```

拆分：

```text
Q1：Kafka 的消息模型是什么？
Q2：RabbitMQ 的消息模型是什么？
Q3：Kafka 和 RabbitMQ 的消费模式有什么区别？
Q4：两者如何保证消息顺序？
Q5：两者分别适合什么场景？
```

### 限制

默认：

```text
MAX_SUB_QUESTIONS = 5
```

建议实际控制在：

```text
1 ~ 5
```

避免过度拆解。

### 要求

Sub Question 必须：

* 与原始 Query 有明确关联
* 尽可能可以独立检索
* 避免重复
* 避免产生没有实际回答价值的子问题

---

# 6. Retrieval Tool

Agent 所有知识库检索统一使用：

```text
search_chunks
```

Agent 不允许直接操作：

```text
Vector DB
Elasticsearch
pgvector
BM25
RRF
Rerank
document_chunk
```

### Tool 内部保持现有流程：

```text
search_chunks(query)
       ↓
Vector Search
       +
BM25
       ↓
RRF
       ↓
Rerank
       ↓
Context Expansion / Parent-Child
       ↓
Hits
```

Agent 只接收最终结果。

---

# 7. Sub Question Retrieval

对于：

```text
Q1
Q2
Q3
```

分别调用：

```text
search_chunks(Q1)
search_chunks(Q2)
search_chunks(Q3)
```

每个 Sub Question 必须记录自己的 Evidence。

例如：

```text
Q1
 └── evidence_ids = [12, 15]

Q2
 └── evidence_ids = [18, 21]

Q3
 └── evidence_ids = [15, 25]
```

允许不同 Q 共享同一个 Evidence。

---

# 8. Evidence Sufficiency

## 8.1 需求

增加真正的证据停止条件。

当前：

```text
MAX_LOOPS = 3
```

不能继续作为唯一停止依据。

增加：

```text
Evidence Sufficiency
```

判断当前 Evidence 是否足够回答：

```text
Original Query
```

以及：

```text
Sub Questions
```

---

## 8.2 判断结果

每个 Sub Question 至少有：

```text
SUFFICIENT
INSUFFICIENT
```

例如：

```text
Q1 → SUFFICIENT
Q2 → SUFFICIENT
Q3 → INSUFFICIENT
Q4 → SUFFICIENT
```

Agent 只处理：

```text
Q3
```

而不是重新搜索 Q1/Q2/Q4。

---

# 9. Evidence Sufficiency 与 Relevance 的区别

不得简单使用：

```text
score > threshold
```

作为 Evidence Sufficiency。

因为：

```text
相关 ≠ 足够回答
```

例如：

```text
Query：
Kafka Consumer Group 如何实现负载均衡？
```

检索结果：

```text
Chunk A：
Consumer Group 定义

Chunk B：
Consumer Group 可以包含多个 Consumer
```

两个 Chunk 都高度相关。

但可能仍然缺少：

```text
Partition Assignment
Rebalance
```

因此：

```text
Relevance = TRUE
Evidence Sufficiency = FALSE
```

---

# 10. Query Rewrite

当：

```text
Evidence Sufficiency = INSUFFICIENT
```

Agent 应针对具体 Sub Question 进行 Query Rewrite。

例如：

```text
原始：
Kafka 为什么保证消息顺序？

Rewrite：
Kafka partition message ordering guarantee

或者：

Kafka partition offset ordering producer consumer
```

然后：

```text
search_chunks(rewritten_query)
```

---

## 10.1 Rewrite 要求

Rewrite：

* 必须针对当前缺失的 Sub Question
* 不得修改用户原始意图
* 避免重复已有 Query
* 不允许无限 Rewrite

建议：

```text
MAX_REWRITE_PER_SUBQUESTION = 2
```

---

# 11. 防止重复检索

Agent State 增加：

```text
searched_queries
```

例如：

```text
searched_queries = [
    "Kafka Consumer Group",
    "Kafka consumer group partition allocation"
]
```

新 Query 如果与已搜索 Query 完全相同，不得再次调用 Tool。

如果实现成本允许，可以进一步做简单语义去重，但第一版不要求增加 Embedding。

---

# 12. Loop 控制

保留：

```text
MAX_LOOPS = 3
```

但定义修改为：

> Agent 最大允许进行 3 轮补充检索，用于防止异常情况下的循环。

正常停止条件：

```text
所有 Sub Questions = SUFFICIENT
```

强制停止条件：

```text
loop_count >= MAX_LOOPS
```

因此：

```text
Evidence Sufficient
        ↓
正常停止

Evidence Insufficient
        ↓
Rewrite
        ↓
Retry

loop >= 3
        ↓
强制停止
```

---

# 13. Evidence Merge

多个 Sub Question 的检索结果进入统一 Evidence Pool。

例如：

```text
Q1 → A B
Q2 → B C
Q3 → D E
```

Merge：

```text
A
B
C
D
E
```

而不是：

```text
A B B C D E
```

---

## 13.1 Merge 要求

至少实现：

### 去重

相同：

```text
document_id + chunk_id
```

只保留一份。

### 保留最高分

重复 Evidence：

```text
Q1 → chunk 20 score 0.82
Q2 → chunk 20 score 0.91
```

保留：

```text
chunk 20 score 0.91
```

### 保留 Sub Question 关联

即使 Evidence 被全局去重，也要知道：

```text
chunk 20
related_questions = [Q1, Q2]
```

这样最终回答阶段可以正确组织内容。

---

# 14. Evidence Context Budget

Evidence Merge 后不得无限塞入 LLM Context。

继续使用现有 Context Expansion 的限制策略。

要求：

```text
Evidence Pool
 ↓
Dedup
 ↓
Rank
 ↓
Context Budget
 ↓
LLM
```

第一阶段可以继续使用字符限制。

后续可以升级为：

```text
MAX_EVIDENCE_TOKENS
```

暂时不要求引入 tokenizer。

---

# 15. Knowledge Gap

当：

```text
MAX_LOOPS reached
```

但仍然：

```text
Q3 = INSUFFICIENT
```

Agent 不得根据模型自身常识强行补全。

应该生成：

```text
Knowledge Gap
```

例如：

```text
知识库已找到：

✓ Kafka Consumer Group 定义
✓ Consumer 与 Partition 的关系

知识库缺少：

✗ Rebalance 的具体执行机制
```

最终回答必须明确区分：

```text
有知识库证据
```

和：

```text
知识库没有足够证据
```

---

# 16. Citation

最终回答中的 Citation 必须来自实际 Evidence。

要求：

```text
Final Answer
    ↓
Citation
    ↓
Original Child / Document Chunk
```

即使：

```text
Context Expansion
Parent
Section
```

被用于生成，也不能丢失原始 Citation 来源。

不得生成没有对应 Evidence 的 Citation。

---

# 17. Agent State

建议 Agent State 最小增加/整理为：

```text
query
query_type
sub_questions
evidence
searched_queries
loop_count
max_loops
knowledge_gaps
final_answer
```

其中：

### sub_questions

```text
[
  {
    id,
    question,
    status,
    rewrite_count,
    evidence_ids
  }
]
```

### evidence

```text
[
  {
    id,
    document_id,
    chunk_id,
    score,
    content,
    related_questions
  }
]
```

不允许把每轮完整 Tool Result 无限累积到 State。

---

# 18. Agent 流程

最终 LangGraph 流程建议：

```text
START
  ↓
analyze_query
  ↓
┌────────────────────┐
│ Simple / Complex   │
└─────────┬──────────┘
          │
     ┌────┴────┐
     ▼         ▼
  Simple    Complex
     │         │
     │    decompose
     │         │
     │    retrieve_subquestions
     │         │
     │         ▼
     │   evidence_check
     │         │
     │     ┌───┴────┐
     │     ▼        ▼
     │  enough   insufficient
     │     │        │
     │     │     rewrite
     │     │        │
     │     │     retrieve
     │     │        │
     │     └────┬───┘
     │          │
     └──────────┤
                ▼
          evidence_merge
                │
          ┌─────┴─────┐
          ▼           ▼
       Answer      Knowledge Gap
```

---

# 19. Chunking 优化

本需求不要求完整实现所有 Chunking Strategy。

当前：

```text
Fixed
Paragraph
Recursive
Semantic
```

其中：

```text
Fixed = 当前实现
Paragraph = 占位
Recursive = 占位
Semantic = 占位
```

建议下一阶段优先：

```text
Recursive
```

原因：

> Recursive Chunking 可以在固定大小约束下优先保留标题、段落、换行等自然边界，比单纯固定长度切分更适合作为通用默认策略。

暂时不要求 Semantic Chunking。

---

# 20. Chunking 与 Context Expansion 的职责边界

必须保持：

```text
Chunking Strategy
```

负责：

> **如何把 Document 切成 Child Chunk。**

而：

```text
Context Expansion
```

负责：

> **检索命中后提供多少上下文。**

两者不得合并成一个配置。

例如：

```text
Chunking
├── Fixed
├── Recursive
├── Paragraph
└── Semantic

Context Expansion
├── Child Only
├── Section
└── Parent
```

---

# 21. Agent 路由

建议增加简单的：

```text
Simple / Complex
```

路由。

但是：

**不要为了实现 Router 而新增一个独立 LLM Agent。**

可以使用：

* LLM Structured Output
* 简单规则
* 或现有 Agent Node

具体实现由代码现状决定。

---

# 22. 评估指标

本次优化必须增加 Agent 层评估维度。

## Retrieval

继续：

```text
Recall@K
Precision@K
MRR / NDCG
RRF
Rerank
```

---

## Answer

继续：

```text
Answer Correctness
Faithfulness
Answer Relevance
Citation Correctness
```

---

## Agent

新增：

```text
Decomposition Success
Evidence Sufficiency Accuracy
Knowledge Gap Accuracy
Search Calls
Rewrite Calls
LLM Calls
Total Tokens
Latency
```

重点关注：

```text
Answer Quality
+
Retrieval Quality
+
Agent Efficiency
```

---

# 23. Agent Trace

Debug / Trace 中建议能看到：

```text
User Query
    ↓
Query Type
    ↓
Sub Questions
    ↓
Q1 → search_chunks
    ↓
Q2 → search_chunks
    ↓
Q3 → search_chunks
    ↓
Evidence Sufficiency
    ↓
Q3 insufficient
    ↓
Query Rewrite
    ↓
Q3' → search_chunks
    ↓
Evidence Sufficiency
    ↓
Sufficient
    ↓
Evidence Merge
    ↓
Final Answer
```

重点展示：

```text
Loop Count
Tool Calls
Rewrite Count
Sub Question Status
Knowledge Gap
Token Usage
Latency
```

---

# 24. Debug 数据口径

必须保持：

```text
search_debug
```

只用于评估 Retrieval 本身。

因此：

```text
search_debug
```

**不得因为 Agent Context Expansion 而改变 Recall / Precision 的标注口径。**

即：

```text
Retrieval Evaluation
        ↓
Child Hits
```

而：

```text
Generation Context
        ↓
Expanded / Parent Context
```

两者分离。

---

# 25. 性能与成本要求

### 简单问题

目标：

```text
1 × search_chunks
```

尽量不产生额外 Agent Loop。

### 普通复杂问题

目标：

```text
Decomposition
+
N × search_chunks
```

### 补充检索

最多：

```text
MAX_LOOPS = 3
```

同时：

```text
MAX_REWRITE_PER_SUBQUESTION = 2
```

防止异常情况下 Token 和延迟失控。

---

# 26. 异常处理

### Decomposition 失败

降级：

```text
Original Query
 ↓
search_chunks
 ↓
Answer
```

---

### Retrieval 失败

不要让 Agent 崩溃。

记录：

```text
Tool Error
```

并进入：

```text
Knowledge Gap / Graceful Failure
```

---

### Evidence Sufficiency 失败

如果判断节点异常：

```text
不允许无限重试
```

使用：

```text
MAX_LOOPS
```

进行保护。

---

### LLM Structured Output 解析失败

允许有限重试：

```text
MAX_PARSE_RETRY = 1
```

超过后采用安全降级。

---

# 27. 验收标准

## AC-01 简单问题

输入：

```text
Kafka 是什么？
```

要求：

```text
不进行 Decomposition
search_chunks = 1
正常生成答案
```

---

## AC-02 多问题

输入：

```text
Kafka 的消息模型、消费模式和顺序保证分别是什么？
```

要求：

```text
生成多个 Sub Questions
每个 Sub Question 独立检索
最终统一回答
```

---

## AC-03 部分证据不足

输入一个需要三个知识点的问题。

模拟：

```text
Q1 ✓
Q2 ✓
Q3 ✗
```

要求：

```text
只 Rewrite Q3
```

不得重新搜索 Q1/Q2。

---

## AC-04 Evidence Sufficiency

要求：

```text
Evidence 足够
→ 直接 Answer
```

不能因为：

```text
loop_count < 3
```

继续无意义检索。

---

## AC-05 Loop Limit

当始终：

```text
Evidence insufficient
```

要求：

```text
loop_count >= 3
→ 停止
→ Knowledge Gap
```

不得无限循环。

---

## AC-06 重复 Query

如果 Agent 已搜索：

```text
Kafka Consumer Group
```

不得再次完全相同搜索。

---

## AC-07 Evidence Dedup

如果：

```text
Q1 → Chunk A
Q2 → Chunk A
```

最终 Evidence Pool：

```text
Chunk A
```

只能保留一份，但：

```text
related_questions = [Q1, Q2]
```

---

## AC-08 Citation

最终回答的 Citation 必须能够追溯到实际 Retrieval Evidence。

---

## AC-09 P0 不受影响

验证：

```text
/api/chat
/api/chat/stream
```

原有行为保持不变。

---

## AC-10 Retrieval Debug 不污染

`search_debug`：

```text
Vector
BM25
RRF
Rerank
```

仍然展示原始 Child Retrieval 结果。

不因为 Agent Context Expansion 修改 Recall / Precision 评估口径。

---

# 28. 推荐实施顺序

不要一次全部实现。

### Phase 1：Evidence Sufficiency

```text
search
 ↓
evidence check
 ↓
enough / insufficient
```

同时保留：

```text
MAX_LOOPS = 3
```

---

### Phase 2：Query Decomposition

```text
Complex Query
 ↓
Q1 Q2 Q3
 ↓
search_chunks(Qi)
```

---

### Phase 3：定向 Query Rewrite

```text
Qi insufficient
 ↓
Rewrite Qi
 ↓
search_chunks(Qi')
```

---

### Phase 4：Evidence Merge

```text
Q1 evidence
Q2 evidence
Q3 evidence
 ↓
Dedup
 ↓
Group
 ↓
Rank
```

---

### Phase 5：Knowledge Gap

```text
仍然 insufficient
 ↓
Knowledge Gap
```

---

### Phase 6：Simple / Complex Routing

```text
Simple → P0 Retrieval
Complex → Agent
```

---

### Phase 7：Agent Evaluation

增加：

```text
Search Calls
LLM Calls
Token
Latency
Decomposition
Evidence Sufficiency
Knowledge Gap
```

---

### Phase 8：Recursive Chunking

最后再处理：

```text
Fixed
 ↓
Recursive
```

Semantic Chunking 暂不作为本阶段必做项。

---

# 29. 技术约束

1. **P0 RAG 与 P1 Agent 解耦。**
2. `search_chunks` 是唯一知识库 Retrieval Tool。
3. Agent 不实现 Vector / BM25 / RRF / Rerank。
4. Context Expansion 保持在 Retrieval 层。
5. Parent-Child 保持在 Retrieval / Context 层。
6. `MAX_LOOPS=3` 保留。
7. Evidence Sufficiency 才是正常停止条件。
8. Sub Question 独立维护 Evidence。
9. Rewrite 只针对不足的 Sub Question。
10. 禁止重复 Query。
11. Knowledge Gap 必须阻止无证据幻觉。
12. 不为了本需求引入 Multi-Agent。
13. 不破坏现有 API。
14. 不修改 Debug Retrieval 的评估口径。
15. State 保持精简，不无限保存历史 Tool Result。

---

# 30. 最终目标

本次优化完成后，知域 Agent 应从：

```text
User
 ↓
Agent
 ↓
search
 ↓
search
 ↓
search
 ↓
Answer
```

升级为：

```text
                 User
                  │
                  ▼
             Query Analysis
                  │
           ┌──────┴──────┐
           ▼             ▼
        Simple         Complex
           │             │
           │       Decomposition
           │             │
           │        Q1 Q2 Q3
           │             │
           │             ▼
           │      search_chunks
           │             │
           │             ▼
           │       Evidence Pool
           │             │
           │             ▼
           │    Evidence Sufficiency
           │         /        \
           │      enough     missing
           │        │           │
           │        │       Rewrite Qi
           │        │           │
           │        │      search_chunks
           │        │           │
           └────────┴───────────┘
                    │
                    ▼
              Evidence Merge
                    │
                    ▼
               Final Answer
                /        \
          Citations    Knowledge Gap
```

**核心原则：**

> **Agent 负责决策与编排，`search_chunks` 负责检索，Evidence Sufficiency 负责决定是否继续，Knowledge Gap 负责防止无证据硬答。**

不用一次性改完全部 Phase**。尤其是 Phase 1 的 Evidence Sufficiency 和 Phase 2 的 Decomposition 应该先单独落地和测试。
