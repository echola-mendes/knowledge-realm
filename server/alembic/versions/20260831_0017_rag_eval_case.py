"""rag_eval_case for GT answer eval cases

Revision ID: 20260831_0017
Revises: 20260830_0016
Create Date: 2026-08-31

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0017"
down_revision: Union[str, Sequence[str], None] = "20260830_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_eval_case",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_norm", sa.String(500), nullable=False),
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_base.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("gt_answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rag_eval_case_user_id", "rag_eval_case", ["user_id"])
    op.create_index(
        "uq_rag_eval_case_scope",
        "rag_eval_case",
        ["user_id", "query_norm", "knowledge_base_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_rag_eval_case_scope", table_name="rag_eval_case")
    op.drop_index("ix_rag_eval_case_user_id", table_name="rag_eval_case")
    op.drop_table("rag_eval_case")
