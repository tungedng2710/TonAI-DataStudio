"""Add users, personal API tokens, and dataset ownership.

Revision ID: 20260722_0002
Revises: 20260722_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index("ix_api_tokens_token_prefix", "api_tokens", ["token_prefix"])
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True)

    with op.batch_alter_table("dataset_repositories") as batch:
        batch.add_column(sa.Column("owner_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_dataset_repositories_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
        )
        batch.create_index("ix_dataset_repositories_owner_id", ["owner_id"])


def downgrade() -> None:
    with op.batch_alter_table("dataset_repositories") as batch:
        batch.drop_index("ix_dataset_repositories_owner_id")
        batch.drop_constraint("fk_dataset_repositories_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
    op.drop_table("api_tokens")
    op.drop_table("users")
