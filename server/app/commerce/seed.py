from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderItem, Product


def seed_commerce_data(session: Session, user_id: uuid.UUID) -> bool:
    """若该用户尚无商品，写入一套演示数据。返回是否新写入。"""
    existing = session.scalar(
        select(func.count()).select_from(Product).where(Product.user_id == user_id)
    )
    if existing and int(existing) > 0:
        return False

    now = datetime.now(timezone.utc)
    customers = [
        Customer(id=uuid.uuid4(), user_id=user_id, name="张三", city="上海"),
        Customer(id=uuid.uuid4(), user_id=user_id, name="李四", city="北京"),
        Customer(id=uuid.uuid4(), user_id=user_id, name="王五", city="杭州"),
        Customer(id=uuid.uuid4(), user_id=user_id, name="赵六", city="深圳"),
    ]
    products = [
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="机械键盘",
            category="电子",
            price=Decimal("399.00"),
            stock=25,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="无线鼠标",
            category="电子",
            price=Decimal("129.00"),
            stock=80,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="27寸显示器",
            category="电子",
            price=Decimal("1599.00"),
            stock=12,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="降噪耳机",
            category="电子",
            price=Decimal("899.00"),
            stock=8,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="充电宝",
            category="电子",
            price=Decimal("159.00"),
            stock=5,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="云南咖啡豆",
            category="食品",
            price=Decimal("68.00"),
            stock=120,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="龙井茶叶",
            category="食品",
            price=Decimal("188.00"),
            stock=40,
        ),
        Product(
            id=uuid.uuid4(),
            user_id=user_id,
            name="笔记本支架",
            category="配件",
            price=Decimal("99.00"),
            stock=3,
        ),
    ]
    session.add_all(customers)
    session.add_all(products)
    session.flush()

    c0, c1, c2, c3 = customers
    p_kb, p_mouse, p_mon, p_hp, p_power, p_coffee, p_tea, p_stand = products

    orders_spec: list[tuple[Customer, str, datetime, str | None, list[tuple[Product, int]]]] = [
        (
            c0,
            "paid",
            now - timedelta(days=40),
            None,
            [(p_kb, 1), (p_mouse, 2)],
        ),
        (
            c0,
            "shipped",
            now - timedelta(days=12),
            "加急",
            [(p_mon, 1)],
        ),
        (
            c1,
            "paid",
            now - timedelta(days=25),
            None,
            [(p_hp, 1), (p_power, 1)],
        ),
        (
            c2,
            "pending",
            now - timedelta(days=3),
            None,
            [(p_coffee, 3), (p_tea, 1)],
        ),
        (
            c3,
            "cancelled",
            now - timedelta(days=18),
            "用户取消",
            [(p_stand, 2)],
        ),
        (
            c1,
            "paid",
            now - timedelta(days=5),
            None,
            [(p_kb, 1), (p_stand, 1), (p_coffee, 2)],
        ),
    ]

    for customer, status, ordered_at, note, items in orders_spec:
        order = Order(
            id=uuid.uuid4(),
            user_id=user_id,
            customer_id=customer.id,
            status=status,
            ordered_at=ordered_at,
            note=note,
        )
        session.add(order)
        session.flush()
        for product, qty in items:
            session.add(
                OrderItem(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    product_id=product.id,
                    quantity=qty,
                    unit_price=product.price,
                )
            )

    session.commit()
    return True
