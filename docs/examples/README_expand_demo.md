# 同节扩窗验证示例

文件：[`kafka_consumer_group_expand_demo.md`](kafka_consumer_group_expand_demo.md)

默认切块：`chunk_size=800`，`overlap=120`。

结构：`## Kafka Consumer Group` + `### Partition 分配` + `### Rebalance`。
因 heading 取最浅级标题，子节 child 的 `heading` 仍是 `Kafka Consumer Group`，适合验 V0 同节扩窗。

## 预期切块（本机预览 5 块）

| 切片 | 长度 | 文内标记 |
| --- | --- | --- |
| Chunk 1 | 786 | `CHUNK1` |
| Chunk 2 | 779 | `CHUNK2` |
| Chunk 3 | 760 | `CHUNK3` |
| Chunk 4 | 775 | `CHUNK4` |
| Chunk 5 | 760 | `CHUNK5` |

## 验证步骤

1. 导入该 Markdown（笔记/上传），等待索引完成。
2. 文档详情确认约 5 个切片，heading 均为 `Kafka Consumer Group`。
3. 搜索：`CHUNK4 Rebalance` 或 `Preparing to rebalance`。
4. 搜索结果 `content` 应含多个 `【标记:CHUNKx】`（邻块拼入，预算 4000 内）。
5. 检索调试同一 query：final 仍为单 child。
