"""reminder delivery fallback fields

Revision ID: 20260727_0003
Revises: 20260727_0002
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0003"
down_revision: str | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add local notification and fallback status fields."""

    op.add_column(
        "reminders",
        sa.Column(
            "local_registration_status",
            sa.String(length=64),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "reminders",
        sa.Column(
            "fallback_status",
            sa.String(length=64),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column(
        "reminders",
        sa.Column(
            "fallback_after_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
    )
    op.add_column(
        "reminders",
        sa.Column("fallback_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove local notification and fallback status fields."""

    op.drop_column("reminders", "fallback_requested_at")
    op.drop_column("reminders", "fallback_after_seconds")
    op.drop_column("reminders", "fallback_status")
    op.drop_column("reminders", "local_registration_status")
