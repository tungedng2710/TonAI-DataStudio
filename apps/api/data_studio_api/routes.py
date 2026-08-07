from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .auth import (
    Principal,
    authorize_repository_read,
    authorize_repository_write,
    can_read_repository,
    get_optional_principal,
    get_principal,
    require_scope,
)
from .config import Settings, get_settings
from .database import get_db
from .errors import NotFoundError
from .models import (
    DatasetConfig,
    DatasetRepository,
    DatasetRevision,
    DatasetSplit,
    ProcessingJob,
    User,
)
from .schemas import (
    ConfigRead,
    DatasetCreate,
    DatasetList,
    DatasetPatch,
    DatasetRead,
    FilePage,
    JobRead,
    RevisionRead,
    RevisionSummary,
    StageChangeCreate,
    UploadComplete,
    UploadCreate,
    UploadFilesResult,
    UploadRead,
    ViewerResponse,
)
from .service import (
    DatasetService,
    get_repository,
    repository_payload,
    resolve_revision,
)
from .storage import ObjectStorage

router = APIRouter(prefix="/api/v1")

Database = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]


def service(request: Request, db: Database, settings: SettingsDependency) -> DatasetService:
    storage: ObjectStorage = request.app.state.storage
    return DatasetService(db, storage, settings)


Service = Annotated[DatasetService, Depends(service)]


def _repository_for_read(
    db: Session,
    namespace: str,
    dataset: str,
    principal: Principal | None,
) -> DatasetRepository:
    repository = get_repository(db, namespace, dataset)
    authorize_repository_read(repository, principal)
    return repository


def _repository_for_write(
    db: Session,
    namespace: str,
    dataset: str,
    principal: Principal,
) -> DatasetRepository:
    repository = get_repository(db, namespace, dataset)
    authorize_repository_write(repository, principal)
    return repository


def _repository_payload(
    db: Session, repository: DatasetRepository, principal: Principal | None
) -> dict[str, Any]:
    return repository_payload(
        db,
        repository,
        viewer_id=principal.user_id if principal else None,
        viewer_is_admin=principal.is_admin if principal else False,
    )


def _revision_payload(revision: DatasetRevision, *, include_files: bool) -> dict[str, Any]:
    return {
        "revision_id": revision.revision_id,
        "branch": revision.branch,
        "commit_message": revision.commit_message,
        "data_stage": revision.data_stage,
        "git_commit": revision.git_commit,
        "dvc_revision": revision.dvc_revision,
        "source_object_set_checksum": revision.source_object_set_checksum,
        "status": revision.status,
        "manifest_sha256": revision.manifest_sha256,
        "error_code": revision.error_code,
        "error_message": revision.error_message,
        "created_at": revision.created_at,
        "card_markdown": revision.card_markdown,
        "card_html": revision.card_html,
        "card_metadata": revision.card_metadata,
        "files": revision.files if include_files else [],
        "configs": revision.configs,
    }


@router.get("/datasets", response_model=DatasetList)
def list_datasets(
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
    owner: Annotated[str | None, Query(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=20)] = None,
) -> dict[str, Any]:
    repositories = datasets.list_repositories()
    if owner is not None:
        owner_user = db.scalar(select(User).where(User.username == owner))
        repositories = (
            [item for item in repositories if item.owner_id == owner_user.id]
            if owner_user is not None
            else []
        )
    visible = [item for item in repositories if can_read_repository(item, principal)]
    if search is not None:
        query = search.strip().lower()
        if not query:
            visible = []
        else:
            visible = [
                item
                for item in visible
                if query
                in " ".join(
                    [
                        f"{item.namespace}/{item.slug}",
                        item.slug,
                        item.description,
                        item.data_stage or "",
                        *item.tags,
                    ]
                ).lower()
            ]
            visible.sort(
                key=lambda item: (
                    f"{item.namespace}/{item.slug}".lower() != query,
                    item.slug.lower() != query,
                )
            )
    if limit is not None:
        visible = visible[:limit]
    return {"items": [_repository_payload(db, item, principal) for item in visible]}


