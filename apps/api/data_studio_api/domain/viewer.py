import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import duckdb
import pyarrow.parquet as parquet

from ..errors import ValidationError
from .layout import IMAGE_SUFFIXES, METADATA_NAMES
from .preview import _json_value


@dataclass(frozen=True)
class ViewerFilter:
    column: str
    operator: str
    expected: Any


@dataclass(frozen=True)
class ViewerPage:
    rows: list[dict[str, Any]]
    total_rows: int
    available_rows: int
    row_indices: list[int]


def parse_viewer_filter(raw_filter: str | None, columns: set[str]) -> ViewerFilter | None:
    if not raw_filter:
        return None
    try:
        value = json.loads(raw_filter)
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid_filter", "Filter must be valid JSON.") from exc
    if not isinstance(value, dict) or not {"column", "op", "value"} <= set(value):
        raise ValidationError("invalid_filter", "Filter requires column, op, and value fields.")

    column = value["column"]
    operator = value["op"]
    if not isinstance(column, str) or column not in columns:
        raise ValidationError("invalid_filter", f"Unknown filter column: {column}")
    if operator not in {"eq", "ne", "contains", "gt", "gte", "lt", "lte"}:
        raise ValidationError("invalid_filter", f"Unsupported filter operator: {operator}")
    return ViewerFilter(column, operator, value["value"])


def row_matches_filter(row: dict[str, Any], filter_: ViewerFilter | None) -> bool:
    if filter_ is None:
        return True
    actual = row.get(filter_.column)
    expected = filter_.expected
    if filter_.operator == "eq":
        return bool(actual == expected)
    if filter_.operator == "ne":
        return bool(actual != expected)
    if filter_.operator == "contains":
        return str(expected).lower() in str(actual).lower()
    if isinstance(actual, str) and isinstance(expected, str):
        if filter_.operator == "gt":
            return actual > expected
        if filter_.operator == "gte":
            return actual >= expected
        if filter_.operator == "lt":
            return actual < expected
        return actual <= expected
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        if filter_.operator == "gt":
            return actual > expected
        if filter_.operator == "gte":
            return actual >= expected
        if filter_.operator == "lt":
            return actual < expected
        return actual <= expected
    return False


