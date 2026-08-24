"""entity and entity_link

Revision ID: 20260824_0004
Revises: 20260824_0003
Create Date: 2026-08-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260824_0004"
down_revision: Union[str, Sequence[str], None] = "20260824_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_base.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("knowledge_base_id", "name", "type", name="uq_entity_kb_name_type"),
    )
    op.create_table(
        "entity_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rel", sa.String(100), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["from_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("from_id", "to_id", "rel", "document_id", name="uq_entity_link_edge"),
    )


def downgrade() -> None:
    op.drop_table("entity_link")
    op.drop_table("entity")
