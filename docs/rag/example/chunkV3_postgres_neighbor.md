## PostgreSQL 实践笔记

### B-Tree 索引

PostgreSQL 默认索引类型是 B-Tree。等值查询（`WHERE id = 1`）和范围查询（`WHERE created_at >= ...`）通常都能很好利用它。复合索引遵循最左前缀：`(tenant_id, created_at)` 可以加速按租户过滤再按时间排序，但不能单独高效服务「只按 created_at」的条件。

唯一约束与主键底层也是 B-Tree。高基数列更适合做索引前导列；低基数列（如布尔）单独建索引收益往往很小，可考虑与高基数列组成复合索引，或改用部分索引（`WHERE status = 'active'`）缩小体积。

用 `EXPLAIN (ANALYZE, BUFFERS)` 看是否 Index Scan / Index Only Scan。若出现 Seq Scan 且代价更低，不一定是缺索引——表很小或选择性差时顺序扫可能更快。注意 `work_mem` 过小会导致排序/哈希溢出到磁盘，表现为额外临时文件 I/O。

### 向量检索与 pgvector

`pgvector` 在 PostgreSQL 内提供 `vector` 类型与距离运算符。常见距离：`<=>` 余弦距离、`<->` L2、`<#>` 内积（负内积）。检索流水线一般是：Embedding 模型把查询编成向量，再在库内做近邻搜索。

小数据量可用精确搜：`ORDER BY embedding <=> $1 LIMIT k`。数据变大后建近似索引：`ivfflat`（需先 `ANALYZE`，并设 `lists`）或 `hnsw`（构建更慢、查询通常更稳）。`ivfflat` 查询前可调 `ivfflat.probes`；`hnsw` 可调 `hnsw.ef_search`。召回率与延迟要按业务压测，不要照搬默认值。

混合检索常见做法：先用 BM25/关键词（或业务过滤）缩小候选，再对候选做向量重排；或向量召回后再用元数据过滤。过滤条件尽量能下推到索引扫描阶段，避免「先取大量近邻再丢掉」。余弦相似度与余弦距离不要混用：距离越小越近，相似度通常是 `1 - distance`（取决于具体定义）。

### MVCC、VACUUM 与膨胀

PostgreSQL 用 MVCC：更新/删除会留下旧版本行（dead tuples）。长时间未提交的事务会阻止清理，导致表膨胀、索引变大、查询变慢。常规运维依赖 autovacuum；大表或突发写入后可手动 `VACUUM (VERBOSE, ANALYZE)`，极端膨胀再考虑 `VACUUM FULL`（会排他锁，慎用）。

观察手段：`pg_stat_user_tables` 的 `n_dead_tup`、`last_autovacuum`；`pg_stat_activity` 里过老的 `xact_start`。复制槽（replication slot）若长期落后，也会拖住 xmin horizon，使 VACUUM 无法回收。连接池要避免「空闲会话长期挂着未结束事务」。

### 连接、事务与锁

短事务优于长事务：尽快提交或回滚，减少锁持有时间。`SELECT ... FOR UPDATE` 会行锁；分析锁等待可用 `pg_locks` 与 `pg_stat_activity` 关联。死锁时 PostgreSQL 会取消其中一方事务并报错，应用需可重试。

连接数有上限（`max_connections`）。应用侧用连接池（PgBouncer 或驱动池），区分事务池与会话池模式。避免在事务里做远程 HTTP 等不可控耗时操作。只读报表可走只读副本，但要注意复制延迟下的读己之写问题。

### 备份与升级要点

逻辑备份用 `pg_dump` / `pg_dumpall`；物理备份与 PITR 用 `pg_basebackup` 加 WAL 归档。恢复演练比「有备份」更重要。大版本升级可走 `pg_upgrade` 或逻辑迁移；扩展（含 pgvector）需确认目标大版本兼容后再升。

参数调优优先保证：数据校验和（`data_checksums`）、合理的 `shared_buffers`、足够的磁盘与监控（缓存命中、临时文件、锁等待、autovacuum 是否跟得上）。先定位慢查询与膨胀，再谈微调 planner 相关参数。
