"""user_chunk_setting for per-user chunk size/overlap

Revision ID: 20260828_0013
Revises: 20260828_0012
Create Date: 2026-08-28

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0013"
down_revision: Union[str, Sequence[str], None] = "20260828_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_chunk_setting",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("chunk_size > 0", name="ck_user_chunk_setting_size_positive"),
        sa.CheckConstraint("chunk_overlap >= 0", name="ck_user_chunk_setting_overlap_nonneg"),
        sa.CheckConstraint(
            "chunk_overlap < chunk_size",
            name="ck_user_chunk_setting_overlap_lt_size",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_chunk_setting")
