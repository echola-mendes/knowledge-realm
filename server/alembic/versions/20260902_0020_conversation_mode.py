"""conversation.mode for chat tab persistence

Revision ID: 20260902_0020
Revises: 20260902_0019
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0020"
down_revision: Union[str, Sequence[str], None] = "20260902_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column("mode", sa.String(20), nullable=False, server_default="chat"),
    )


def downgrade() -> None:
    op.drop_column("conversation", "mode")
