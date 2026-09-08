"""document_chunk role / parent_id / embedding nullable

Revision ID: 20260908_0025
Revises: 20260906_0024
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0025"
down_revision: Union[str, Sequence[str], None] = "20260906_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunk",
        sa.Column("role", sa.String(length=16), server_default="child", nullable=False),
    )
    op.add_column(
        "document_chunk",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_document_chunk_parent_id", "document_chunk", ["parent_id"])
    op.create_foreign_key(
        "fk_document_chunk_parent_id",
        "document_chunk",
        "document_chunk",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("document_chunk", "embedding", nullable=True)


def downgrade() -> None:
    op.alter_column("document_chunk", "embedding", nullable=False)
    op.drop_constraint("fk_document_chunk_parent_id", "document_chunk", type_="foreignkey")
    op.drop_index("ix_document_chunk_parent_id", table_name="document_chunk")
    op.drop_column("document_chunk", "parent_id")
    op.drop_column("document_chunk", "role")
