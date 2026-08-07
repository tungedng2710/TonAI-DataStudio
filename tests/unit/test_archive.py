from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from data_studio_api.config import Settings
from data_studio_api.database import Base
from data_studio_api.models import (
    DatasetRepository,
    DatasetRevision,
    RepositoryFile,
    RevisionStatus,
)
from data_studio_api.service import DatasetService
from data_studio_api.storage import LocalObjectStorage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_revision_archive_contains_the_complete_source_tree(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        staging_root=tmp_path / "uploads",
        versioning_enabled=False,
    )
    storage = LocalObjectStorage(settings.storage_root)
    source_files = {
        "README.md": b"---\nlicense: apache-2.0\n---\n# LaTeX OCR\n",
        "data/train.parquet": b"PAR1test-data",
        "metadata.jsonl": b'{"image":"formula.png","text":"x^2"}\n',
    }

    with Session(engine, expire_on_commit=False) as db:
        repository = DatasetRepository(namespace="unsloth", slug="LaTeX_OCR")
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
        for path in reversed(list(source_files)):
            object_key = f"objects/{path}"
            payload = source_files[path]
            storage.put_bytes(object_key, payload, "application/octet-stream")
            db.add(
                RepositoryFile(
                    revision_id=revision.id,
                    path=path,
                    size_bytes=len(payload),
                    sha256="0" * 64,
                    media_type="application/octet-stream",
                    storage_object_key=object_key,
                    is_previewable=False,
                )
            )
        db.commit()

        filename, file_count, chunks = DatasetService(
            db, storage, settings
        ).revision_archive("unsloth", "LaTeX_OCR", "abc123")
        archive_bytes = b"".join(chunks)

    assert filename == "unsloth-LaTeX_OCR-abc123.zip"
    assert file_count == len(source_files)
    with ZipFile(BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == sorted(source_files)
        assert {path: archive.read(path) for path in archive.namelist()} == source_files
