"""Revision dataset lifecycle stage changes.

Revision ID: 20260804_0006
Revises: 20260730_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0006"
down_revision: str | None = "20260730_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dataset_revisions",
        sa.Column("data_stage", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE dataset_revisions
            SET data_stage = (
                SELECT dataset_repositories.data_stage
                FROM dataset_repositories
                WHERE dataset_repositories.id = dataset_revisions.repository_id
            )
            """
        )
    )
    op.add_column(
        "upload_sessions",
        sa.Column("data_stage", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "upload_sessions",
        sa.Column(
            "data_stage_provided",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("upload_sessions", "data_stage_provided")
    op.drop_column("upload_sessions", "data_stage")
    op.drop_column("dataset_revisions", "data_stage")
