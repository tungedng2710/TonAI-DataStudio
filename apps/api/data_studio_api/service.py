import hashlib
import json
import mimetypes
import shutil
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

from .config import Settings
from .domain.archive import iter_repository_zip
from .domain.card import DatasetCard, parse_dataset_card
from .domain.layout import DetectedConfig, detect_layout, is_previewable
from .domain.manifest import ManifestFile, build_manifest
from .domain.paths import normalize_repository_path
from .domain.preview import compute_statistics, preview_split
from .domain.viewer import (
    ViewerPage,
    imagefolder_metadata_path,
    imagefolder_page,
    parquet_image_cell,
    parse_viewer_filter,
    query_parquet_page,
    query_tabular_page,
)
from .errors import ConflictError, NotFoundError, ValidationError
from .models import (
    DatasetConfig,
    DatasetRepository,
    DatasetRevision,
    DatasetSplit,
    ProcessingJob,
    RepositoryFile,
    RevisionStatus,
    UploadSession,
    UploadStatus,
    User,
    utcnow,
)
from .schemas import DatasetCreate, DatasetPatch
from .storage import ObjectStorage
from .versioning import GitDVCRevisionService


def _repository_query(namespace: str, slug: str) -> Select[tuple[DatasetRepository]]:
    return select(DatasetRepository).where(
        DatasetRepository.namespace == namespace, DatasetRepository.slug == slug
    )


def get_repository(db: Session, namespace: str, slug: str) -> DatasetRepository:
    repository = db.scalar(_repository_query(namespace, slug))
    if repository is None:
        raise NotFoundError(f"Dataset {namespace}/{slug}")
    return repository


def get_revision(
    db: Session,
    repository: DatasetRepository,
    revision: str,
    *,
    include_files: bool = True,
) -> DatasetRevision:
    options = [selectinload(DatasetRevision.configs).selectinload(DatasetConfig.splits)]
    if include_files:
        options.append(selectinload(DatasetRevision.files))
    statement = (
        select(DatasetRevision)
        .where(
            DatasetRevision.repository_id == repository.id,
            DatasetRevision.revision_id == revision,
        )
        .options(*options)
    )
    result = db.scalar(statement)
    if result is None:
        raise NotFoundError(f"Revision {revision}")
    return result


def latest_revision(db: Session, repository_id: str) -> DatasetRevision | None:
    return db.scalar(
        select(DatasetRevision)
        .where(DatasetRevision.repository_id == repository_id)
        .order_by(DatasetRevision.created_at.desc(), DatasetRevision.id.desc())
        .limit(1)
    )


def resolve_revision(
    db: Session,
    repository: DatasetRepository,
    revision: str | None,
    *,
    include_files: bool = True,
) -> DatasetRevision:
    if revision and revision not in {"main", "latest"}:
        return get_revision(db, repository, revision, include_files=include_files)
    result = latest_revision(db, repository.id)
    if result is None:
        raise NotFoundError("Latest revision")
    return get_revision(db, repository, result.revision_id, include_files=include_files)


