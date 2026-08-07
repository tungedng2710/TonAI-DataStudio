import pytest
from data_studio_api.schemas import DatasetCreate, DatasetPatch
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ("License plate", "license-plate"),
        ("  License   plate  ", "license-plate"),
        ("License--plate", "license-plate"),
        ("DATASET.v2", "dataset.v2"),
    ],
)
def test_dataset_create_normalizes_slug(provided: str, expected: str) -> None:
    dataset = DatasetCreate(namespace="owner", slug=provided)

    assert dataset.slug == expected


def test_dataset_create_still_rejects_unsupported_slug_characters() -> None:
    with pytest.raises(ValidationError):
        DatasetCreate(namespace="owner", slug="License/plate")


def test_dataset_tags_are_normalized_and_deduplicated() -> None:
    dataset = DatasetPatch(
        data_stage="raw_validated",
        tags=["Synthetic Data", "license--plates", "synthetic-data"],
    )

    assert dataset.data_stage == "raw_validated"
    assert dataset.tags == ["synthetic-data", "license-plates"]


def test_dataset_stage_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        DatasetPatch(data_stage="archived")


def test_dataset_tags_reject_unsupported_characters() -> None:
    with pytest.raises(ValidationError):
        DatasetPatch(tags=["image/ocr"])
