import hashlib
import json
import subprocess
from pathlib import Path

from data_studio_api.config import Settings
from data_studio_api.versioning import GitDVCRevisionService, RevisionBinding


def _binding(
    service: GitDVCRevisionService,
    source: Path,
    parent: tuple[str, RevisionBinding] | None = None,
) -> tuple[str, RevisionBinding]:
    manifest = json.dumps(
        {
            "files": [
                {"path": "data.jsonl", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            ]
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    return manifest_sha[:12], service.publish(
        repository_id="11111111-1111-1111-1111-111111111111",
        branch="main",
        revision_id=manifest_sha[:12],
        parent_revision_id=parent[0] if parent else None,
        parent_git_commit=parent[1].git_commit if parent else None,
        commit_message="Publish fixture",
        data_stage=None,
        manifest_bytes=manifest,
        manifest_sha256=manifest_sha,
        source_object_set_checksum=hashlib.sha256(b"inventory").hexdigest(),
        staged_files=[("data.jsonl", source)],
        card_markdown="# Fixture\n",
        card_html="<h1>Fixture</h1>",
        card_metadata={"license": "mit"},
    )


def test_publish_is_immutable_and_restorable_through_dvc(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        storage_backend="local",
        storage_root=tmp_path / "objects",
        staging_root=tmp_path / "uploads",
        versioning_root=tmp_path / "versioning",
    )
    service = GitDVCRevisionService(settings)
    source = tmp_path / "data.jsonl"
    source.write_text('{"value": 1}\n', encoding="utf-8")

    revision_id, first = _binding(service, source)
    _, second = _binding(service, source)

    assert second == first
    assert len(first.git_commit) == 40
    assert first.dvc_revision.startswith("md5:")

    repository = settings.versioning_root / "git" / "11111111-1111-1111-1111-111111111111"
    tracked = subprocess.run(
        [settings.git_executable, "ls-tree", "--name-only", first.git_commit],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked == [
        ".data-studio",
        ".dvc",
        ".dvcignore",
        ".gitignore",
        "README.md",
        "data.dvc",
        "manifest.json",
    ]
    assert "data" not in tracked

    restored = tmp_path / "restored"
    service.restore("11111111-1111-1111-1111-111111111111", revision_id, restored)
    assert (restored / "data.jsonl").read_bytes() == source.read_bytes()

    source.write_text('{"value": 2}\n', encoding="utf-8")
    next_revision_id, next_binding = _binding(service, source, (revision_id, first))
    parent_commit = subprocess.run(
        [settings.git_executable, "rev-parse", f"{next_binding.git_commit}^"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert parent_commit == first.git_commit

    next_restored = tmp_path / "next-restored"
    service.restore(
        "11111111-1111-1111-1111-111111111111",
        next_revision_id,
        next_restored,
    )
    assert (next_restored / "data.jsonl").read_bytes() == source.read_bytes()
