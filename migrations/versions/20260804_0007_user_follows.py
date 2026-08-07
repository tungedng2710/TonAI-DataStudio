"""Add user follow relationships.

Revision ID: 20260804_0007
Revises: 20260804_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0007"
down_revision: str | None = "20260804_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_follows",
        sa.Column("follower_id", sa.String(36), nullable=False),
        sa.Column("followed_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("follower_id != followed_id", name="ck_user_follows_not_self"),
        sa.ForeignKeyConstraint(["followed_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("follower_id", "followed_id"),
    )
    op.create_index("ix_user_follows_followed_id", "user_follows", ["followed_id"])
    op.create_index("ix_user_follows_follower_id", "user_follows", ["follower_id"])


def downgrade() -> None:
    op.drop_index("ix_user_follows_follower_id", table_name="user_follows")
    op.drop_index("ix_user_follows_followed_id", table_name="user_follows")
    op.drop_table("user_follows")
