from pathlib import Path

import pytest
from data_studio_api.config import Settings
from data_studio_api.database import Base
from data_studio_api.errors import ConflictError
from data_studio_api.models import (
    DatasetConfig,
    DatasetRepository,
    DatasetRevision,
    RepositoryFile,
    RevisionStatus,
)
from data_studio_api.schemas import DatasetPatch
from data_studio_api.service import DatasetService, get_repository, get_revision
from data_studio_api.storage import LocalObjectStorage
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def _file(revision_id: str, path: str) -> RepositoryFile:
    return RepositoryFile(
        revision_id=revision_id,
        path=path,
        size_bytes=len(path),
        sha256="0" * 64,
        media_type="application/octet-stream",
        storage_object_key=f"objects/{path}",
        is_previewable=False,
    )


def test_revision_file_loading_is_optional_and_file_pages_are_searchable(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        repository = DatasetRepository(namespace="research", slug="demo")
        db.add(repository)
        db.flush()
        revision = DatasetRevision(
            repository_id=repository.id,
            revision_id="abc123",
            manifest_object_key="manifests/abc123.json",
            manifest_sha256="1" * 64,
            status=RevisionStatus.ready,
        )
        db.add(revision)
        db.flush()
        db.add(DatasetConfig(revision_id=revision.id, name="default"))
        db.add_all(
            [
                _file(revision.id, "README.md"),
                _file(revision.id, "data/test.parquet"),
                _file(revision.id, "data/train.parquet"),
            ]
        )
        db.commit()
        db.expunge_all()

        stored_repository = db.get(DatasetRepository, repository.id)
        assert stored_repository is not None
        lightweight = get_revision(db, stored_repository, "abc123", include_files=False)
        assert "files" not in lightweight.__dict__
        assert lightweight.configs[0].name == "default"

        settings = Settings(
            _env_file=None,
            database_url="sqlite://",
            storage_backend="local",
            storage_root=tmp_path / "objects",
            staging_root=tmp_path / "uploads",
        )
        storage = LocalObjectStorage(settings.storage_root)
        service = DatasetService(db, storage, settings)
        for key in ["objects/README.md", "objects/data/test.parquet", "objects/data/train.parquet"]:
            storage.put_bytes(key, key.encode(), "application/octet-stream")
        storage.put_bytes("manifests/abc123.json", b"{}", "application/json")
        files, total = service.list_files(
            "research",
            "demo",
            "abc123",
            offset=0,
            limit=1,
            search="data/",
        )
        assert total == 2
        assert [file.path for file in files] == ["data/test.parquet"]

        literal_wildcard, literal_total = service.list_files(
            "research",
            "demo",
            "abc123",
            offset=0,
            limit=100,
            search="%",
        )
        assert literal_total == 0
        assert not literal_wildcard

        conflicting = DatasetRepository(namespace="research", slug="taken")
        db.add(conflicting)
        db.commit()
        with pytest.raises(ConflictError):
            service.patch_repository("research", "demo", DatasetPatch(slug="taken"))
        db.delete(conflicting)
        db.commit()

        renamed = service.patch_repository("research", "demo", DatasetPatch(slug="renamed"))
        assert renamed.slug == "renamed"
        assert get_repository(db, "research", "renamed").id == repository.id
        assert service.get_file("research", "renamed", "abc123", "README.md").path == "README.md"

        service.delete_repository("research", "renamed")
        assert db.scalar(select(func.count()).select_from(DatasetRepository)) == 0
        assert db.scalar(select(func.count()).select_from(DatasetRevision)) == 0
        assert db.scalar(select(func.count()).select_from(RepositoryFile)) == 0
        assert not (settings.storage_root / "objects/README.md").exists()
        assert not (settings.storage_root / "manifests/abc123.json").exists()
