import pytest
from data_studio_api.domain.layout import detect_layout, detect_split_name
from data_studio_api.errors import ValidationError


def test_detects_sharded_conventional_splits() -> None:
    paths = [
        "README.md",
        "data/train-00000-of-00002.parquet",
        "data/train-00001-of-00002.parquet",
        "data/test-00000-of-00001.parquet",
    ]

    configs = detect_layout(paths, {})

    assert configs[0].builder_name == "parquet"
    assert {split.name: split.files for split in configs[0].splits} == {
        "test": ["data/test-00000-of-00001.parquet"],
        "train": [
            "data/train-00000-of-00002.parquet",
            "data/train-00001-of-00002.parquet",
        ],
    }
    assert detect_split_name("nested/validation-00003-of-00004.jsonl") == "validation"


def test_explicit_card_config_takes_precedence() -> None:
    configs = detect_layout(
        ["data/part-1.csv", "data/part-2.csv"],
        {
            "configs": [
                {
                    "config_name": "english",
                    "data_files": {"train": "data/part-*.csv"},
                    "separator": ",",
                }
            ]
        },
    )

    assert configs[0].name == "english"
    assert configs[0].parameters == {"separator": ","}
    assert configs[0].splits[0].files == ["data/part-1.csv", "data/part-2.csv"]


def test_missing_explicit_file_does_not_silently_fallback() -> None:
    with pytest.raises(ValidationError, match="did not match"):
        detect_layout(["train.csv"], {"data_files": {"train": "missing.csv"}})


def test_imagefolder_infers_layout() -> None:
    configs = detect_layout(["cats/1.jpg", "dogs/2.png"], {})
    assert configs[0].builder_name == "imagefolder"
    assert configs[0].splits[0].name == "train"


def test_tabular_shards_take_precedence_over_raw_media() -> None:
    configs = detect_layout(
        [
            "hf_parquet/train-00000-of-00001.parquet",
            "hf_parquet/test-00000-of-00001.parquet",
            "images/sample.png",
            "raw/sample.json",
        ],
        {},
    )

    assert configs[0].builder_name == "parquet"
    assert {split.name: split.files for split in configs[0].splits} == {
        "test": ["hf_parquet/test-00000-of-00001.parquet"],
        "train": ["hf_parquet/train-00000-of-00001.parquet"],
    }


def test_repeated_explicit_split_entries_are_merged() -> None:
    configs = detect_layout(
        ["data/one.csv", "data/two.csv"],
        {
            "configs": [
                {
                    "config_name": "default",
                    "data_files": [
                        {"split": "train", "path": "data/one.csv"},
                        {"split": "train", "path": "data/two.csv"},
                    ],
                }
            ]
        },
    )
    assert configs[0].splits == [
        type(configs[0].splits[0])("train", ["data/one.csv", "data/two.csv"])
    ]
