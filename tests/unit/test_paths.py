import pytest
from data_studio_api.domain.paths import normalize_repository_path
from data_studio_api.errors import ValidationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("README.md", "README.md"),
        ("data/train.csv", "data/train.csv"),
        ("images\\cats\\1.jpg", "images/cats/1.jpg"),
    ],
)
def test_normalize_safe_paths(raw: str, expected: str) -> None:
    assert normalize_repository_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "/etc/passwd", "../secret", "data/../secret", "C:\\secret", "a//b", "a/./b"],
)
def test_rejects_unsafe_paths(raw: str) -> None:
    with pytest.raises(ValidationError, match="Unsafe"):
        normalize_repository_path(raw)
