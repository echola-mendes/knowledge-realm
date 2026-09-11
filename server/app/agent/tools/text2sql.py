from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agent.text2sql import text2sql as run_text2sql
from app.agent.tools._context import tool_runtime
from app.agent.tools.formatters import format_sql_result


def text2sql(
    session: Session,
    question: str,
    user_id: uuid.UUID,
    *,
    sql: str | None = None,
) -> dict[str, Any]:
    """自然语言查询 customers/products/orders/order_items（仅 SELECT）。"""
    return run_text2sql(session, question, user_id, sql=sql)


@tool("text2sql")
def text2sql_tool(question: str, config: RunnableConfig) -> str:
    """仅用于结构化业务数据查询（如商品、订单等表；Text2SQL，只读 SELECT）。

    不要用于知识库文档问答或互联网检索；那些应使用 search_knowledge / search_graph / web_search。

    Args:
        question: 面向结构化表的自然语言问题
    """
    import json

    session, user_id, _, _ = tool_runtime(config)
    if session is None or user_id is None:
        return json.dumps({"text": "查询失败：缺少运行时上下文。", "citations": []}, ensure_ascii=False)
    return json.dumps(
        {"text": format_sql_result(text2sql(session, question, user_id)), "citations": []},
        ensure_ascii=False,
    )
