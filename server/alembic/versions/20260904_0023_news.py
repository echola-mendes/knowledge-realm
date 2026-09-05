"""news, news_daily_rank, news_settings + default settings seed

Revision ID: 20260904_0023
Revises: 20260903_0022
Create Date: 2026-09-04

"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0023"
down_revision: Union[str, Sequence[str], None] = "20260903_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("importance_score", sa.Integer(), nullable=True),
        sa.Column("heat_score", sa.Float(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_news_url"),
        sa.UniqueConstraint("content_hash", name="uq_news_content_hash"),
    )

    op.create_table(
        "news_daily_rank",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("news_id", sa.BigInteger(), nullable=False),
        sa.Column("rank_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["news_id"], ["news.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rank_date", "category", "rank", name="uq_news_daily_rank_slot"),
    )
    op.create_index("ix_news_daily_rank_news_id", "news_daily_rank", ["news_id"])
    op.create_index("ix_news_daily_rank_rank_date", "news_daily_rank", ["rank_date"])

    op.create_table(
        "news_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("enabled_categories", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    bind = op.get_bind()
    exists = bind.execute(sa.text("SELECT 1 FROM news_settings LIMIT 1")).fetchone()
    if not exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO news_settings (enabled_categories)
                VALUES (CAST(:enabled_categories AS jsonb))
                """
            ),
            {
                "enabled_categories": json.dumps(["technology", "ai", "finance"]),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_news_daily_rank_rank_date", table_name="news_daily_rank")
    op.drop_index("ix_news_daily_rank_news_id", table_name="news_daily_rank")
    op.drop_table("news_settings")
    op.drop_table("news_daily_rank")
    op.drop_table("news")
