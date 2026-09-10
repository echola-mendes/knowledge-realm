from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.agent import text2sql as text2sql_mod
from app.agent.text2sql import text2sql, validate_select_sql
from app.commerce.seed import seed_commerce_data
from app.db import session_scope
from app.main import reset_app_state
from app.models import Customer, Order, OrderItem, Product, User


def test_validate_select_sql_rejects_writes():
    with pytest.raises(ValueError):
        validate_select_sql("DELETE FROM products WHERE user_id = :user_id")
    with pytest.raises(ValueError):
        validate_select_sql("SELECT * FROM users WHERE id = :user_id")
    with pytest.raises(ValueError):
        validate_select_sql("SELECT * FROM products")  # missing user_id eq


def test_validate_rejects_fake_user_id_and_order_items_leak():
    with pytest.raises(ValueError, match="user_id"):
        validate_select_sql("SELECT * FROM products WHERE 1=1 OR :user_id IS NOT NULL")
    with pytest.raises(ValueError, match="user_id"):
        validate_select_sql("SELECT * FROM products WHERE :user_id IS NOT NULL")
    with pytest.raises(ValueError, match="JOIN orders"):
        validate_select_sql("SELECT * FROM order_items WHERE :user_id IS NOT NULL")
    with pytest.raises(ValueError, match="orders.user_id"):
        validate_select_sql(
            "SELECT oi.* FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE oi.quantity > 0"
        )
    with pytest.raises(ValueError, match="UNION|集合"):
        validate_select_sql(
            "SELECT name FROM products WHERE user_id = :user_id "
            "UNION SELECT name FROM products WHERE user_id = :user_id"
        )
    with pytest.raises(ValueError, match="子查询"):
        validate_select_sql(
            "SELECT name FROM products WHERE user_id = :user_id AND id IN (SELECT id FROM products)"
        )


def test_validate_select_sql_allows_whitelist():
    sql = validate_select_sql(
        "SELECT name, stock FROM products WHERE user_id = :user_id AND stock < 10 LIMIT 999"
    )
    assert sql.upper().startswith("SELECT")
    assert sql.upper().endswith("LIMIT 100")
    assert "999" not in sql

    sql2 = validate_select_sql(
        "SELECT oi.quantity FROM order_items oi "
        "JOIN orders o ON oi.order_id = o.id WHERE o.user_id = :user_id"
    )
    assert "LIMIT 100" in sql2.upper()


def test_seed_and_text2sql_query():
    reset_app_state()
    from app.config import get_settings
    from http_client import api_client

    get_settings(load_file=True)
    with api_client() as client:
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        session = session_scope()
        try:
            user = session.scalar(select(User).limit(1))
            assert user is not None
            seed_commerce_data(session, user.id)
            assert session.scalar(select(func.count()).select_from(Product).where(Product.user_id == user.id)) == 8
            assert session.scalar(select(func.count()).select_from(Customer).where(Customer.user_id == user.id)) == 4
            assert session.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id)) == 6
            assert session.scalar(select(func.count()).select_from(OrderItem)) >= 6

            result = text2sql(
                session,
                "库存低于10的商品",
                user.id,
                sql=(
                    "SELECT name, stock FROM products "
                    "WHERE user_id = :user_id AND stock < 10 ORDER BY stock"
                ),
            )
            assert result["error"] is None
            names = {row["name"] for row in result["rows"]}
            assert "充电宝" in names
            assert "笔记本支架" in names
            assert "降噪耳机" in names
        finally:
            session.close()
    reset_app_state()


def test_text2sql_generate_uses_llm(monkeypatch):
    def fake_generate(question: str) -> str:
        return (
            "SELECT c.name, COUNT(o.id) AS cnt "
            "FROM customers c JOIN orders o ON o.customer_id = c.id "
            "WHERE c.user_id = :user_id AND o.user_id = :user_id AND c.city = '上海' "
            "GROUP BY c.name"
        )

    monkeypatch.setattr(text2sql_mod, "generate_sql", fake_generate)
    reset_app_state()
    from app.config import get_settings
    from http_client import api_client

    get_settings(load_file=True)
    with api_client():
        session = session_scope()
        try:
            user = session.scalar(select(User).limit(1))
            assert user is not None
            seed_commerce_data(session, user.id)
            out = text2sql(session, "上海客户有多少订单", user.id)
            assert out["error"] is None
            assert out["rows"]
            assert int(out["rows"][0]["cnt"]) >= 1
        finally:
            session.close()
    reset_app_state()
