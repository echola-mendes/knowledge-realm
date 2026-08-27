"""users table and per-user isolation

Revision ID: 20260827_0005
Revises: 20260824_0004
Create Date: 2026-08-27

"""

from __future__ import annotations

import os
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0005"
down_revision: Union[str, Sequence[str], None] = "20260824_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.passwords import hash_password

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    password = (os.environ.get("INITIAL_PASSWORD") or "").strip()
    if not password:
        raise RuntimeError("迁移 20260827_0005 需要环境变量 INITIAL_PASSWORD")
    username = (os.environ.get("INITIAL_USERNAME") or "echola").strip() or "echola"
    user_id = uuid.uuid4()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO users (id, username, password_hash) VALUES (:id, :username, :password_hash)"
        ),
        {"id": user_id, "username": username, "password_hash": hash_password(password)},
    )

    op.add_column("knowledge_base", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("conversation", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tag", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("favorite", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))

    bind.execute(sa.text("UPDATE knowledge_base SET user_id = :uid"), {"uid": user_id})
    bind.execute(sa.text("UPDATE conversation SET user_id = :uid"), {"uid": user_id})
    bind.execute(sa.text("UPDATE tag SET user_id = :uid"), {"uid": user_id})
    bind.execute(sa.text("UPDATE favorite SET user_id = :uid"), {"uid": user_id})

    op.alter_column("knowledge_base", "user_id", nullable=False)
    op.alter_column("conversation", "user_id", nullable=False)
    op.alter_column("tag", "user_id", nullable=False)
    op.alter_column("favorite", "user_id", nullable=False)

    op.create_foreign_key("fk_knowledge_base_user", "knowledge_base", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_conversation_user", "conversation", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_tag_user", "tag", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_favorite_user", "favorite", "users", ["user_id"], ["id"], ondelete="CASCADE")

    op.drop_constraint("knowledge_base_name_key", "knowledge_base", type_="unique")
    op.create_unique_constraint("uq_knowledge_base_user_name", "knowledge_base", ["user_id", "name"])
    op.execute(
        "CREATE UNIQUE INDEX uq_knowledge_base_user_default ON knowledge_base (user_id) WHERE is_default"
    )

    op.drop_constraint("tag_name_key", "tag", type_="unique")
    op.create_unique_constraint("uq_tag_user_name", "tag", ["user_id", "name"])

    op.drop_constraint("favorite_pkey", "favorite", type_="primary")
    op.create_primary_key("favorite_pkey", "favorite", ["user_id", "document_id"])

    op.drop_table("app_user")


def downgrade() -> None:
    raise NotImplementedError("AUTH-1 不支持自动降级")
