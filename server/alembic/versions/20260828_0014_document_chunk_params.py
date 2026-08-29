"""document.chunk_size / chunk_overlap for index-time params

Revision ID: 20260828_0014
Revises: 20260828_0013
Create Date: 2026-08-28

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0014"
down_revision: Union[str, Sequence[str], None] = "20260828_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document", sa.Column("chunk_size", sa.Integer(), nullable=True))
    op.add_column("document", sa.Column("chunk_overlap", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE document SET chunk_size = 800, chunk_overlap = 120 WHERE status = 'ready'"
        )
    )


def downgrade() -> None:
    op.drop_column("document", "chunk_overlap")
    op.drop_column("document", "chunk_size")
