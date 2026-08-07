"""add complete Git and DVC revision binding

Revision ID: 20260727_0003
Revises: 20260722_0002
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0003"
down_revision = "20260722_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_revisions",
        sa.Column("source_object_set_checksum", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_revisions", "source_object_set_checksum")
