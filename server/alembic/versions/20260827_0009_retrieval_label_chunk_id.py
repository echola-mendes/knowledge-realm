"""retrieval_label chunk_id for chunk-level ground truth

Revision ID: 20260827_0009
Revises: 20260827_0008
Create Date: 2026-08-27

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0009"
down_revision: Union[str, Sequence[str], None] = "20260827_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retrieval_label",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_retrieval_label_chunk_id",
        "retrieval_label",
        "document_chunk",
        ["chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        """
        UPDATE retrieval_label rl
        SET chunk_id = (
            SELECT dc.id
            FROM document_chunk dc
            WHERE dc.document_id = rl.document_id
            ORDER BY dc.chunk_index
            LIMIT 1
        )
        """
    )
    op.execute("DELETE FROM retrieval_label WHERE chunk_id IS NULL")
    op.alter_column("retrieval_label", "chunk_id", nullable=False)
    op.drop_index("uq_retrieval_label_scope", table_name="retrieval_label")
    op.create_index(
        "uq_retrieval_label_scope",
        "retrieval_label",
        ["user_id", "query_norm", "knowledge_base_id", "chunk_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_retrieval_label_scope", table_name="retrieval_label")
    op.create_index(
        "uq_retrieval_label_scope",
        "retrieval_label",
        ["user_id", "query_norm", "knowledge_base_id", "document_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint("fk_retrieval_label_chunk_id", "retrieval_label", type_="foreignkey")
    op.drop_column("retrieval_label", "chunk_id")
