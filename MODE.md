请在当前项目中增加一个「Retrieval Debug Mode」，用于调试和评估当前 RAG Hybrid Search 检索链路。

注意：

1. 当前已有一级 Tab：
   - Chat
   - Agent
   - Report

不要新增一级 Tab，暂时不要改变现有的信息架构。

2. Debug Mode 应作为开发者调试功能，通过右上角的 Debug 开关开启/关闭。

3. Debug Mode 开启后，不要跳转到新的页面。
   在当前 Chat / Agent 页面中增加一个 Retrieval Debug Drawer / Side Panel。
   默认可以折叠，点击「Retrieval Debug」后展开。

4. Debug Panel 用于完整展示当前 Query 的检索过程：

   Query
      ↓
   Vector Search
      ↓
   BM25 / ES Search
      ↓
   RRF
      ↓
   Rerank
      ↓
   Final TopK

5. 增加可调检索参数：

   - Vector TopK
   - Vector Similarity Threshold
   - BM25 TopK
   - RRF TopK
   - Rerank TopK
   - Evaluation K
   - RRF rank constant（如果当前实现支持）

   参数修改后可以点击「重新检索」重新执行当前 Query。

6. Vector Search 区域展示：

   - Requested TopK
   - Similarity Threshold
   - Actual Returned Count
   - 每条文档：
     - Vector Rank
     - Vector Similarity Score
     - Document ID
     - Document Title

7. BM25 / ES 区域展示：

   - Requested TopK
   - Actual Returned Count
   - 每条文档：
     - BM25 Rank
     - BM25 Score
     - Document ID
     - Document Title

8. RRF 区域展示：

   - Candidate Count
   - RRF TopK
   - 每条文档：
     - RRF Rank
     - RRF Score
     - Vector Rank
     - BM25 Rank
     - Document ID
     - Document Title

   支持点击某条记录查看 RRF Score 的计算过程。

9. Rerank 区域展示：

   - Rerank Model
   - Rerank TopK
   - 每条文档：
     - Rerank Rank
     - Rerank Score
     - Document ID
     - Document Title

10. 最终增加一个统一的 Candidates Table：

   Rank
   Document
   Vector Rank
   Vector Score
   BM25 Rank
   BM25 Score
   RRF Rank
   RRF Score
   Rerank Rank
   Rerank Score
   Final

11. 增加人工 Ground Truth 标注能力。

   每条文档支持：
   - Relevant
   - Not Relevant

   如果当前系统支持三级相关性，则支持：
   - 0 = Not Relevant
   - 1 = Partially Relevant
   - 2 = Relevant
   - 3 = Highly Relevant

   Ground Truth 必须持久化，后续可以用于评测。

12. 增加 Evaluation 区域：

   - Evaluation K 可配置
   - Recall@K
   - Precision@K

   计算必须基于 Ground Truth，不允许根据 Vector Score、BM25 Score 或 RRF Score 推断文档是否正确。

13. 特别注意：

   Similarity、BM25 Score、RRF Score、Rerank Score 是不同体系的分数，不要在 UI 中直接进行横向比较。

14. Debug Mode OFF 时：

   - 不影响当前 Chat / Agent / Report UI
   - 不展示检索内部 score
   - 不展示 Ground Truth
   - 不影响现有正常聊天流程

15. Debug Mode ON 时：

   必须能够完整追踪一次 Query：

   Query
   → Vector TopK
   → BM25 TopK
   → RRF
   → Rerank
   → Final TopK
   → Ground Truth
   → Recall@K / Precision@K

请根据现有 Python Web 框架（优先复用当前项目的 Pydantic Schema / response model）增加 RetrievalDebugResponse。不要修改现有 Chat/Agent/Report 的正常返回结构。Debug API 单独返回 Vector、BM25、RRF、Rerank 各阶段的 Rank/Score，以及最终过滤结果。

请先检查当前项目已有的前后端结构和 RAG 检索代码，
尽量复用现有 API、DTO、组件和状态管理，不要重复实现已有逻辑。

先给出改造方案和涉及的文件列表，再开始修改代码。