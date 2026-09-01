# 已知问题 / 待办

## server/tests 测试套件（2026-08-31）

### 概况

- 位置：`server/tests/`
- 类型：后端 pytest 自动化测试（非业务代码）
- 规模：43 个 `test_*.py` + `conftest.py`（夹具）+ `http_client.py`（登录 TestClient 工具）
- 前端 `web/` 无对应测试目录

### 覆盖范围

| 模块 | 代表文件 |
|---|---|
| P0 基础 | `test_auth`、`test_upload`、`test_parse_*`、`test_index`、`test_search`、`test_chat*` |
| 文档管理 | `test_document_*`、`test_url_refresh`、`test_incremental_index`、`test_tags`、`test_favorites` |
| P1 Agent | `test_p1_agent`、`test_p1_graph`、`test_p1_tools`、`test_p1_ltm`、`test_search_graph` |
| 调试/评测 | `test_rag_*`、`test_retrieval_debug`、`test_answer_quality`、`test_insights`、`test_recommendations` |

### 运行结果（2026-08-31）

```bash
cd server && .venv/bin/pytest tests/ -q
# 139 collected, 136 passed, 3 failed
```

失败用例（暂未修）：

1. `test_p1_ltm.py::test_ltm_survives_new_conversation` — `IndexError`（疑似 mock 未覆盖或行为变更）
2. `test_rerank.py::test_search_without_rerank_or_llm_key_not_500` — 无 LLM Key 时仍触发真实 API 连接（`APIConnectionError`）
3. `test_search.py::test_search_isolates_kb_tag_kind_and_skips_chat` — 隔离/跳过 chat 断言可能过时

### 结论

- **保留**：是当前功能的回归护栏，不应删除
- `conftest.py` 用独立库 `echola_kb_test`，mock embedding/ES/rerank，不污染正式数据
- P4 Master 改造时需同步更新：`test_p1_agent.py`、`test_p1_graph.py`、`test_search_graph.py`
