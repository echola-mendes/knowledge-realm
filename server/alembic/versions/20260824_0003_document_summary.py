"""document.summary

Revision ID: 20260824_0003
Revises: 20260824_0002
Create Date: 2026-08-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0003"
down_revision: Union[str, Sequence[str], None] = "20260824_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "summary")
