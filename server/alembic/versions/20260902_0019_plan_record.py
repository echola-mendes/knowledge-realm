"""plan_record for saved itinerary plan pages

Revision ID: 20260902_0019
Revises: 20260901_0018
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0019"
down_revision: Union[str, Sequence[str], None] = "20260901_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("destination", sa.String(100), nullable=True),
        sa.Column("depart_date", sa.String(40), nullable=True),
        sa.Column("minio_key", sa.String(500), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_record_user_id", "plan_record", ["user_id"])
    op.create_index("ix_plan_record_created_at", "plan_record", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_plan_record_created_at", table_name="plan_record")
    op.drop_index("ix_plan_record_user_id", table_name="plan_record")
    op.drop_table("plan_record")
