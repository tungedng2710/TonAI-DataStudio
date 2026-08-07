import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from .config import Settings


class VersioningError(RuntimeError):
    """Raised when an internal Git or DVC publication cannot be completed."""


@dataclass(frozen=True)
class RevisionBinding:
    git_commit: str
    dvc_revision: str


class GitDVCRevisionService:
    """Publish immutable dataset revisions to isolated internal Git+DVC repositories."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.versioning_root.resolve()
        self.repositories_root = self.root / "git"
        self.locks_root = self.root / "locks"
        if settings.versioning_enabled:
            self.repositories_root.mkdir(parents=True, exist_ok=True)
            self.locks_root.mkdir(parents=True, exist_ok=True)
            if settings.storage_backend != "s3" and settings.dvc_remote_url is None:
                self._local_remote().mkdir(parents=True, exist_ok=True)

    def _repository_path(self, repository_id: str) -> Path:
        try:
            normalized = str(UUID(repository_id))
        except ValueError as exc:
            raise VersioningError("The internal repository ID is invalid.") from exc
        if normalized != repository_id.lower():
            raise VersioningError("The internal repository ID is invalid.")
        return self.repositories_root / normalized

    @staticmethod
    def _validate_revision_id(revision_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{12,64}", revision_id):
            raise VersioningError("The revision ID is invalid.")

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,63}", branch)
            or ".." in branch
            or branch.endswith(("/", ".", ".lock"))
            or "@{" in branch
        ):
            raise VersioningError("The internal Git branch is invalid.")

    def _local_remote(self) -> Path:
        return self.root / "dvc-cache"

    def _remote_url(self) -> str:
        if self.settings.dvc_remote_url:
            return self.settings.dvc_remote_url
        if self.settings.storage_backend == "s3":
            return f"s3://{self.settings.s3_bucket}/dvc/cache"
        return str(self._local_remote())

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "AWS_ACCESS_KEY_ID": self.settings.s3_access_key,
                "AWS_SECRET_ACCESS_KEY": self.settings.s3_secret_key,
                "AWS_DEFAULT_REGION": self.settings.s3_region,
            }
        )
        return environment

    def _run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        cwd: Path,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [executable, *arguments],
                cwd=cwd,
                env=self._environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.settings.versioning_command_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VersioningError(
                f"Could not execute the internal {Path(executable).name} versioning command."
            ) from exc
        if result.returncode not in allowed_returncodes:
            detail = (result.stderr or result.stdout).strip().splitlines()
            summary = detail[-1][:500] if detail else "command failed without diagnostic output"
            raise VersioningError(f"Internal {Path(executable).name} versioning failed: {summary}")
        return result

    def _git(
        self,
        repository: Path,
        *arguments: str,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            self.settings.git_executable,
            arguments,
            cwd=repository,
            allowed_returncodes=allowed_returncodes,
        )

    def _dvc(self, repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self._run(self.settings.dvc_executable, arguments, cwd=repository)

    @contextmanager
    def _lock(self, repository_id: str) -> Iterator[None]:
        lock_path = self.locks_root / f"{repository_id}.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _ensure_repository(self, repository_id: str, branch: str) -> Path:
        repository = self._repository_path(repository_id)
        if (repository / ".git").is_dir():
            return repository

        repository.mkdir(parents=True, exist_ok=False)
        try:
            self._git(repository, "init", "--initial-branch", branch)
            self._git(repository, "config", "user.name", "CogniDoc Data Studio")
            self._git(repository, "config", "user.email", "data-studio@localhost")
            self._dvc(repository, "init")
            self._dvc(
                repository,
                "remote",
                "add",
                "--default",
                self.settings.dvc_remote_name,
                self._remote_url(),
            )
            if self.settings.storage_backend == "s3":
                self._dvc(
                    repository,
                    "remote",
                    "modify",
                    self.settings.dvc_remote_name,
                    "endpointurl",
                    self.settings.s3_endpoint_url,
                )
        except Exception:
            shutil.rmtree(repository, ignore_errors=True)
            raise
        return repository

    def _has_head(self, repository: Path) -> bool:
        result = self._git(
            repository,
            "rev-parse",
            "--verify",
            "HEAD",
            allowed_returncodes=(0, 128),
        )
        return result.returncode == 0

    def _checkout_parent(
        self, repository: Path, branch: str, parent_git_commit: str | None
    ) -> None:
        if parent_git_commit:
            self._git(repository, "cat-file", "-e", f"{parent_git_commit}^{{commit}}")
            self._git(repository, "checkout", "-B", branch, parent_git_commit)
            return
        if not self._has_head(repository):
            return

        self._git(repository, "checkout", "--detach")
        self._git(
            repository,
            "update-ref",
            "-d",
            f"refs/heads/{branch}",
            allowed_returncodes=(0, 1),
        )
        self._git(repository, "switch", "--orphan", branch)

    @staticmethod
    def _replace_tree(
        repository: Path,
        staged_files: Sequence[tuple[str, Path]],
        manifest_bytes: bytes,
        card_markdown: str,
        card_html: str,
        card_metadata: dict[str, Any],
        revision_metadata: dict[str, Any],
    ) -> None:
        data_root = repository / "data"
        if data_root.exists():
            shutil.rmtree(data_root)
        data_root.mkdir()
        for relative_path, source in staged_files:
            destination = data_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

        (repository / "manifest.json").write_bytes(manifest_bytes)
        (repository / "README.md").write_text(card_markdown, encoding="utf-8")
        metadata_root = repository / ".data-studio"
        metadata_root.mkdir(exist_ok=True)
        (metadata_root / "card.html").write_text(card_html, encoding="utf-8")
        (metadata_root / "card-metadata.json").write_text(
            json.dumps(card_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        (metadata_root / "revision.json").write_text(
            json.dumps(
                revision_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _dvc_revision(pointer_path: Path) -> str:
        try:
            pointer = yaml.safe_load(pointer_path.read_text(encoding="utf-8"))
            output = pointer["outs"][0]
            algorithm = str(output.get("hash", "md5"))
            value = str(output[algorithm])
        except (KeyError, IndexError, TypeError, yaml.YAMLError) as exc:
            raise VersioningError("DVC produced an invalid data pointer.") from exc
        return f"{algorithm}:{value}"

    def _binding_from_ref(
        self, repository: Path, revision_ref: str, manifest_bytes: bytes
    ) -> RevisionBinding | None:
        result = self._git(
            repository,
            "show-ref",
            "--verify",
            "--hash",
            revision_ref,
            allowed_returncodes=(0, 1, 128),
        )
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()
        committed_manifest = self._git(
            repository, "show", f"{commit}:manifest.json"
        ).stdout.encode()
        if committed_manifest != manifest_bytes:
            raise VersioningError(
                "An immutable revision ref conflicts with the canonical manifest."
            )
        try:
            pointer = yaml.safe_load(self._git(repository, "show", f"{commit}:data.dvc").stdout)
            output = pointer["outs"][0]
            algorithm = str(output.get("hash", "md5"))
            dvc_revision = f"{algorithm}:{output[algorithm]}"
        except (KeyError, IndexError, TypeError, yaml.YAMLError) as exc:
            raise VersioningError(
                "The immutable revision ref contains an invalid DVC pointer."
            ) from exc
        return RevisionBinding(commit, dvc_revision)

    def publish(
        self,
        *,
        repository_id: str,
        branch: str,
        revision_id: str,
        parent_revision_id: str | None,
        parent_git_commit: str | None,
        commit_message: str,
        data_stage: str | None,
        manifest_bytes: bytes,
        manifest_sha256: str,
        source_object_set_checksum: str,
        staged_files: Sequence[tuple[str, Path]],
        card_markdown: str,
        card_html: str,
        card_metadata: dict[str, Any],
    ) -> RevisionBinding:
        if not self.settings.versioning_enabled:
            raise VersioningError("Git+DVC versioning is disabled.")
        self._validate_revision_id(revision_id)
        self._validate_branch(branch)
        if parent_git_commit and not re.fullmatch(r"[0-9a-f]{40}", parent_git_commit):
            raise VersioningError("The parent Git commit is invalid.")
        revision_ref = f"refs/data-studio/revisions/{revision_id}"
        with self._lock(repository_id):
            repository = self._ensure_repository(repository_id, branch)
            existing = self._binding_from_ref(repository, revision_ref, manifest_bytes)
            if existing:
                return existing

            self._checkout_parent(repository, branch, parent_git_commit)
            self._replace_tree(
                repository,
                staged_files,
                manifest_bytes,
                card_markdown,
                card_html,
                card_metadata,
                {
                    "revision_id": revision_id,
                    "parent_revision_id": parent_revision_id,
                    "manifest_sha256": manifest_sha256,
                    "source_object_set_checksum": source_object_set_checksum,
                    "data_stage": data_stage,
                },
            )
            self._dvc(repository, "add", "data")
            dvc_revision = self._dvc_revision(repository / "data.dvc")

            # A Git ref is never published until DVC confirms the complete object set is durable.
            self._dvc(repository, "push", "data.dvc")
            cloud_status = self._dvc(repository, "status", "--cloud", "--json", "data.dvc")
            try:
                missing_objects = json.loads(cloud_status.stdout or "{}")
            except json.JSONDecodeError as exc:
                raise VersioningError("DVC remote verification returned invalid output.") from exc
            if missing_objects:
                raise VersioningError("DVC remote verification found objects that are not durable.")

            self._git(repository, "add", "--all")
            self._git(repository, "commit", "--message", commit_message)
            git_commit = self._git(repository, "rev-parse", "HEAD").stdout.strip()
            self._git(repository, "update-ref", revision_ref, git_commit, "0" * 40)
            return RevisionBinding(git_commit, dvc_revision)

    def publish_metadata(
        self,
        *,
        repository_id: str,
        branch: str,
        revision_id: str,
        parent_revision_id: str,
        parent_git_commit: str | None,
        commit_message: str,
        manifest_bytes: bytes,
        manifest_sha256: str,
        source_object_set_checksum: str,
        data_stage: str | None,
    ) -> RevisionBinding:
        if not self.settings.versioning_enabled:
            raise VersioningError("Git+DVC versioning is disabled.")
        self._validate_revision_id(revision_id)
        self._validate_branch(branch)
        if not parent_git_commit or not re.fullmatch(r"[0-9a-f]{40}", parent_git_commit):
            raise VersioningError("A stage revision requires a valid parent Git commit.")
        revision_ref = f"refs/data-studio/revisions/{revision_id}"
        with self._lock(repository_id):
            repository = self._ensure_repository(repository_id, branch)
            existing = self._binding_from_ref(repository, revision_ref, manifest_bytes)
            if existing:
                return existing

            self._checkout_parent(repository, branch, parent_git_commit)
            (repository / "manifest.json").write_bytes(manifest_bytes)
            metadata_root = repository / ".data-studio"
            metadata_root.mkdir(exist_ok=True)
            (metadata_root / "revision.json").write_text(
                json.dumps(
                    {
                        "revision_id": revision_id,
                        "parent_revision_id": parent_revision_id,
                        "manifest_sha256": manifest_sha256,
                        "source_object_set_checksum": source_object_set_checksum,
                        "data_stage": data_stage,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            dvc_revision = self._dvc_revision(repository / "data.dvc")
            self._git(repository, "add", "manifest.json", ".data-studio/revision.json")
            self._git(repository, "commit", "--message", commit_message)
            git_commit = self._git(repository, "rev-parse", "HEAD").stdout.strip()
            self._git(repository, "update-ref", revision_ref, git_commit, "0" * 40)
            return RevisionBinding(git_commit, dvc_revision)

    def restore(self, repository_id: str, revision_id: str, destination: Path) -> None:
        """Restore a published source tree through Git metadata and the DVC remote."""

        self._validate_revision_id(revision_id)
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise VersioningError("The restore destination must be an empty directory.")
        destination.mkdir(parents=True, exist_ok=True)
        with self._lock(repository_id):
            repository = self._repository_path(repository_id)
            revision_ref = f"refs/data-studio/revisions/{revision_id}"
            self._git(repository, "show-ref", "--verify", revision_ref)
            with tempfile.TemporaryDirectory(prefix="restore-", dir=self.root) as temporary:
                worktree = Path(temporary) / "worktree"
                self._git(repository, "worktree", "add", "--detach", str(worktree), revision_ref)
                try:
                    self._dvc(worktree, "pull", "data.dvc")
                    shutil.copytree(worktree / "data", destination, dirs_exist_ok=True)
                finally:
                    self._git(repository, "worktree", "remove", "--force", str(worktree))

    def delete_repository(self, repository_id: str) -> None:
        if not self.settings.versioning_enabled:
            return
        with self._lock(repository_id):
            shutil.rmtree(self._repository_path(repository_id), ignore_errors=True)
