"""Add user avatar object metadata.

Revision ID: 20260728_0004
Revises: 20260727_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260727_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_object_key", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_media_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_media_type")
    op.drop_column("users", "avatar_object_key")
