### ReAct Agent 能力补齐需求

当前 `graph.py` 已经是标准 LangGraph ReAct：`agent → ToolNode → agent`，并且已有 `MAX_LOOPS`、`MAX_TOOL_CALLS`、工具调用截断、citations 去重等执行预算控制。

但这些只解决了工具执行安全与预算问题，没有解决旧 ReAct 的核心缺口：

* 没有真正的结构化子问题分解；
* 检索结果没有和 Qi 对齐；
* 没有 Sufficiency 判断“证据是否足以回答”；
* 没有基于缺口的 Query Rewrite；
* 多轮检索主要依赖 LLM 自由决定，容易变成重复搜索后硬停。

**目标：保留 `graph.py` 的标准 ReAct 形态，不要直接改造成 `knowledge_flow` 固定 DAG，也不要复制一套完整 Workflow。**

请基于现有实现，设计一个轻量的 ReAct 检索控制增强层：

1. **Complexity / Decompose**

   * 简单问题允许直接检索；
   * 复杂问题允许生成结构化 `sub_questions[]`；
   * Qi 应有稳定 ID、问题文本、状态；
   * 不要求每次 ReAct 都强制分解。

2. **Qi-aware Retrieval**

   * 检索过程应能记录当前 Query 对应的 Qi；
   * 证据进入统一 Evidence Pool，而不是只在 messages 中平铺堆积；
   * 尽量复用现有 RAG、RRF、Rerank、Tool Schema，不改动 P0 旧 `/api/chat` 路径。

3. **Sufficiency**

   * 先实现低成本 V0/V0.5 规则判断；
   * 至少区分“有命中”和“证据是否达到最低要求”，不要把 `len(hits)>0` 直接等同于完整回答；
   * 为后续 LLM Sufficiency V1 预留结构化接口。

4. **Rewrite**

   * 仅在当前 Qi 证据不足时触发；
   * Rewrite 应基于缺失方面生成，而不是无条件重复搜索；
   * 每个 Qi 和整个 ReAct 都要有明确补搜预算。

5. **Agent 决策**

   * 保留 ReAct 的自主性：Agent 可以继续检索、改写 Query、切换工具或结束；
   * 不要把所有步骤强制写成固定 DAG；
   * Sufficiency / Evidence 状态应成为 Agent 决策依据，而不是仅依赖原始 Tool Observation。

6. **边界**

   * `knowledge_flow.py` 继续作为结构化知识检索工作流；
   * `graph.py` 是自主工具使用 Agent；
   * 两者共享底层检索、Rerank、Evidence 处理能力，避免重复实现；
   * 先给出最小改造方案、State 变化、节点/工具职责和数据流，再编码。

**重点验收：**

> 对“Kafka Rebalance 时为什么消费会停？怎么排查？”这类复合问题，ReAct 不应只是连续调用 3 次搜索后硬停，而应能识别多个回答方面，记录各 Qi 的证据覆盖情况，在不足时进行针对性补搜，并在证据不足时保留缺口信息。

