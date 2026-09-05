"""decision_run, decision_span

Revision ID: 20260906_0024
Revises: 20260904_0023
Create Date: 2026-09-06

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0024"
down_revision: Union[str, Sequence[str], None] = "20260904_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["message.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_run_message_id", "decision_run", ["message_id"])
    op.create_index("ix_decision_run_conversation_id", "decision_run", ["conversation_id"])
    op.create_index("ix_decision_run_user_created", "decision_run", ["user_id", "created_at"])

    op.create_table(
        "decision_span",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.String(20), nullable=False),
        sa.Column("decision", postgresql.JSONB(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["decision_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_span_run_seq", "decision_span", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_decision_span_run_seq", table_name="decision_span")
    op.drop_table("decision_span")
    op.drop_index("ix_decision_run_user_created", table_name="decision_run")
    op.drop_index("ix_decision_run_conversation_id", table_name="decision_run")
    op.drop_index("ix_decision_run_message_id", table_name="decision_run")
    op.drop_table("decision_run")