@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(
    body: DatasetCreate, db: Database, datasets: Service, principal: CurrentPrincipal
) -> dict[str, Any]:
    require_scope(principal, "write")
    repository = datasets.create_repository(body, principal.user_id)
    return _repository_payload(db, repository, principal)


@router.get("/datasets/{namespace}/{dataset}", response_model=DatasetRead)
def read_dataset(
    namespace: str, dataset: str, db: Database, principal: OptionalPrincipal
) -> dict[str, Any]:
    repository = _repository_for_read(db, namespace, dataset, principal)
    return _repository_payload(db, repository, principal)


@router.patch("/datasets/{namespace}/{dataset}", response_model=DatasetRead)
def patch_dataset(
    namespace: str,
    dataset: str,
    body: DatasetPatch,
    db: Database,
    datasets: Service,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    _repository_for_write(db, namespace, dataset, principal)
    repository = datasets.patch_repository(namespace, dataset, body)
    return _repository_payload(db, repository, principal)


@router.post("/datasets/{namespace}/{dataset}/stage", response_model=DatasetRead)
def change_dataset_stage(
    namespace: str,
    dataset: str,
    body: StageChangeCreate,
    db: Database,
    datasets: Service,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    _repository_for_write(db, namespace, dataset, principal)
    datasets.change_data_stage(
        namespace,
        dataset,
        body.data_stage,
        body.commit_message,
    )
    repository = get_repository(db, namespace, dataset)
    return _repository_payload(db, repository, principal)


@router.delete("/datasets/{namespace}/{dataset}", status_code=204)
def delete_dataset(
    namespace: str,
    dataset: str,
    db: Database,
    datasets: Service,
    principal: CurrentPrincipal,
) -> Response:
    _repository_for_write(db, namespace, dataset, principal)
    datasets.delete_repository(namespace, dataset)
    return Response(status_code=204)


@router.post("/datasets/{namespace}/{dataset}/uploads", response_model=UploadRead, status_code=201)
def create_upload(
    namespace: str,
    dataset: str,
    body: UploadCreate,
    db: Database,
    datasets: Service,
    principal: CurrentPrincipal,
) -> UploadRead:
    _repository_for_write(db, namespace, dataset, principal)
    return UploadRead.model_validate(
        datasets.create_upload(
            namespace,
            dataset,
            body.commit_message,
            body.data_stage,
            "data_stage" in body.model_fields_set,
        )
    )


@router.post("/uploads/{upload_id}/files", response_model=UploadFilesResult)
async def upload_files(
    upload_id: str,
    datasets: Service,
    principal: CurrentPrincipal,
    files: Annotated[list[UploadFile], File(description="Repository files")],
    paths: Annotated[list[str], Form(description="POSIX path corresponding to each file")],
) -> UploadFilesResult:
    authorize_repository_write(datasets.get_upload_repository(upload_id), principal)
    accepted = await datasets.add_files(upload_id, files, paths)
    upload = datasets.get_upload(upload_id)
    return UploadFilesResult(
        upload_id=upload.id, accepted_paths=accepted, bytes_received=upload.bytes_received
    )


@router.post("/uploads/{upload_id}/complete", response_model=RevisionRead)
def complete_upload(
    upload_id: str,
    body: UploadComplete,
    datasets: Service,
    principal: CurrentPrincipal,
    include_files: bool = True,
) -> dict[str, Any]:
    authorize_repository_write(datasets.get_upload_repository(upload_id), principal)
    revision = datasets.complete_upload(
        upload_id,
        body.expected_file_count,
        include_files=include_files,
    )
    return _revision_payload(revision, include_files=include_files)


@router.get("/uploads/{upload_id}", response_model=UploadRead)
def read_upload(upload_id: str, datasets: Service, principal: CurrentPrincipal) -> UploadRead:
    authorize_repository_write(datasets.get_upload_repository(upload_id), principal)
    return UploadRead.model_validate(datasets.get_upload(upload_id))


@router.get("/datasets/{namespace}/{dataset}/revisions", response_model=list[RevisionSummary])
def list_revisions(
    namespace: str, dataset: str, db: Database, principal: OptionalPrincipal
) -> list[DatasetRevision]:
    repository = _repository_for_read(db, namespace, dataset, principal)
    return list(
        db.scalars(
            select(DatasetRevision)
            .where(DatasetRevision.repository_id == repository.id)
            .order_by(DatasetRevision.created_at.desc(), DatasetRevision.id.desc())
        ).all()
    )


@router.get("/datasets/{namespace}/{dataset}/revisions/{revision}", response_model=RevisionRead)
def read_revision(
    namespace: str,
    dataset: str,
    revision: str,
    db: Database,
    principal: OptionalPrincipal,
    include_files: bool = True,
) -> dict[str, Any]:
    repository = _repository_for_read(db, namespace, dataset, principal)
    resolved = resolve_revision(db, repository, revision, include_files=include_files)
    return _revision_payload(resolved, include_files=include_files)


@router.get("/datasets/{namespace}/{dataset}/tree/{revision}/page", response_model=FilePage)
def read_tree_page(
    namespace: str,
    dataset: str,
    revision: str,
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    search: str | None = None,
) -> dict[str, Any]:
    _repository_for_read(db, namespace, dataset, principal)
    items, total = datasets.list_files(
        namespace,
        dataset,
        revision,
        offset=offset,
        limit=limit,
        search=search,
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/datasets/{namespace}/{dataset}/tree/{revision}", response_model=list[dict[str, Any]])
def read_tree(
    namespace: str, dataset: str, revision: str, db: Database, principal: OptionalPrincipal
) -> list[dict[str, Any]]:
    repository = _repository_for_read(db, namespace, dataset, principal)
    resolved = resolve_revision(db, repository, revision)
    return [
        {
            "path": file.path,
            "size_bytes": file.size_bytes,
            "sha256": file.sha256,
            "media_type": file.media_type,
            "is_previewable": file.is_previewable,
        }
        for file in sorted(resolved.files, key=lambda item: item.path)
    ]


@router.get("/datasets/{namespace}/{dataset}/blob/{revision}/{path:path}")
def download_blob(
    namespace: str,
    dataset: str,
    revision: str,
    path: str,
    request: Request,
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
    inline: bool = False,
) -> StreamingResponse:
    _repository_for_read(db, namespace, dataset, principal)
    repository_file = datasets.get_file(namespace, dataset, revision, path)
    storage: ObjectStorage = request.app.state.storage
    return StreamingResponse(
        storage.iter_object(repository_file.storage_object_key),
        media_type=repository_file.media_type,
        headers={
            "Content-Disposition": (
                f"{'inline' if inline else 'attachment'}; "
                f'filename="{repository_file.path.rsplit("/", 1)[-1]}"'
            )
        },
    )


@router.get("/datasets/{namespace}/{dataset}/archive/{revision}")
def download_archive(
    namespace: str,
    dataset: str,
    revision: str,
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
) -> StreamingResponse:
    _repository_for_read(db, namespace, dataset, principal)
    filename, file_count, archive = datasets.revision_archive(namespace, dataset, revision)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Archive-File-Count": str(file_count),
        },
    )


@router.get("/datasets/{namespace}/{dataset}/configs", response_model=list[ConfigRead])
def list_configs(
    namespace: str,
    dataset: str,
    db: Database,
    principal: OptionalPrincipal,
    revision: str = "main",
) -> list[DatasetConfig]:
    repository = _repository_for_read(db, namespace, dataset, principal)
    resolved = resolve_revision(db, repository, revision, include_files=False)
    return resolved.configs


def _resolve_split(
    db: Session,
    namespace: str,
    dataset: str,
    revision: str,
    config_name: str,
    split_name: str,
) -> tuple[DatasetRevision, DatasetSplit]:
    repository = get_repository(db, namespace, dataset)
    resolved = resolve_revision(db, repository, revision, include_files=False)
    statement = (
        select(DatasetSplit)
        .join(DatasetConfig)
        .where(
            DatasetConfig.revision_id == resolved.id,
            DatasetConfig.name == config_name,
            DatasetSplit.name == split_name,
        )
        .options(selectinload(DatasetSplit.config))
    )
    split = db.scalar(statement)
    if split is None:
        raise NotFoundError(f"Config/split {config_name}/{split_name}")
    return resolved, split


@router.get(
    "/datasets/{namespace}/{dataset}/viewer/{config_name}/{split_name}",
    response_model=ViewerResponse,
)
def viewer(
    namespace: str,
    dataset: str,
    config_name: str,
    split_name: str,
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
    revision: str = "main",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    columns: str | None = None,
    filter_: Annotated[str | None, Query(alias="filter")] = None,
) -> ViewerResponse:
    _repository_for_read(db, namespace, dataset, principal)
    resolved, split = _resolve_split(db, namespace, dataset, revision, config_name, split_name)
    page = datasets.viewer_page(
        resolved,
        split,
        raw_filter=filter_,
        offset=offset,
        limit=limit,
    )
    selected = [column for column in columns.split(",") if column] if columns else None
    rows = page.rows
    if selected is not None:
        rows = [{key: row.get(key) for key in selected if key in row} for row in rows]
    return ViewerResponse(
        repository=f"{namespace}/{dataset}",
        revision=resolved.revision_id,
        config=config_name,
        split=split_name,
        offset=offset,
        limit=limit,
        total_rows=page.total_rows,
        available_rows=page.available_rows,
        rows=rows,
        row_indices=page.row_indices,
        schema_=split.schema_json,
        capabilities={
            "projection": True,
            "filter": True,
            "global_sort": False,
            "text_search": False,
            "preview_is_bounded": False,
        },
    )


@router.get(
    "/datasets/{namespace}/{dataset}/viewer-media/{config_name}/{split_name}/{row_index}/{column}"
)
def viewer_media(
    namespace: str,
    dataset: str,
    config_name: str,
    split_name: str,
    row_index: int,
    column: str,
    db: Database,
    datasets: Service,
    principal: OptionalPrincipal,
    revision: str = "main",
    thumbnail: bool = True,
) -> Response:
    _repository_for_read(db, namespace, dataset, principal)
    resolved, split = _resolve_split(
        db,
        namespace,
        dataset,
        revision,
        config_name,
        split_name,
    )
    content, media_type, _ = datasets.viewer_image(
        resolved,
        split,
        row_index=row_index,
        column=column,
        thumbnail=thumbnail,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/datasets/{namespace}/{dataset}/statistics/{config_name}/{split_name}")
def statistics(
    namespace: str,
    dataset: str,
    config_name: str,
    split_name: str,
    db: Database,
    principal: OptionalPrincipal,
    revision: str = "main",
) -> dict[str, Any]:
    _repository_for_read(db, namespace, dataset, principal)
    resolved, split = _resolve_split(db, namespace, dataset, revision, config_name, split_name)
    return {
        "repository": f"{namespace}/{dataset}",
        "revision": resolved.revision_id,
        "config": config_name,
        "split": split_name,
        **split.statistics_json,
    }


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job_id: str, db: Database, principal: CurrentPrincipal) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id}")
    repository = db.get(DatasetRepository, job.repository_id)
    if repository is None:
        raise NotFoundError("Job repository")
    authorize_repository_read(repository, principal)
    return job
