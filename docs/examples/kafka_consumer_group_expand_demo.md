## Kafka Consumer Group

【标记:CHUNK1】【主题:Kafka Consumer Group 导言】
Kafka Consumer Group 是消费侧的核心抽象：同一 group.id 下的多个 Consumer 共同订阅 Topic，
每个 Partition 同一时刻只被组内一个成员消费。Coordinator 负责成员管理、位移提交与故障转移。
若 Group 设计不当，会出现重复消费、消费停滞或热点分区。先建立「组 + 分区所有权」心智模型，再谈调参。
补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK1）：在真实集群里请结合监控与日志交叉验证上述

### Partition 分配

【标记:CHUNK2】【主题:Partition 分配】
一个 Consumer Group 中，Partition 分配决定谁读哪些分区。常见策略有 Range、RoundRobin、Sticky、CooperativeSticky。
Sticky / Cooperative 尽量在 Rebalance 时保留旧分配，降低停顿。Consumer 数大于 Partition 数时会有空闲实例；
单分区内保序，跨分区聚合需接受乱序或自行排序。
补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK2）：在真实集群里请结合监控与日志交叉验证上述

【标记:CHUNK3】【主题:Partition 实践要点】
实践上要盯 assignment 是否符合预期，避免在 poll 循环里做重阻塞导致会话超时。
关键链路应异步化或限时；位移提交策略（自动/手动）要与业务确认语义一致。
用管理员工具或 consumer.assignment() 核对分区归属，是排查「有的实例吃不到活」的第一步。
补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK3）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。

### Rebalance

【标记:CHUNK4】【主题:Rebalance 机制】
当 Consumer 加入或退出、订阅变更或会话超时，Group 会 Rebalance：回收分区再重新分配。
窗口期内消费暂停；处理不当会重复消费或长时间停顿。协作式再均衡只动变更分区，优于一次性全量回收。
日志中的 Preparing to rebalance / Member leaving 是直接线索。
补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK4）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 

【标记:CHUNK5】【主题:Rebalance 排查】
排查优先核对 session.timeout.ms、max.poll.interval.ms、heartbeat.interval.ms，以及 poll 间隔是否被业务拖长。
稳定 Group 通常来自：合理超时、消费幂等、Sticky/Cooperative 降抖动，并为突发扩缩容预留余量。
把「再均衡频率」纳入告警，往往比事后翻日志更快定位。
补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consumer Lag、Coordinator 事件与业务幂等日志应一起看。补充说明（CHUNK5）：在真实集群里请结合监控与日志交叉验证上述结论；不要只看单一指标。Consume
