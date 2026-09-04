"""scheduled_task and task_execution tables + NEWS_REFRESH seed

Revision ID: 20260903_0022
Revises: 20260903_0021
Create Date: 2026-09-03

"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0022"
down_revision: Union[str, Sequence[str], None] = "20260903_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("schedule_type", sa.String(16), nullable=False),
        sa.Column("schedule_config", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_type", name="uq_scheduled_task_task_type"),
    )

    op.create_table(
        "task_execution",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["scheduled_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_task_execution_run_id"),
    )
    op.create_index("ix_task_execution_task_id", "task_execution", ["task_id"])

    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM scheduled_task WHERE task_type = :task_type LIMIT 1"),
        {"task_type": "NEWS_REFRESH"},
    ).fetchone()
    if not exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO scheduled_task (name, task_type, schedule_type, schedule_config, enabled)
                VALUES (:name, :task_type, :schedule_type, CAST(:schedule_config AS jsonb), :enabled)
                """
            ),
            {
                "name": "AI资讯更新",
                "task_type": "NEWS_REFRESH",
                "schedule_type": "INTERVAL",
                "schedule_config": json.dumps({"minutes": 30}),
                "enabled": True,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_task_execution_task_id", table_name="task_execution")
    op.drop_table("task_execution")
    op.drop_table("scheduled_task")
