"""plan_record.trip_type and nights (no itinerary status)

Revision ID: 20260903_0021
Revises: 20260902_0020
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0021"
down_revision: Union[str, Sequence[str], None] = "20260902_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_record",
        sa.Column("trip_type", sa.String(20), nullable=False, server_default="other"),
    )
    op.add_column("plan_record", sa.Column("nights", sa.Integer(), nullable=True))
    op.alter_column("plan_record", "trip_type", server_default=None)


def downgrade() -> None:
    op.drop_column("plan_record", "nights")
    op.drop_column("plan_record", "trip_type")
