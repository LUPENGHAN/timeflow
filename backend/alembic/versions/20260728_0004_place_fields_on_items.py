"""place fields on items

Revision ID: 20260728_0004
Revises: 20260727_0003
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260727_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add place fields to items so a place can be attached directly to an item."""

    op.add_column("items", sa.Column("place_type", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("latitude", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("longitude", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("accuracy_meters", sa.Integer(), nullable=True))
    op.add_column(
        "items",
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="100"),
    )


def downgrade() -> None:
    """Remove place fields from items."""

    op.drop_column("items", "radius_meters")
    op.drop_column("items", "accuracy_meters")
    op.drop_column("items", "longitude")
    op.drop_column("items", "latitude")
    op.drop_column("items", "place_type")
