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
    """查询商品、订单等结构化业务数据（Text2SQL）。

    Args:
        question: 自然语言问题
    """
    import json

    session, user_id, _, _ = tool_runtime(config)
    if session is None or user_id is None:
        return json.dumps({"text": "查询失败：缺少运行时上下文。", "citations": []}, ensure_ascii=False)
    return json.dumps(
        {"text": format_sql_result(text2sql(session, question, user_id)), "citations": []},
        ensure_ascii=False,
    )
