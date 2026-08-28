"""conversation.summary for Agent long history

Revision ID: 20260828_0011
Revises: 20260827_0010
Create Date: 2026-08-28

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0011"
down_revision: Union[str, Sequence[str], None] = "20260827_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversation", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversation", "summary")
