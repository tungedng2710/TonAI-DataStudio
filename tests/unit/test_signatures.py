from pathlib import Path

import pytest
from data_studio_api.errors import ValidationError
from data_studio_api.service import DatasetService


def test_rejects_extension_spoofed_parquet(tmp_path: Path) -> None:
    path = tmp_path / "data.parquet"
    path.write_bytes(b"this is not parquet")

    with pytest.raises(ValidationError, match="not a valid Parquet"):
        DatasetService._validate_file_signature("data.parquet", path)


def test_accepts_png_magic_bytes(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")

    DatasetService._validate_file_signature("image.png", path)
