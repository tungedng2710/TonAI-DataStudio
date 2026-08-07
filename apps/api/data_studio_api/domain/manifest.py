import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ManifestFile:
    path: str
    size_bytes: int
    sha256: str
    media_type: str
    object_key: str


def build_manifest(
    repository: str,
    files: list[ManifestFile],
    parent_revision: str | None = None,
    data_stage: str | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "repository": repository,
        "parent_revision": parent_revision,
        "data_stage": data_stage,
        "files": [asdict(file) for file in sorted(files, key=lambda item: item.path)],
    }
    encoded = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return manifest, encoded, hashlib.sha256(encoded).hexdigest()
