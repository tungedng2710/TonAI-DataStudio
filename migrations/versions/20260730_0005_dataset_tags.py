"""Add dataset lifecycle stage and optional tags.

Revision ID: 20260730_0005
Revises: 20260728_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dataset_repositories",
        sa.Column("data_stage", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "dataset_repositories",
        sa.Column(
            "tags",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dataset_repositories", "tags")
    op.drop_column("dataset_repositories", "data_stage")
