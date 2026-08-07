import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet
from data_studio_api.domain.viewer import (
    parse_viewer_filter,
    query_parquet_page,
    query_tabular_page,
)


def test_parquet_viewer_pages_and_filters_across_shards(tmp_path: Path) -> None:
    first = tmp_path / "train-00000.parquet"
    second = tmp_path / "train-00001.parquet"
    parquet.write_table(
        pa.table(
            {
                "id": list(range(80)),
                "text": [f"row-{index}" for index in range(80)],
            }
        ),
        first,
    )
    parquet.write_table(
        pa.table(
            {
                "id": list(range(80, 130)),
                "text": [
                    "find-this-row" if index == 129 else f"row-{index}" for index in range(80, 130)
                ],
            }
        ),
        second,
    )

    page = query_tabular_page([first, second], None, offset=100, limit=50)
    assert page.total_rows == 130
    assert page.available_rows == 130
    assert [row["id"] for row in page.rows] == list(range(100, 130))

    filter_ = parse_viewer_filter(
        json.dumps({"column": "text", "op": "contains", "value": "find-this-row"}),
        {"id", "text"},
    )
    filtered = query_tabular_page([first, second], filter_, offset=0, limit=50)
    assert filtered.available_rows == 1
    assert filtered.rows == [{"id": 129, "text": "find-this-row"}]

    with first.open("rb") as first_handle, second.open("rb") as second_handle:
        parquet_page = query_parquet_page(
            [
                (first.name, first_handle),
                (second.name, second_handle),
            ],
            filter_,
            offset=0,
            limit=50,
        )
    assert parquet_page.available_rows == 1
    assert parquet_page.row_indices == [129]
    assert parquet_page.rows == [{"id": 129, "text": "find-this-row"}]
