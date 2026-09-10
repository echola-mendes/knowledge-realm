"""Text2SQL：自然语言 → 受限 SELECT → 执行（仅演示表白名单）。"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

ALLOWED_TABLES = frozenset({"customers", "products", "orders", "order_items"})
# 自身带 user_id、必须出现「该表.user_id = :user_id」的表
SCOPED_TABLES = frozenset({"customers", "products", "orders"})
MAX_ROWS = 100

_FORBIDDEN_KW = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"execute|call|do|merge|replace|attach|detach|pragma|vacuum|"
    r"union|intersect|except|into|set)\b",
    re.IGNORECASE,
)
_WITH_CTE = re.compile(r"(?is)^\s*with\b")
_SUBQUERY = re.compile(r"\(\s*select\b", re.IGNORECASE)
# FROM/JOIN 表名 [AS] 别名
_TABLE_ALIAS = re.compile(
    r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)\s*(?:(?:as)\s+)?([a-z_][a-z0-9_]*)?",
    re.IGNORECASE,
)
_LIMIT_CLAUSE = re.compile(r"(?is)\blimit\s+\d+(?:\s+offset\s+\d+)?\s*$")
_SCHEMA = """
表（均按 user_id 隔离）：
- customers(id, user_id, name, city, created_at)
- products(id, user_id, name, category, price, stock, created_at)
- orders(id, user_id, customer_id, status, ordered_at, note)  status: pending|paid|shipped|cancelled
- order_items(id, order_id, product_id, quantity, unit_price)  无 user_id，必须 JOIN orders 且 orders.user_id = :user_id
规则：每张出现的 customers/products/orders 都必须写 表或别名.user_id = :user_id；禁止 UNION/CTE/子查询；LIMIT≤100。
""".strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def extract_sql(raw: str) -> str:
    text_raw = (raw or "").strip()
    if text_raw.startswith("```"):
        lines = text_raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_raw = "\n".join(lines).strip()
        if text_raw.lower().startswith("sql"):
            text_raw = text_raw[3:].strip()
    start = text_raw.lower().find("select")
    if start >= 0:
        text_raw = text_raw[start:]
    if ";" in text_raw:
        text_raw = text_raw.split(";", 1)[0]
    return text_raw.strip()


def _alias_map(sql: str) -> dict[str, str]:
    """alias_or_name -> real table name（小写）。"""
    mapping: dict[str, str] = {}
    for m in _TABLE_ALIAS.finditer(sql):
        table = m.group(1).lower()
        alias = (m.group(2) or table).lower()
        # 避免把 ON/WHERE 等吃成别名：下一词若是 SQL 关键字则无别名
        if alias in {
            "on",
            "where",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "full",
            "cross",
            "group",
            "order",
            "limit",
            "having",
            "and",
            "or",
            "as",
        }:
            alias = table
        mapping[alias] = table
        mapping[table] = table
    return mapping


def _tables_used(alias_map: dict[str, str]) -> set[str]:
    return set(alias_map.values())


def _has_user_id_eq(sql: str, table: str, alias_map: dict[str, str]) -> bool:
    """是否存在「该表(或其别名).user_id = :user_id」（或反之）。"""
    names = {alias for alias, real in alias_map.items() if real == table}
    names.add(table)
    for name in names:
        pat = re.compile(
            rf"(?i)\b{re.escape(name)}\.user_id\s*=\s*:user_id\b|:user_id\s*=\s*{re.escape(name)}\.user_id\b"
        )
        if pat.search(sql):
            return True
    # 仅当查询里只有这一张需隔离表、且没有其它业务表时，允许裸 user_id = :user_id
    scoped_present = _tables_used(alias_map) & SCOPED_TABLES
    if scoped_present == {table} and re.search(r"(?i)\buser_id\s*=\s*:user_id\b|:user_id\s*=\s*user_id\b", sql):
        # 裸列不得带其它表前缀误判已由上面覆盖；再排除「xxx.user_id」已处理
        if re.search(r"(?i)(?<![a-z0-9_])user_id\s*=\s*:user_id\b|:user_id\s*=\s*(?<![a-z0-9_.])user_id\b", sql):
            return True
    return False


def _has_orders_user_id_eq(sql: str, alias_map: dict[str, str]) -> bool:
    return _has_user_id_eq(sql, "orders", alias_map)


def _rewrite_limit(sql: str) -> str:
    cleaned = _LIMIT_CLAUSE.sub("", sql).rstrip()
    # 去掉中间残留的 LIMIT（演示场景：禁止复杂 OFFSET 嵌套，统一末尾钳制）
    cleaned = re.sub(r"(?is)\blimit\s+\d+(?:\s+offset\s+\d+)?", "", cleaned).rstrip()
    return f"{cleaned} LIMIT {MAX_ROWS}"


def validate_select_sql(sql: str) -> str:
    cleaned = extract_sql(sql)
    if not cleaned:
        raise ValueError("空 SQL")
    if _WITH_CTE.search(cleaned):
        raise ValueError("禁止 CTE")
    if _SUBQUERY.search(cleaned):
        raise ValueError("禁止子查询")
    compact = " ".join(cleaned.split())
    if not re.match(r"(?is)^select\b", compact):
        raise ValueError("仅允许 SELECT")
    if _FORBIDDEN_KW.search(compact):
        raise ValueError("含禁止关键字或集合运算")

    alias_map = _alias_map(cleaned)
    tables = _tables_used(alias_map)
    if not tables:
        raise ValueError("未识别到表名")
    unknown = tables - ALLOWED_TABLES
    if unknown:
        raise ValueError(f"表不在白名单: {', '.join(sorted(unknown))}")

    # 每张带 user_id 的表必须有真过滤（不是「字符串里出现过 :user_id」）
    for table in tables & SCOPED_TABLES:
        if not _has_user_id_eq(cleaned, table, alias_map):
            raise ValueError(f"{table} 必须包含 {table}.user_id = :user_id（或唯一表时的 user_id = :user_id）")

    # order_items 无 user_id：必须经 orders，且 orders.user_id = :user_id
    if "order_items" in tables:
        if "orders" not in tables:
            raise ValueError("查询 order_items 必须 JOIN orders")
        if not _has_orders_user_id_eq(cleaned, alias_map):
            raise ValueError("查询 order_items 必须包含 orders.user_id = :user_id")

    return _rewrite_limit(cleaned)


def generate_sql(question: str) -> str:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是 Text2SQL。只输出一条 PostgreSQL SELECT，不要解释。"
                "只能查白名单表。customers/products/orders 必须写 表或别名.user_id = :user_id。"
                "order_items 必须 JOIN orders 且 orders.user_id = :user_id。"
                "禁止 UNION/CTE/子查询/多语句。不要分号。\n\n{schema}",
            ),
            ("human", "{question}"),
        ]
    )
    raw = (prompt | model).invoke({"schema": _SCHEMA, "question": question})
    return validate_select_sql(str(raw.content))


def run_select(session: Session, sql: str, user_id: uuid.UUID) -> list[dict[str, Any]]:
    safe = validate_select_sql(sql)
    result = session.execute(text(safe), {"user_id": user_id})
    rows = result.mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows[:MAX_ROWS]:
        out.append({k: _jsonable(v) for k, v in dict(row).items()})
    return out


def text2sql(
    session: Session,
    question: str,
    user_id: uuid.UUID,
    *,
    sql: str | None = None,
) -> dict[str, Any]:
    """自然语言查询演示库。可传入已生成 sql（测试用）跳过 LLM。"""
    q = (question or "").strip()
    if not q and not sql:
        return {"sql": "", "rows": [], "error": "空问题"}
    try:
        final_sql = validate_select_sql(sql) if sql else generate_sql(q)
        rows = run_select(session, final_sql, user_id)
        return {"sql": final_sql, "rows": rows, "error": None}
    except Exception as exc:  # noqa: BLE001 — 工具层吞掉，交给 Agent 展示
        return {"sql": (sql or "").strip(), "rows": [], "error": str(exc)}


def rows_preview(rows: list[dict[str, Any]], *, limit: int = 8) -> str:
    if not rows:
        return "（无行）"
    chunk = rows[:limit]
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in chunk)
