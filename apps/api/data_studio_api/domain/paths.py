import re
from pathlib import PurePosixPath

from ..errors import ValidationError

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def normalize_repository_path(raw_path: str) -> str:
    """Return a safe, portable POSIX repository path.

    Uploaded paths are identities, so normalization is deliberately conservative:
    backslashes are accepted from Windows browsers, while traversal, absolute paths,
    empty segments, control characters, and ambiguous dot segments are rejected.
    """

    path = raw_path.replace("\\", "/")
    if not path or path.startswith("/") or _DRIVE_PREFIX.match(path):
        raise ValidationError("unsafe_path", f"Unsafe repository path: {raw_path!r}")
    if _CONTROL_CHARS.search(path):
        raise ValidationError("unsafe_path", f"Path contains control characters: {raw_path!r}")

    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("unsafe_path", f"Unsafe repository path: {raw_path!r}")

    normalized = PurePosixPath(*parts).as_posix()
    if len(normalized.encode("utf-8")) > 1024:
        raise ValidationError("path_too_long", "Repository paths may not exceed 1024 bytes.")
    return normalized
