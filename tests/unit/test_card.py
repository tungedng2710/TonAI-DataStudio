import pytest
from data_studio_api.domain.card import parse_dataset_card
from data_studio_api.errors import ValidationError


def test_parses_front_matter_and_sanitizes_markdown() -> None:
    card = parse_dataset_card(
        b"""---
license: apache-2.0
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train-*.jsonl
---
# Useful dataset

<script>alert('no')</script>
[unsafe](javascript:alert('no'))
"""
    )

    assert card.metadata["license"] == "apache-2.0"
    assert card.metadata["configs"][0]["config_name"] == "default"
    assert "<h1>Useful dataset</h1>" in card.html
    assert "<script" not in card.html
    assert "javascript:" not in card.html


def test_invalid_yaml_is_actionable() -> None:
    with pytest.raises(ValidationError, match="Invalid Dataset Card YAML"):
        parse_dataset_card(b"---\nconfigs: [oops\n---\n# Card")


def test_yaml_dates_are_normalized_for_json_storage() -> None:
    card = parse_dataset_card(b"---\ncreated: 2026-07-22\n---\n# Card")
    assert card.metadata["created"] == "2026-07-22"