def page_rows(
    rows: list[dict[str, Any]],
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    filtered = [(index, row) for index, row in enumerate(rows) if row_matches_filter(row, filter_)]
    selected = filtered[offset : offset + limit]
    return ViewerPage(
        rows=[row for _, row in selected],
        total_rows=len(rows),
        available_rows=len(filtered),
        row_indices=[index for index, _ in selected],
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _source_query(path: Path) -> str:
    literal = _sql_literal(str(path))
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return f"SELECT * FROM read_parquet({literal})"
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        return (
            f"SELECT * FROM read_csv_auto({literal}, "
            f"delim = {_sql_literal(delimiter)}, header = true)"
        )
    if suffix == ".jsonl":
        return (
            f"SELECT * FROM read_json_auto({literal}, "
            "format = 'newline_delimited', union_by_name = true)"
        )
    if suffix == ".json":
        return f"SELECT * FROM read_json_auto({literal}, union_by_name = true)"
    if suffix == ".txt":
        return (
            f"SELECT column0 AS text FROM read_csv({literal}, header = false, "
            "delim = '\x1f', quote = '', escape = '', columns = {'column0': 'VARCHAR'})"
        )
    raise ValidationError("unsupported_viewer_file", f"Cannot browse file type {suffix!r}.")


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _filter_sql(filter_: ViewerFilter | None) -> tuple[str, list[Any]]:
    if filter_ is None:
        return "", []
    column = _quoted_identifier(filter_.column)
    if filter_.operator == "contains":
        return f" WHERE CAST({column} AS VARCHAR) ILIKE ?", [f"%{filter_.expected}%"]
    if filter_.operator == "eq":
        return f" WHERE {column} IS NOT DISTINCT FROM ?", [filter_.expected]
    if filter_.operator == "ne":
        return f" WHERE {column} IS DISTINCT FROM ?", [filter_.expected]
    symbols = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f" WHERE {column} {symbols[filter_.operator]} ?", [filter_.expected]


def query_tabular_page(
    files: list[Path],
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    if not files:
        return ViewerPage([], 0, 0, [])

    source = " UNION ALL BY NAME ".join(_source_query(path) for path in files)
    hidden_column = "__cognidoc_viewer_row"
    filter_sql, parameters = _filter_sql(filter_)
    with duckdb.connect() as connection:
        connection.execute(
            f"CREATE TEMP TABLE viewer_source AS "
            f"SELECT row_number() OVER () AS {hidden_column}, * FROM ({source})"
        )
        total_result = connection.execute("SELECT count(*) FROM viewer_source").fetchone()
        available_result = connection.execute(
            f"SELECT count(*) FROM viewer_source{filter_sql}",
            parameters,
        ).fetchone()
        if total_result is None or available_result is None:
            raise RuntimeError("Viewer row count query returned no result.")
        total_rows = int(total_result[0])
        available_rows = int(available_result[0])
        cursor = connection.execute(
            f"SELECT * FROM viewer_source{filter_sql} ORDER BY {hidden_column} LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        )
        names = [item[0] for item in cursor.description]
        hidden_index = names.index(hidden_column)
        rows: list[dict[str, Any]] = []
        row_indices: list[int] = []
        for values in cursor.fetchall():
            row_indices.append(int(values[hidden_index]) - 1)
            rows.append(
                {
                    name: _json_value(value)
                    for name, value in zip(names, values, strict=True)
                    if name != hidden_column
                }
            )
    return ViewerPage(rows, total_rows, available_rows, row_indices)


@dataclass(frozen=True)
class _ParquetShard:
    path: str
    reader: parquet.ParquetFile
    start: int
    row_group_starts: list[int]

    @property
    def row_count(self) -> int:
        return int(self.reader.metadata.num_rows)


def _parquet_shards(sources: list[tuple[str, BinaryIO]]) -> list[_ParquetShard]:
    shards: list[_ParquetShard] = []
    shard_start = 0
    for path, handle in sources:
        reader = parquet.ParquetFile(handle)
        row_group_starts: list[int] = []
        row_group_start = 0
        for index in range(reader.metadata.num_row_groups):
            row_group_starts.append(row_group_start)
            row_group_start += reader.metadata.row_group(index).num_rows
        shards.append(_ParquetShard(path, reader, shard_start, row_group_starts))
        shard_start += reader.metadata.num_rows
    return shards


def _row_group_for_index(shard: _ParquetShard, local_index: int) -> tuple[int, int]:
    for row_group in range(shard.reader.metadata.num_row_groups):
        start = shard.row_group_starts[row_group]
        count = shard.reader.metadata.row_group(row_group).num_rows
        if start <= local_index < start + count:
            return row_group, local_index - start
    raise IndexError(f"Row {local_index} is outside Parquet shard {shard.path}.")


def _shard_for_index(shards: list[_ParquetShard], row_index: int) -> tuple[int, int]:
    for shard_index, shard in enumerate(shards):
        if shard.start <= row_index < shard.start + shard.row_count:
            return shard_index, row_index - shard.start
    raise IndexError(f"Row {row_index} is outside the Parquet split.")


def _filter_value(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("path"), str):
        return value["path"]
    return value


def _image_reference(value: Any, row_index: int, column: str) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not {"bytes", "path"} & set(value):
        return None
    content = value.get("bytes")
    path = value.get("path")
    if content is None and not isinstance(path, str):
        return None
    size = len(content) if isinstance(content, bytes | bytearray | memoryview) else None
    return {
        "_type": "image",
        "row": row_index,
        "column": column,
        "path": path if isinstance(path, str) else None,
        "size": size,
    }


def _viewer_row(row: dict[str, Any], row_index: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column, value in row.items():
        result[column] = _image_reference(value, row_index, column) or _json_value(value)
    return result


def _matching_parquet_indices(
    shards: list[_ParquetShard],
    filter_: ViewerFilter,
    offset: int,
    limit: int,
) -> tuple[list[int], int]:
    selected: list[int] = []
    matched = 0
    for shard in shards:
        for row_group in range(shard.reader.metadata.num_row_groups):
            table = shard.reader.read_row_group(row_group, columns=[filter_.column])
            values = table.to_pylist()
            group_start = shard.start + shard.row_group_starts[row_group]
            for position, row in enumerate(values):
                candidate = {filter_.column: _filter_value(row.get(filter_.column))}
                if not row_matches_filter(candidate, filter_):
                    continue
                if offset <= matched < offset + limit:
                    selected.append(group_start + position)
                matched += 1
    return selected, matched


def _read_parquet_indices(
    shards: list[_ParquetShard],
    row_indices: list[int],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for row_index in row_indices:
        shard_index, local_index = _shard_for_index(shards, row_index)
        row_group, position = _row_group_for_index(shards[shard_index], local_index)
        grouped.setdefault((shard_index, row_group), []).append((row_index, position))

    rows_by_index: dict[int, dict[str, Any]] = {}
    for (shard_index, row_group), positions in grouped.items():
        table = shards[shard_index].reader.read_row_group(row_group)
        for row_index, position in positions:
            row = table.slice(position, 1).to_pylist()[0]
            rows_by_index[row_index] = _viewer_row(row, row_index)
    return [rows_by_index[row_index] for row_index in row_indices]


def query_parquet_page(
    sources: list[tuple[str, BinaryIO]],
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    shards = _parquet_shards(sources)
    total_rows = sum(shard.row_count for shard in shards)
    if filter_ is None:
        row_indices = list(range(offset, min(offset + limit, total_rows)))
        available_rows = total_rows
    else:
        row_indices, available_rows = _matching_parquet_indices(
            shards,
            filter_,
            offset,
            limit,
        )
    return ViewerPage(
        rows=_read_parquet_indices(shards, row_indices),
        total_rows=total_rows,
        available_rows=available_rows,
        row_indices=row_indices,
    )


def parquet_image_cell(
    sources: list[tuple[str, BinaryIO]],
    row_index: int,
    column: str,
) -> tuple[bytes, str | None]:
    shards = _parquet_shards(sources)
    shard_index, local_index = _shard_for_index(shards, row_index)
    shard = shards[shard_index]
    row_group, position = _row_group_for_index(shard, local_index)
    table = shard.reader.read_row_group(row_group, columns=[column])
    if column not in table.column_names:
        raise ValidationError("invalid_image_column", f"Column {column!r} was not found.")
    value = table[column][position].as_py()
    if not isinstance(value, dict):
        raise ValidationError("invalid_image_cell", f"Column {column!r} is not an image.")
    content = value.get("bytes")
    if not isinstance(content, bytes | bytearray | memoryview):
        raise ValidationError(
            "missing_image_bytes",
            "This image cell does not contain image bytes.",
        )
    path = value.get("path")
    return bytes(content), path if isinstance(path, str) else None


def imagefolder_page(
    repository_paths: list[str],
    metadata_path: str | None,
    metadata_page: ViewerPage | None,
    filter_: ViewerFilter | None,
    offset: int,
    limit: int,
) -> ViewerPage:
    if metadata_path is None:
        rows = [
            {
                "image": {"_type": "image", "path": path},
                "label": PurePosixPath(path).parent.name,
            }
            for path in repository_paths
            if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES
        ]
        return page_rows(rows, filter_, offset, limit)

    if metadata_page is None:
        return ViewerPage([], 0, 0, [])
    image_column = next(
        (
            name
            for name in ("file_name", "image", "path")
            if any(name in row for row in metadata_page.rows)
        ),
        None,
    )
    if image_column:
        metadata_parent = PurePosixPath(metadata_path).parent
        available_paths = set(repository_paths)
        for row in metadata_page.rows:
            value = row.get(image_column)
            if isinstance(value, str):
                relative = (metadata_parent / value).as_posix()
                resolved = relative if relative in available_paths else value
                row[image_column] = {"_type": "image", "path": resolved}
    return metadata_page


def imagefolder_metadata_path(paths: list[str]) -> str | None:
    return next(
        (path for path in paths if PurePosixPath(path).name.lower() in METADATA_NAMES),
        None,
    )
