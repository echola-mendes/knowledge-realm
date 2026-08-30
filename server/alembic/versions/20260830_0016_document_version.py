"""document.version + document_version

Revision ID: 20260830_0016
Revises: 20260828_0014
Create Date: 2026-08-30

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0016"
down_revision: Union[str, Sequence[str], None] = "20260828_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "document_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "version", name="uq_document_version"),
    )
    op.create_index("ix_document_version_document_id", "document_version", ["document_id"])
    # 存量为每个文档补 v1 版本行
    op.execute(
        sa.text(
            "INSERT INTO document_version (id, document_id, version, checksum, byte_size) "
            "SELECT gen_random_uuid(), id, 1, checksum, byte_size FROM document "
            "WHERE NOT EXISTS (SELECT 1 FROM document_version v WHERE v.document_id = document.id)"
        )
    )


def downgrade() -> None:
    op.drop_table("document_version")
    op.drop_column("document", "version")
