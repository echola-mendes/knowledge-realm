"""knowledge_base.is_enabled

Revision ID: 20260827_0006
Revises: 20260827_0005
Create Date: 2026-08-27

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0006"
down_revision: Union[str, Sequence[str], None] = "20260827_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("knowledge_base", "is_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_base", "is_enabled")
