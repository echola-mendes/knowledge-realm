"""retrieval_label for debug ground truth

Revision ID: 20260827_0007
Revises: 20260827_0006
Create Date: 2026-08-27

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0007"
down_revision: Union[str, Sequence[str], None] = "20260827_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_label",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_norm", sa.String(500), nullable=False),
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_base.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevance", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_retrieval_label_user_id", "retrieval_label", ["user_id"])
    op.create_index(
        "uq_retrieval_label_scope",
        "retrieval_label",
        ["user_id", "query_norm", "knowledge_base_id", "document_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_retrieval_label_scope", table_name="retrieval_label")
    op.drop_index("ix_retrieval_label_user_id", table_name="retrieval_label")
    op.drop_table("retrieval_label")
