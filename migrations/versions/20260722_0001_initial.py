"""Initial Data Studio operational metadata.

Revision ID: 20260722_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

visibility = sa.Enum("private", "internal", "public", name="visibility")
revision_status = sa.Enum(
    "uploading", "validating", "indexing", "ready", "failed", name="revisionstatus"
)
upload_status = sa.Enum("open", "processing", "complete", "failed", name="uploadstatus")


def upgrade() -> None:
    op.create_table(
        "dataset_repositories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(96), nullable=False),
        sa.Column("visibility", visibility, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "slug"),
    )
    op.create_index("ix_dataset_repositories_namespace", "dataset_repositories", ["namespace"])
    op.create_index("ix_dataset_repositories_slug", "dataset_repositories", ["slug"])
    op.create_table(
        "dataset_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("dataset_repositories.id"), nullable=False
        ),
        sa.Column("parent_revision_id", sa.String(36), sa.ForeignKey("dataset_revisions.id")),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("branch", sa.String(64), nullable=False),
        sa.Column("commit_message", sa.String(500), nullable=False),
        sa.Column("git_commit", sa.String(64)),
        sa.Column("dvc_revision", sa.String(128)),
        sa.Column("manifest_object_key", sa.String(1024), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("status", revision_status, nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("card_markdown", sa.Text(), nullable=False),
        sa.Column("card_html", sa.Text(), nullable=False),
        sa.Column("card_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repository_id", "revision_id"),
    )
    op.create_index("ix_dataset_revisions_repository_id", "dataset_revisions", ["repository_id"])
    op.create_index("ix_dataset_revisions_revision_id", "dataset_revisions", ["revision_id"])
    op.create_index(
        "ix_dataset_revisions_manifest_sha256", "dataset_revisions", ["manifest_sha256"]
    )
    op.create_table(
        "repository_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("dataset_revisions.id"), nullable=False
        ),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("storage_object_key", sa.String(1024), nullable=False),
        sa.Column("is_previewable", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("revision_id", "path"),
    )
    op.create_index("ix_repository_files_revision_id", "repository_files", ["revision_id"])
    op.create_table(
        "dataset_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id", sa.String(36), sa.ForeignKey("dataset_revisions.id"), nullable=False
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("builder_name", sa.String(64), nullable=False),
        sa.Column("builder_parameters", sa.JSON(), nullable=False),
        sa.UniqueConstraint("revision_id", "name"),
    )
    op.create_index("ix_dataset_configs_revision_id", "dataset_configs", ["revision_id"])
    op.create_table(
        "dataset_splits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("config_id", sa.String(36), sa.ForeignKey("dataset_configs.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("data_files", sa.JSON(), nullable=False),
        sa.Column("num_rows", sa.BigInteger()),
        sa.Column("num_bytes", sa.BigInteger(), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("statistics_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("config_id", "name"),
    )
    op.create_index("ix_dataset_splits_config_id", "dataset_splits", ["config_id"])
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("dataset_repositories.id"), nullable=False
        ),
        sa.Column("status", upload_status, nullable=False),
        sa.Column("commit_message", sa.String(500), nullable=False),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("revision_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_upload_sessions_repository_id", "upload_sessions", ["repository_id"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("dataset_repositories.id"), nullable=False
        ),
        sa.Column("revision_id", sa.String(64)),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_processing_jobs_repository_id", "processing_jobs", ["repository_id"])


def downgrade() -> None:
    op.drop_table("processing_jobs")
    op.drop_table("upload_sessions")
    op.drop_table("dataset_splits")
    op.drop_table("dataset_configs")
    op.drop_table("repository_files")
    op.drop_table("dataset_revisions")
    op.drop_table("dataset_repositories")
