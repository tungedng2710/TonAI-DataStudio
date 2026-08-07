from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from data_studio_api.domain.preview import preview_file


def test_parquet_preview_uses_bounded_rows_and_full_metadata_count(tmp_path: Path) -> None:
    path = tmp_path / "train.parquet"
    pq.write_table(pa.table({"id": [1, 2, 3], "nested": [["a"], ["b"], ["c"]]}), path)

    preview = preview_file(path, "data/train.parquet", limit=2)

    assert preview.total_rows == 3
    assert preview.rows == [{"id": 1, "nested": ["a"]}, {"id": 2, "nested": ["b"]}]
    assert [field["name"] for field in preview.schema] == ["id", "nested"]


def test_csv_preview_infers_scalar_types_with_polars(tmp_path: Path) -> None:
    path = tmp_path / "train.csv"
    path.write_text("id,score,active\n1,2.5,true\n2,3.0,false\n", encoding="utf-8")

    preview = preview_file(path, "data/train.csv", limit=1)

    assert preview.rows == [{"id": 1, "score": 2.5, "active": True}]
    assert {field["name"]: field["type"] for field in preview.schema} == {
        "id": "Int64",
        "score": "Float64",
        "active": "Boolean",
    }
