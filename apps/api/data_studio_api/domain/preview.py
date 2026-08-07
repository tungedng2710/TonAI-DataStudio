import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

import duckdb
import polars as pl
import pyarrow.parquet as parquet

from .layout import IMAGE_SUFFIXES, METADATA_NAMES


@dataclass
class Preview:
    rows: list[dict[str, Any]]
    schema: list[dict[str, Any]]
    total_rows: int | None


def _json_value(value: Any, max_chars: int = 20_000) -> Any:
    result: Any
    if value is None or isinstance(value, (str, int, bool)):
        result = value
    elif isinstance(value, float):
        result = value if math.isfinite(value) else str(value)
    elif isinstance(value, (date, datetime, Decimal)):
        result = str(value)
    elif isinstance(value, bytes):
        result = {"_type": "binary", "size": len(value)}
    elif isinstance(value, list):
        result = [_json_value(item, max_chars) for item in value]
    elif isinstance(value, dict):
        result = {str(key): _json_value(item, max_chars) for key, item in value.items()}
    else:
        result = str(value)
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    if len(serialized) > max_chars:
        return {"_type": "truncated", "preview": serialized[:max_chars], "size": len(serialized)}
    return result


def _schema_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    types: dict[str, set[str]] = {}
    nullable: dict[str, bool] = {}
    for row in rows:
        for key in set(types) | set(row):
            value = row.get(key)
            types.setdefault(key, set())
            nullable[key] = nullable.get(key, False) or value is None
            if value is not None:
                type_name = (
                    "struct"
                    if isinstance(value, dict)
                    else "list"
                    if isinstance(value, list)
                    else type(value).__name__
                )
                types.setdefault(key, set()).add(type_name)
    return [
        {
            "name": key,
            "type": " | ".join(sorted(type_names)) if type_names else "null",
            "nullable": nullable.get(key, True),
        }
        for key, type_names in sorted(types.items())
    ]


def _csv_preview(path: Path, delimiter: str, limit: int) -> Preview:
    frame = pl.read_csv(
        path,
        separator=delimiter,
        n_rows=limit,
        infer_schema_length=min(1_000, limit),
        try_parse_dates=True,
    )
    rows = [{key: _json_value(value) for key, value in row.items()} for row in frame.to_dicts()]
    schema = [
        {
            "name": name,
            "type": str(dtype),
            "nullable": bool(frame[name].null_count()),
        }
        for name, dtype in frame.schema.items()
    ]
    return Preview(rows, schema, None)


def _jsonl_preview(path: Path, limit: int) -> Preview:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            rows.append(
                _json_value(value) if isinstance(value, dict) else {"value": _json_value(value)}
            )
            if len(rows) >= limit:
                break
    return Preview(rows, _schema_from_rows(rows), None)


def _json_preview(path: Path, limit: int) -> Preview:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    values: Iterable[Any]
    if isinstance(value, list):
        values = value[:limit]
        total = len(value)
    else:
        values = [value]
        total = 1
    rows = [
        _json_value(item) if isinstance(item, dict) else {"value": _json_value(item)}
        for item in values
    ]
    return Preview(rows, _schema_from_rows(rows), total)


def _text_preview(path: Path, limit: int) -> Preview:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for index, line in enumerate(handle):
            if index >= limit:
                break
            rows.append({"text": line.rstrip("\r\n")})
    return Preview(rows, [{"name": "text", "type": "str", "nullable": False}], None)


def preview_file(path: Path, repository_path: str, limit: int) -> Preview:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        parquet_file = parquet.ParquetFile(path)
        with duckdb.connect() as connection:
            table = connection.execute(
                "SELECT * FROM read_parquet(?) LIMIT ?", [str(path), limit]
            ).to_arrow_table()
        rows = [
            {key: _json_value(value) for key, value in row.items()} for row in table.to_pylist()
        ]
        schema = [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in table.schema
        ]
        return Preview(rows, schema, parquet_file.metadata.num_rows)
    if suffix in {".csv", ".tsv"}:
        return _csv_preview(path, "\t" if suffix == ".tsv" else ",", limit)
    if suffix == ".jsonl":
        return _jsonl_preview(path, limit)
    if suffix == ".json":
        return _json_preview(path, limit)
    if suffix == ".txt":
        return _text_preview(path, limit)
    if suffix in IMAGE_SUFFIXES:
        return Preview(
            [{"image": {"_type": "image", "path": repository_path}}],
            [{"name": "image", "type": "image", "nullable": False}],
            1,
        )
    return Preview([], [], 0)


def merge_previews(previews: list[Preview], limit: int) -> Preview:
    rows: list[dict[str, Any]] = []
    total: int | None = 0
    for preview in previews:
        rows.extend(preview.rows[: max(0, limit - len(rows))])
        if total is not None and preview.total_rows is not None:
            total += preview.total_rows
        else:
            total = None
    return Preview(rows[:limit], _schema_from_rows(rows[:limit]), total)


def compute_statistics(rows: list[dict[str, Any]], total_rows: int | None) -> dict[str, Any]:
    columns = sorted({key for row in rows for key in row})
    result: dict[str, Any] = {"sample_size": len(rows), "total_rows": total_rows, "columns": {}}
    for column in columns:
        values = [row.get(column) for row in rows]
        present = [value for value in values if value is not None]
        scalars = [value for value in present if isinstance(value, str | int | float | bool)]
        entry: dict[str, Any] = {
            "null_count": len(values) - len(present),
            "distinct_in_sample": len({json.dumps(value, sort_keys=True) for value in present}),
        }
        numeric = [
            value
            for value in scalars
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        if numeric:
            entry.update(
                {"min": min(numeric), "max": max(numeric), "mean": sum(numeric) / len(numeric)}
            )
        result["columns"][column] = entry
    return result


def preview_split(staging_root: Path, files: list[str], limit: int, builder_name: str) -> Preview:
    if builder_name == "imagefolder":
        metadata = [path for path in files if PurePosixPath(path).name.lower() in METADATA_NAMES]
        if metadata:
            base = preview_file(staging_root / metadata[0], metadata[0], limit)
            image_column = next(
                (
                    name
                    for name in ("file_name", "image", "path")
                    if any(name in row for row in base.rows)
                ),
                None,
            )
            if image_column:
                metadata_parent = PurePosixPath(metadata[0]).parent
                for row in base.rows:
                    value = row.get(image_column)
                    if isinstance(value, str):
                        relative = (metadata_parent / value).as_posix()
                        resolved = relative if relative in files else value
                        row[image_column] = {"_type": "image", "path": resolved}
            return base
        image_files = [
            path for path in files if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES
        ]
        rows = [
            {
                "image": {"_type": "image", "path": path},
                "label": PurePosixPath(path).parent.name,
            }
            for path in image_files[:limit]
        ]
        return Preview(rows, _schema_from_rows(rows), len(image_files))
    previews = [preview_file(staging_root / path, path, limit) for path in files]
    return merge_previews(previews, limit)
