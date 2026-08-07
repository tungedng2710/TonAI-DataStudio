import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Visibility(StrEnum):
    private = "private"
    internal = "internal"
    public = "public"


class RevisionStatus(StrEnum):
    uploading = "uploading"
    validating = "validating"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class UploadStatus(StrEnum):
    open = "open"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_admin: Mapped[bool] = mapped_column(default=False)
    avatar_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    avatar_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repositories: Mapped[list["DatasetRepository"]] = relationship(back_populates="owner")
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserFollow(Base):
    __tablename__ = "user_follows"
    __table_args__ = (
        CheckConstraint("follower_id != followed_id", name="ck_user_follows_not_self"),
    )

    follower_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    followed_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_prefix: Mapped[str] = mapped_column(String(20), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="api_tokens")


class DatasetRepository(Base):
    __tablename__ = "dataset_repositories"
    __table_args__ = (UniqueConstraint("namespace", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    namespace: Mapped[str] = mapped_column(String(64), index=True)
    slug: Mapped[str] = mapped_column(String(96), index=True)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    description: Mapped[str] = mapped_column(Text, default="")
    data_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_branch: Mapped[str] = mapped_column(String(64), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    revisions: Mapped[list["DatasetRevision"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    owner: Mapped[User | None] = relationship(back_populates="repositories")


class DatasetRevision(Base):
    __tablename__ = "dataset_revisions"
    __table_args__ = (UniqueConstraint("repository_id", "revision_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    repository_id: Mapped[str] = mapped_column(ForeignKey("dataset_repositories.id"), index=True)
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_revisions.id"), nullable=True
    )
    revision_id: Mapped[str] = mapped_column(String(64), index=True)
    branch: Mapped[str] = mapped_column(String(64), default="main")
    commit_message: Mapped[str] = mapped_column(String(500), default="Upload dataset")
    data_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dvc_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_object_set_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_object_key: Mapped[str] = mapped_column(String(1024))
    manifest_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[RevisionStatus] = mapped_column(
        Enum(RevisionStatus), default=RevisionStatus.uploading
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_markdown: Mapped[str] = mapped_column(Text, default="")
    card_html: Mapped[str] = mapped_column(Text, default="")
    card_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository: Mapped[DatasetRepository] = relationship(back_populates="revisions")
    files: Mapped[list["RepositoryFile"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    configs: Mapped[list["DatasetConfig"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )


class RepositoryFile(Base):
    __tablename__ = "repository_files"
    __table_args__ = (UniqueConstraint("revision_id", "path"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    revision_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), index=True)
    path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(255))
    storage_object_key: Mapped[str] = mapped_column(String(1024))
    is_previewable: Mapped[bool] = mapped_column(default=False)

    revision: Mapped[DatasetRevision] = relationship(back_populates="files")


class DatasetConfig(Base):
    __tablename__ = "dataset_configs"
    __table_args__ = (UniqueConstraint("revision_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    revision_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    builder_name: Mapped[str] = mapped_column(String(64), default="auto")
    builder_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    revision: Mapped[DatasetRevision] = relationship(back_populates="configs")
    splits: Mapped[list["DatasetSplit"]] = relationship(
        back_populates="config", cascade="all, delete-orphan"
    )


class DatasetSplit(Base):
    __tablename__ = "dataset_splits"
    __table_args__ = (UniqueConstraint("config_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    config_id: Mapped[str] = mapped_column(ForeignKey("dataset_configs.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    data_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    num_rows: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    num_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    schema_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    preview_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    statistics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    config: Mapped[DatasetConfig] = relationship(back_populates="splits")


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    repository_id: Mapped[str] = mapped_column(ForeignKey("dataset_repositories.id"), index=True)
    status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus), default=UploadStatus.open)
    commit_message: Mapped[str] = mapped_column(String(500), default="")
    data_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_stage_provided: Mapped[bool] = mapped_column(default=False)
    bytes_received: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    repository_id: Mapped[str] = mapped_column(ForeignKey("dataset_repositories.id"), index=True)
    revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_type: Mapped[str] = mapped_column(String(64), default="ingest")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempt_count: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
