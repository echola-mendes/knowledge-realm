"""document_chunk global chunk_label

Revision ID: 20260827_0010
Revises: 20260827_0009
Create Date: 2026-08-27

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0010"
down_revision: Union[str, Sequence[str], None] = "20260827_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE chunk_label_seq START WITH 1")
    op.add_column("document_chunk", sa.Column("chunk_label", sa.String(32), nullable=True))
    op.execute(
        """
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM document_chunk
        )
        UPDATE document_chunk dc
        SET chunk_label = 'Chunk_' || ordered.rn
        FROM ordered
        WHERE dc.id = ordered.id
        """
    )
    op.execute(
        """
        SELECT setval(
            'chunk_label_seq',
            COALESCE(
                (SELECT MAX(CAST(SUBSTRING(chunk_label FROM 7) AS INTEGER)) FROM document_chunk),
                0
            )
        )
        """
    )
    op.alter_column("document_chunk", "chunk_label", nullable=False)
    op.create_index("uq_document_chunk_label", "document_chunk", ["chunk_label"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_document_chunk_label", table_name="document_chunk")
    op.drop_column("document_chunk", "chunk_label")
    op.execute("DROP SEQUENCE IF EXISTS chunk_label_seq")