class DatasetService:
    def __init__(
        self,
        db: Session,
        storage: ObjectStorage,
        settings: Settings,
        versioning: GitDVCRevisionService | None = None,
    ) -> None:
        self.db = db
        self.storage = storage
        self.settings = settings
        self.versioning = versioning or (
            GitDVCRevisionService(settings) if settings.versioning_enabled else None
        )

    def list_repositories(self) -> Sequence[DatasetRepository]:
        return self.db.scalars(
            select(DatasetRepository).order_by(
                DatasetRepository.updated_at.desc(),
                DatasetRepository.namespace,
                DatasetRepository.slug,
            )
        ).all()

    def create_repository(self, data: DatasetCreate, owner_id: str) -> DatasetRepository:
        if self.db.scalar(_repository_query(data.namespace, data.slug)):
            raise ConflictError(f"Dataset {data.namespace}/{data.slug} already exists.")
        repository = DatasetRepository(owner_id=owner_id, **data.model_dump())
        self.db.add(repository)
        self.db.commit()
        self.db.refresh(repository)
        return repository

    def delete_repository(self, namespace: str, slug: str) -> None:
        repository = get_repository(self.db, namespace, slug)
        upload_ids = list(
            self.db.scalars(
                select(UploadSession.id).where(UploadSession.repository_id == repository.id)
            ).all()
        )
        revision_ids = select(DatasetRevision.id).where(
            DatasetRevision.repository_id == repository.id
        )
        object_keys = list(
            self.db.scalars(
                select(RepositoryFile.storage_object_key).where(
                    RepositoryFile.revision_id.in_(revision_ids)
                )
            ).all()
        )
        object_keys.extend(
            self.db.scalars(
                select(DatasetRevision.manifest_object_key).where(
                    DatasetRevision.repository_id == repository.id
                )
            ).all()
        )
        self.storage.delete_objects(object_keys)
        self.storage.delete_prefix(f"datasets/source/{namespace}/{slug}/")
        self.storage.delete_prefix(f"datasets/derived/{namespace}/{slug}/")
        self.storage.delete_prefix(f"datasets/derived/viewer-thumbnails/{repository.id}/")
        config_ids = select(DatasetConfig.id).where(DatasetConfig.revision_id.in_(revision_ids))
        self.db.execute(delete(DatasetSplit).where(DatasetSplit.config_id.in_(config_ids)))
        self.db.execute(delete(DatasetConfig).where(DatasetConfig.revision_id.in_(revision_ids)))
        self.db.execute(delete(RepositoryFile).where(RepositoryFile.revision_id.in_(revision_ids)))
        self.db.execute(
            update(DatasetRevision)
            .where(DatasetRevision.repository_id == repository.id)
            .values(parent_revision_id=None)
        )
        self.db.execute(
            delete(DatasetRevision).where(DatasetRevision.repository_id == repository.id)
        )
        self.db.execute(delete(UploadSession).where(UploadSession.repository_id == repository.id))
        self.db.execute(delete(ProcessingJob).where(ProcessingJob.repository_id == repository.id))
        self.db.execute(delete(DatasetRepository).where(DatasetRepository.id == repository.id))
        self.db.commit()
        for upload_id in upload_ids:
            shutil.rmtree(self.settings.staging_root / upload_id, ignore_errors=True)
        if self.versioning:
            self.versioning.delete_repository(repository.id)

    def patch_repository(self, namespace: str, slug: str, data: DatasetPatch) -> DatasetRepository:
        repository = get_repository(self.db, namespace, slug)
        if "data_stage" in data.model_fields_set and data.data_stage != repository.data_stage:
            if latest_revision(self.db, repository.id) is None:
                raise ValidationError(
                    "initial_stage_requires_upload",
                    "Choose the initial data stage when publishing the first upload.",
                )
            raise ValidationError(
                "data_stage_revision_required",
                "Changing data stage requires a new revision and commit message.",
            )
        changes = {
            key: value
            for key, value in data.model_dump(exclude_unset=True).items()
            if value is not None or key == "data_stage"
        }
        new_slug = changes.get("slug")
        if new_slug and new_slug != repository.slug:
            existing = self.db.scalar(_repository_query(namespace, new_slug))
            if existing is not None:
                raise ConflictError(f"Dataset {namespace}/{new_slug} already exists.")
        for key, value in changes.items():
            setattr(repository, key, value)
        repository.updated_at = utcnow()
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if new_slug:
                raise ConflictError(f"Dataset {namespace}/{new_slug} already exists.") from exc
            raise
        self.db.refresh(repository)
        return repository

    def list_files(
        self,
        namespace: str,
        slug: str,
        revision: str,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
    ) -> tuple[Sequence[RepositoryFile], int]:
        resolved = resolve_revision(
            self.db,
            get_repository(self.db, namespace, slug),
            revision,
            include_files=False,
        )
        filters = [RepositoryFile.revision_id == resolved.id]
        if search:
            filters.append(RepositoryFile.path.icontains(search[:200], autoescape=True))
        total = (
            self.db.scalar(select(func.count()).select_from(RepositoryFile).where(*filters)) or 0
        )
        files = self.db.scalars(
            select(RepositoryFile)
            .where(*filters)
            .order_by(RepositoryFile.path)
            .offset(offset)
            .limit(limit)
        ).all()
        return files, total

    def get_file(
        self,
        namespace: str,
        slug: str,
        revision: str,
        path: str,
    ) -> RepositoryFile:
        normalized = normalize_repository_path(path)
        resolved = resolve_revision(
            self.db,
            get_repository(self.db, namespace, slug),
            revision,
            include_files=False,
        )
        repository_file = self.db.scalar(
            select(RepositoryFile).where(
                RepositoryFile.revision_id == resolved.id,
                RepositoryFile.path == normalized,
            )
        )
        if repository_file is None:
            raise NotFoundError(f"File {normalized}")
        return repository_file

    def viewer_page(
        self,
        revision: DatasetRevision,
        split: DatasetSplit,
        *,
        raw_filter: str | None,
        offset: int,
        limit: int,
    ) -> ViewerPage:
        columns = {
            str(field["name"])
            for field in split.schema_json
            if isinstance(field, dict) and "name" in field
        }
        filter_ = parse_viewer_filter(raw_filter, columns)
        repository_paths = list(split.data_files)
        metadata_path = (
            imagefolder_metadata_path(repository_paths)
            if split.config.builder_name == "imagefolder"
            else None
        )
        if split.config.builder_name == "imagefolder" and metadata_path is None:
            return imagefolder_page(
                repository_paths,
                None,
                None,
                filter_,
                offset,
                limit,
            )

        required_paths = [metadata_path] if metadata_path else repository_paths
        records = self.db.scalars(
            select(RepositoryFile).where(
                RepositoryFile.revision_id == revision.id,
                RepositoryFile.path.in_(required_paths),
            )
        ).all()
        records_by_path = {record.path: record for record in records}
        missing = [path for path in required_paths if path not in records_by_path]
        if missing:
            raise NotFoundError(f"Viewer source file {missing[0]}")

        all_parquet = required_paths and all(
            Path(path).suffix.lower() == ".parquet" for path in required_paths
        )
        if all_parquet:
            with ExitStack() as stack:
                sources = [
                    (
                        path,
                        stack.enter_context(
                            self.storage.open_object(records_by_path[path].storage_object_key)
                        ),
                    )
                    for path in required_paths
                ]
                page = query_parquet_page(
                    sources,
                    filter_,
                    offset,
                    limit,
                )
            if metadata_path:
                return imagefolder_page(
                    repository_paths,
                    metadata_path,
                    page,
                    filter_,
                    offset,
                    limit,
                )
            return page

        self.settings.staging_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="viewer-", dir=self.settings.staging_root) as temp_name:
            temp_root = Path(temp_name)
            local_files: dict[str, Path] = {}
            for index, repository_path in enumerate(required_paths):
                suffix = Path(repository_path).suffix.lower()
                destination = temp_root / f"{index:06d}{suffix}"
                with destination.open("wb") as handle:
                    handle.writelines(
                        self.storage.iter_object(
                            records_by_path[repository_path].storage_object_key
                        )
                    )
                local_files[repository_path] = destination

            page = query_tabular_page(
                [local_files[path] for path in required_paths],
                filter_,
                offset,
                limit,
            )
            if metadata_path:
                return imagefolder_page(
                    repository_paths,
                    metadata_path,
                    page,
                    filter_,
                    offset,
                    limit,
                )
            return page

    def viewer_image(
        self,
        revision: DatasetRevision,
        split: DatasetSplit,
        *,
        row_index: int,
        column: str,
        thumbnail: bool,
    ) -> tuple[bytes, str, str | None]:
        columns = {
            str(field["name"])
            for field in split.schema_json
            if isinstance(field, dict) and "name" in field
        }
        if column not in columns:
            raise ValidationError("invalid_image_column", f"Unknown image column: {column}")
        paths = list(split.data_files)
        if not paths or any(Path(path).suffix.lower() != ".parquet" for path in paths):
            raise ValidationError(
                "unsupported_image_source",
                "Embedded image previews require Parquet source files.",
            )

        column_key = hashlib.sha256(column.encode()).hexdigest()[:16]
        cache_key = (
            f"datasets/derived/viewer-thumbnails/{revision.repository_id}/"
            f"{revision.revision_id}/{split.id}/{row_index}/{column_key}.webp"
        )
        if thumbnail and self.storage.has_object(cache_key):
            return b"".join(self.storage.iter_object(cache_key)), "image/webp", None

        records = self.db.scalars(
            select(RepositoryFile).where(
                RepositoryFile.revision_id == revision.id,
                RepositoryFile.path.in_(paths),
            )
        ).all()
        records_by_path = {record.path: record for record in records}
        missing = [path for path in paths if path not in records_by_path]
        if missing:
            raise NotFoundError(f"Viewer source file {missing[0]}")

        with ExitStack() as stack:
            sources = [
                (
                    path,
                    stack.enter_context(
                        self.storage.open_object(records_by_path[path].storage_object_key)
                    ),
                )
                for path in paths
            ]
            try:
                content, filename = parquet_image_cell(
                    sources,
                    row_index,
                    column,
                )
            except IndexError as exc:
                raise NotFoundError(f"Viewer row {row_index}") from exc
        if len(content) > self.settings.viewer_image_max_bytes:
            raise ValidationError(
                "image_too_large",
                "This image is too large to preview safely.",
            )

        try:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > self.settings.viewer_image_max_pixels:
                    raise ValidationError(
                        "image_too_large",
                        "This image has too many pixels to preview safely.",
                    )
                media_type = Image.MIME.get(image.format or "", "application/octet-stream")
                if not thumbnail:
                    return content, media_type, filename
                image.seek(0)
                image.thumbnail(
                    (
                        self.settings.viewer_thumbnail_size,
                        self.settings.viewer_thumbnail_size,
                    )
                )
                rendered: Image.Image = image
                if image.mode not in {"RGB", "RGBA"}:
                    rendered = image.convert("RGBA" if "transparency" in image.info else "RGB")
                output = BytesIO()
                rendered.save(output, format="WEBP", quality=82, method=4)
                if rendered is not image:
                    rendered.close()
                thumbnail_bytes = output.getvalue()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError(
                "invalid_image_cell",
                "The image cell could not be decoded.",
            ) from exc

        self.storage.put_bytes(cache_key, thumbnail_bytes, "image/webp")
        return thumbnail_bytes, "image/webp", filename

    def revision_archive(
        self,
        namespace: str,
        slug: str,
        revision: str,
    ) -> tuple[str, int, Iterator[bytes]]:
        resolved = resolve_revision(
            self.db,
            get_repository(self.db, namespace, slug),
            revision,
            include_files=False,
        )
        files = self.db.scalars(
            select(RepositoryFile)
            .where(RepositoryFile.revision_id == resolved.id)
            .order_by(RepositoryFile.path)
        ).all()
        filename = f"{namespace}-{slug}-{resolved.revision_id}.zip"
        return filename, len(files), iter_repository_zip(files, self.storage)

    def change_data_stage(
        self,
        namespace: str,
        slug: str,
        data_stage: str | None,
        commit_message: str,
    ) -> DatasetRevision:
        repository = get_repository(self.db, namespace, slug)
        if repository.data_stage == data_stage:
            raise ValidationError(
                "data_stage_unchanged",
                "Choose a data stage different from the current stage.",
            )
        latest = latest_revision(self.db, repository.id)
        if latest is None:
            raise ValidationError(
                "initial_stage_requires_upload",
                "Choose the initial data stage when publishing the first upload.",
            )
        parent = get_revision(self.db, repository, latest.revision_id, include_files=True)
        entries = [
            ManifestFile(
                path=item.path,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
                media_type=item.media_type,
                object_key=item.storage_object_key,
            )
            for item in parent.files
        ]
        _, manifest_bytes, manifest_sha = build_manifest(
            f"{repository.namespace}/{repository.slug}",
            entries,
            parent.revision_id,
            data_stage,
        )
        revision_id = manifest_sha[:12]
        source_checksum = parent.source_object_set_checksum or self._source_object_set_checksum(
            entries
        )
        manifest_key = (
            f"datasets/derived/{repository.namespace}/{repository.slug}/{revision_id}/manifest.json"
        )
        revision = DatasetRevision(
            repository_id=repository.id,
            parent_revision_id=parent.id,
            revision_id=revision_id,
            branch=repository.default_branch,
            commit_message=commit_message,
            data_stage=data_stage,
            source_object_set_checksum=source_checksum,
            manifest_object_key=manifest_key,
            manifest_sha256=manifest_sha,
            status=RevisionStatus.ready,
            card_markdown=parent.card_markdown,
            card_html=parent.card_html,
            card_metadata=parent.card_metadata,
        )
        self.db.add(revision)
        self.db.flush()

        for item in parent.files:
            self.db.add(
                RepositoryFile(
                    revision_id=revision.id,
                    path=item.path,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    media_type=item.media_type,
                    storage_object_key=item.storage_object_key,
                    is_previewable=item.is_previewable,
                )
            )
        for source_config in parent.configs:
            config = DatasetConfig(
                revision_id=revision.id,
                name=source_config.name,
                builder_name=source_config.builder_name,
                builder_parameters=source_config.builder_parameters,
            )
            self.db.add(config)
            self.db.flush()
            for source_split in source_config.splits:
                self.db.add(
                    DatasetSplit(
                        config_id=config.id,
                        name=source_split.name,
                        data_files=source_split.data_files,
                        num_rows=source_split.num_rows,
                        num_bytes=source_split.num_bytes,
                        schema_json=source_split.schema_json,
                        preview_json=source_split.preview_json,
                        statistics_json=source_split.statistics_json,
                    )
                )

        self.storage.put_bytes(manifest_key, manifest_bytes, "application/json")
        if self.versioning:
            binding = self.versioning.publish_metadata(
                repository_id=repository.id,
                branch=repository.default_branch,
                revision_id=revision_id,
                parent_revision_id=parent.revision_id,
                parent_git_commit=parent.git_commit,
                commit_message=commit_message,
                manifest_bytes=manifest_bytes,
                manifest_sha256=manifest_sha,
                source_object_set_checksum=source_checksum,
                data_stage=data_stage,
            )
            revision.git_commit = binding.git_commit
            revision.dvc_revision = binding.dvc_revision

        repository.data_stage = data_stage
        repository.updated_at = utcnow()
        self.db.commit()
        return get_revision(self.db, repository, revision_id, include_files=True)

    def create_upload(
        self,
        namespace: str,
        slug: str,
        commit_message: str | None,
        data_stage: str | None = None,
        data_stage_provided: bool = False,
    ) -> UploadSession:
        repository = get_repository(self.db, namespace, slug)
        if (
            data_stage_provided
            and data_stage != repository.data_stage
            and latest_revision(self.db, repository.id) is not None
            and not commit_message
        ):
            raise ValidationError(
                "stage_commit_message_required",
                "A commit message is required when an upload changes the data stage.",
            )
        upload = UploadSession(
            repository_id=repository.id,
            commit_message=commit_message or "",
            data_stage=data_stage,
            data_stage_provided=data_stage_provided,
        )
        self.db.add(upload)
        self.db.commit()
        self.db.refresh(upload)
        (self.settings.staging_root / upload.id).mkdir(parents=True, exist_ok=False)
        return upload

    def get_upload(self, upload_id: str) -> UploadSession:
        upload = self.db.get(UploadSession, upload_id)
        if upload is None:
            raise NotFoundError(f"Upload {upload_id}")
        return upload

    def get_upload_repository(self, upload_id: str) -> DatasetRepository:
        upload = self.get_upload(upload_id)
        repository = self.db.get(DatasetRepository, upload.repository_id)
        if repository is None:
            raise NotFoundError("Upload repository")
        return repository

    async def add_files(
        self, upload_id: str, files: list[UploadFile], paths: list[str]
    ) -> list[str]:
        upload = self.get_upload(upload_id)
        if upload.status != UploadStatus.open:
            raise ConflictError("Files can only be added to an open upload.")
        if len(files) != len(paths):
            raise ValidationError("path_count_mismatch", "Provide one relative path for each file.")
        if (
            self.settings.max_file_count
            and upload.file_count + len(files) > self.settings.max_file_count
        ):
            raise ValidationError(
                "too_many_files", "Upload exceeds the configured file-count limit."
            )

        normalized_paths = [normalize_repository_path(path) for path in paths]
        if len(normalized_paths) != len(set(normalized_paths)):
            raise ValidationError("duplicate_path", "An upload may not contain duplicate paths.")
        root = (self.settings.staging_root / upload.id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        bytes_added = 0
        written: list[Path] = []
        try:
            for source, normalized in zip(files, normalized_paths, strict=True):
                destination = (root / normalized).resolve()
                if root not in destination.parents or destination.exists():
                    raise ValidationError(
                        "duplicate_path", f"Duplicate or unsafe path: {normalized}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                file_bytes = 0
                with destination.open("xb") as target:
                    while chunk := await source.read(1024 * 1024):
                        file_bytes += len(chunk)
                        bytes_added += len(chunk)
                        if (
                            self.settings.max_file_bytes
                            and file_bytes > self.settings.max_file_bytes
                        ):
                            raise ValidationError(
                                "file_too_large",
                                f"File {normalized!r} exceeds the configured limit.",
                            )
                        if (
                            self.settings.max_upload_bytes
                            and upload.bytes_received + bytes_added > self.settings.max_upload_bytes
                        ):
                            raise ValidationError(
                                "upload_too_large", "Upload exceeds the configured size limit."
                            )
                        target.write(chunk)
                written.append(destination)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        finally:
            for source in files:
                await source.close()

        upload.bytes_received += bytes_added
        upload.file_count += len(files)
        self.db.commit()
        return normalized_paths

    def _staged_files(self, upload: UploadSession) -> list[tuple[str, Path]]:
        root = (self.settings.staging_root / upload.id).resolve()
        if not root.is_dir():
            raise ValidationError("missing_upload", "Upload staging data is missing.")
        files: list[tuple[str, Path]] = []
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValidationError("unsafe_symlink", "Symlinks are not accepted in uploads.")
            if path.is_file():
                files.append((path.relative_to(root).as_posix(), path))
        files.sort(key=lambda item: item[0])
        if not files:
            raise ValidationError("empty_upload", "Upload at least one file before completing.")
        if len(files) != upload.file_count:
            raise ValidationError("file_count_mismatch", "The staged upload file count changed.")
        return files

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _media_type(path: str) -> str:
        if path.lower().endswith(".parquet"):
            return "application/vnd.apache.parquet"
        if path.lower().endswith(".jsonl"):
            return "application/x-ndjson"
        guessed, _ = mimetypes.guess_type(path)
        return guessed or "application/octet-stream"

    @staticmethod
    def _validate_file_signature(repository_path: str, path: Path) -> None:
        """Validate signatures for formats with stable magic bytes.

        Text formats are validated when decoded by the preview reader. This check prevents a
        renamed executable or arbitrary binary from being trusted as Parquet or a browser image.
        """

        suffix = path.suffix.lower()
        with path.open("rb") as handle:
            header = handle.read(16)
            if suffix == ".parquet":
                if path.stat().st_size < 8:
                    valid = False
                else:
                    handle.seek(-4, 2)
                    valid = header[:4] == b"PAR1" and handle.read(4) == b"PAR1"
                if not valid:
                    raise ValidationError(
                        "invalid_file_signature",
                        f"File {repository_path!r} is not a valid Parquet container.",
                    )
            signatures: dict[str, tuple[bytes, ...]] = {
                ".png": (b"\x89PNG\r\n\x1a\n",),
                ".jpg": (b"\xff\xd8\xff",),
                ".jpeg": (b"\xff\xd8\xff",),
                ".gif": (b"GIF87a", b"GIF89a"),
                ".bmp": (b"BM",),
            }
            if suffix in signatures and not any(
                header.startswith(signature) for signature in signatures[suffix]
            ):
                raise ValidationError(
                    "invalid_file_signature",
                    f"File {repository_path!r} does not match its image extension.",
                )
            if suffix == ".webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
                raise ValidationError(
                    "invalid_file_signature",
                    f"File {repository_path!r} is not a valid WebP container.",
                )

    def _card(self, staged: dict[str, Path]) -> DatasetCard:
        readme = next((path for name, path in staged.items() if name.lower() == "readme.md"), None)
        return parse_dataset_card(readme.read_bytes()) if readme else parse_dataset_card(b"")

    def _same_as_latest(
        self,
        repository: DatasetRepository,
        file_entries: list[ManifestFile],
        data_stage: str | None,
    ) -> DatasetRevision | None:
        latest = latest_revision(self.db, repository.id)
        if latest is None:
            return None
        current = self.db.scalars(
            select(RepositoryFile).where(RepositoryFile.revision_id == latest.id)
        ).all()
        old_tree = [
            (item.path, item.size_bytes, item.sha256)
            for item in sorted(current, key=lambda x: x.path)
        ]
        new_tree = [(item.path, item.size_bytes, item.sha256) for item in file_entries]
        return latest if old_tree == new_tree and latest.data_stage == data_stage else None

    @staticmethod
    def _source_object_set_checksum(file_entries: list[ManifestFile]) -> str:
        inventory = [
            {
                "path": item.path,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in sorted(file_entries, key=lambda item: item.path)
        ]
        encoded = json.dumps(
            inventory, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def complete_upload(
        self,
        upload_id: str,
        expected_file_count: int | None = None,
        *,
        include_files: bool = True,
    ) -> DatasetRevision:
        upload = self.get_upload(upload_id)
        if upload.status == UploadStatus.complete and upload.revision_id:
            repository = self.db.get(DatasetRepository, upload.repository_id)
            if repository is None:
                raise NotFoundError("Upload repository")
            return get_revision(
                self.db, repository, upload.revision_id, include_files=include_files
            )
        if upload.status != UploadStatus.open:
            raise ConflictError("Only an open upload can be completed.")
        if expected_file_count is not None and expected_file_count != upload.file_count:
            raise ValidationError(
                "file_count_mismatch",
                f"Expected {expected_file_count} files but received {upload.file_count}.",
            )

        upload.status = UploadStatus.processing
        job = ProcessingJob(repository_id=upload.repository_id, status="running", progress=0.05)
        self.db.add(job)
        self.db.commit()
        try:
            repository = self.db.get(DatasetRepository, upload.repository_id)
            if repository is None:
                raise NotFoundError("Upload repository")
            staged_files = self._staged_files(upload)
            staged = dict(staged_files)
            card = self._card(staged)
            job.progress = 0.2
            layout = detect_layout(list(staged), card.metadata)

            entries: list[ManifestFile] = []
            for path, local_path in staged_files:
                self._validate_file_signature(path, local_path)
                sha256 = self._sha256(local_path)
                object_key = (
                    f"datasets/source/{repository.namespace}/{repository.slug}/{sha256}/{path}"
                )
                entries.append(
                    ManifestFile(
                        path, local_path.stat().st_size, sha256, self._media_type(path), object_key
                    )
                )
            revision_data_stage = (
                upload.data_stage if upload.data_stage_provided else repository.data_stage
            )
            unchanged = self._same_as_latest(repository, entries, revision_data_stage)
            if unchanged:
                upload.status = UploadStatus.complete
                upload.revision_id = unchanged.revision_id
                job.revision_id = unchanged.revision_id
                job.status = "succeeded"
                job.progress = 1.0
                job.finished_at = utcnow()
                self.db.commit()
                return get_revision(
                    self.db, repository, unchanged.revision_id, include_files=include_files
                )

            parent = latest_revision(self.db, repository.id)
            _, manifest_bytes, manifest_sha = build_manifest(
                f"{repository.namespace}/{repository.slug}",
                entries,
                parent.revision_id if parent else None,
                revision_data_stage,
            )
            revision_id = manifest_sha[:12]
            commit_message = upload.commit_message or revision_id
            upload.commit_message = commit_message
            source_object_set_checksum = self._source_object_set_checksum(entries)
            derived_prefix = (
                f"datasets/derived/{repository.namespace}/{repository.slug}/{revision_id}"
            )
            manifest_key = f"{derived_prefix}/manifest.json"
            revision = DatasetRevision(
                repository_id=repository.id,
                parent_revision_id=parent.id if parent else None,
                revision_id=revision_id,
                branch=repository.default_branch,
                commit_message=commit_message,
                data_stage=revision_data_stage,
                source_object_set_checksum=source_object_set_checksum,
                manifest_object_key=manifest_key,
                manifest_sha256=manifest_sha,
                status=RevisionStatus.indexing,
                card_markdown=card.markdown,
                card_html=card.html,
                card_metadata=card.metadata,
            )
            self.db.add(revision)
            self.db.flush()

            job.progress = 0.4
            for entry in entries:
                self.storage.put_file(entry.object_key, staged[entry.path])
                self.db.add(
                    RepositoryFile(
                        revision_id=revision.id,
                        path=entry.path,
                        size_bytes=entry.size_bytes,
                        sha256=entry.sha256,
                        media_type=entry.media_type,
                        storage_object_key=entry.object_key,
                        is_previewable=is_previewable(entry.path),
                    )
                )
            self.storage.put_bytes(manifest_key, manifest_bytes, "application/json")

            if self.versioning:
                binding = self.versioning.publish(
                    repository_id=repository.id,
                    branch=repository.default_branch,
                    revision_id=revision_id,
                    parent_revision_id=parent.revision_id if parent else None,
                    parent_git_commit=parent.git_commit if parent else None,
                    commit_message=commit_message,
                    data_stage=revision_data_stage,
                    manifest_bytes=manifest_bytes,
                    manifest_sha256=manifest_sha,
                    source_object_set_checksum=source_object_set_checksum,
                    staged_files=staged_files,
                    card_markdown=card.markdown,
                    card_html=card.html,
                    card_metadata=card.metadata,
                )
                revision.git_commit = binding.git_commit
                revision.dvc_revision = binding.dvc_revision

            self._save_layout(
                revision,
                layout,
                staged,
                self.settings.staging_root / upload.id,
            )
            revision.status = RevisionStatus.ready
            repository.data_stage = revision_data_stage
            repository.updated_at = utcnow()
            upload.status = UploadStatus.complete
            upload.revision_id = revision_id
            job.revision_id = revision_id
            job.status = "succeeded"
            job.progress = 1.0
            job.finished_at = utcnow()
            self.db.commit()
            shutil.rmtree(self.settings.staging_root / upload.id, ignore_errors=True)
            return get_revision(self.db, repository, revision_id, include_files=include_files)
        except Exception as exc:
            self.db.rollback()
            failed_upload = self.db.get(UploadSession, upload_id)
            if failed_upload:
                failed_upload.status = UploadStatus.failed
                failed_upload.error_code = getattr(exc, "code", "ingestion_failed")
                failed_upload.error_message = str(exc)[:2_000]
            failed_job = self.db.get(ProcessingJob, job.id)
            if failed_job:
                failed_job.status = "failed"
                failed_job.error_code = getattr(exc, "code", "ingestion_failed")
                failed_job.error_message = str(exc)[:2_000]
                failed_job.finished_at = utcnow()
            self.db.commit()
            raise

    def _save_layout(
        self,
        revision: DatasetRevision,
        layout: list[DetectedConfig],
        staged: dict[str, Path],
        staging_root: Path,
    ) -> None:
        for detected_config in layout:
            config = DatasetConfig(
                revision_id=revision.id,
                name=detected_config.name,
                builder_name=detected_config.builder_name,
                builder_parameters=detected_config.parameters,
            )
            self.db.add(config)
            self.db.flush()
            for detected_split in detected_config.splits:
                try:
                    preview = preview_split(
                        staging_root,
                        detected_split.files,
                        self.settings.preview_rows,
                        detected_config.builder_name,
                    )
                except Exception as exc:
                    raise ValidationError(
                        "preview_failed",
                        "Could not inspect "
                        f"config {detected_config.name!r}, split {detected_split.name!r}: "
                        f"{type(exc).__name__}.",
                    ) from exc
                self.db.add(
                    DatasetSplit(
                        config_id=config.id,
                        name=detected_split.name,
                        data_files=detected_split.files,
                        num_rows=preview.total_rows,
                        num_bytes=sum(staged[path].stat().st_size for path in detected_split.files),
                        schema_json=preview.schema,
                        preview_json=preview.rows,
                        statistics_json=compute_statistics(preview.rows, preview.total_rows),
                    )
                )


def repository_payload(
    db: Session,
    repository: DatasetRepository,
    *,
    viewer_id: str | None = None,
    viewer_is_admin: bool = False,
) -> dict[str, Any]:
    latest = latest_revision(db, repository.id)
    owner = db.get(User, repository.owner_id) if repository.owner_id else None
    return {
        "id": repository.id,
        "namespace": repository.namespace,
        "slug": repository.slug,
        "visibility": repository.visibility,
        "description": repository.description,
        "data_stage": repository.data_stage,
        "tags": repository.tags,
        "default_branch": repository.default_branch,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
        "owner": owner.username if owner else None,
        "can_edit": bool(viewer_id and (viewer_is_admin or repository.owner_id == viewer_id)),
        "latest_revision": latest,
    }
