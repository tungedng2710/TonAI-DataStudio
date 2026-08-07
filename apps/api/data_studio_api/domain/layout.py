import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from ..errors import ValidationError

TABULAR_SUFFIXES = {".parquet", ".csv", ".tsv", ".json", ".jsonl", ".txt"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
METADATA_NAMES = {"metadata.csv", "metadata.jsonl", "metadata.parquet"}
_SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "validation": "validation",
    "valid": "validation",
    "val": "validation",
    "dev": "validation",
    "test": "test",
    "testing": "test",
}
_SHARD_SUFFIX = re.compile(r"[-_.]\d{1,6}-of-\d{1,6}(?=\.[^.]+$)", re.IGNORECASE)
_TOKEN_SPLIT = re.compile(r"[/_.-]+")


@dataclass
class DetectedSplit:
    name: str
    files: list[str] = field(default_factory=list)


@dataclass
class DetectedConfig:
    name: str
    builder_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    splits: list[DetectedSplit] = field(default_factory=list)


def is_previewable(path: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in TABULAR_SUFFIXES or suffix in IMAGE_SUFFIXES


def detect_split_name(path: str) -> str:
    clean = _SHARD_SUFFIX.sub("", path.lower())
    for token in _TOKEN_SPLIT.split(clean):
        if token in _SPLIT_ALIASES:
            return _SPLIT_ALIASES[token]
    return "train"


def _expand_patterns(value: Any, available: set[str], context: str) -> list[str]:
    patterns: list[str]
    if isinstance(value, str):
        patterns = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        patterns = value
    else:
        raise ValidationError("invalid_data_files", f"{context} paths must be strings or lists.")

    matched: list[str] = []
    for pattern in patterns:
        candidates = sorted(path for path in available if fnmatch.fnmatchcase(path, pattern))
        if not candidates:
            raise ValidationError(
                "missing_data_file", f"Dataset Card pattern {pattern!r} did not match any file."
            )
        matched.extend(candidates)
    return sorted(set(matched))


def _explicit_splits(data_files: Any, available: set[str], context: str) -> list[DetectedSplit]:
    if isinstance(data_files, str):
        return [DetectedSplit("train", _expand_patterns(data_files, available, context))]
    if isinstance(data_files, dict):
        return [
            DetectedSplit(str(name), _expand_patterns(paths, available, f"{context}.{name}"))
            for name, paths in data_files.items()
        ]
    if not isinstance(data_files, list):
        raise ValidationError("invalid_data_files", f"{context} must be a path, mapping, or list.")

    if all(isinstance(item, str) for item in data_files):
        return [DetectedSplit("train", _expand_patterns(data_files, available, context))]
    grouped: dict[str, list[str]] = {}
    for index, item in enumerate(data_files):
        if not isinstance(item, dict) or "path" not in item:
            raise ValidationError(
                "invalid_data_files", f"{context}[{index}] must contain split and path."
            )
        split_name = str(item.get("split", "train"))
        grouped.setdefault(split_name, []).extend(
            _expand_patterns(item["path"], available, f"{context}[{index}].path")
        )
    return [DetectedSplit(name, sorted(set(paths))) for name, paths in grouped.items()]


def _builder_for(files: list[str]) -> str:
    suffixes = {PurePosixPath(path).suffix.lower() for path in files}
    if suffixes and suffixes <= IMAGE_SUFFIXES:
        return "imagefolder"
    if ".parquet" in suffixes:
        return "parquet"
    if suffixes & {".csv", ".tsv"}:
        return "csv"
    if suffixes & {".json", ".jsonl"}:
        return "json"
    if ".txt" in suffixes:
        return "text"
    return "auto"


def _validate_split_names(splits: list[DetectedSplit], context: str) -> None:
    if any(not split.name or len(split.name) > 128 for split in splits):
        raise ValidationError("invalid_data_files", f"{context} has an invalid split name.")


def detect_layout(paths: list[str], metadata: dict[str, Any]) -> list[DetectedConfig]:
    available = set(paths)
    configs_value = metadata.get("configs")
    if configs_value is not None:
        if not isinstance(configs_value, list) or not configs_value:
            raise ValidationError(
                "invalid_configs", "Dataset Card configs must be a non-empty list."
            )
        configs: list[DetectedConfig] = []
        config_names: set[str] = set()
        for index, raw_config in enumerate(configs_value):
            if not isinstance(raw_config, dict):
                raise ValidationError("invalid_configs", f"configs[{index}] must be a mapping.")
            name = str(raw_config.get("config_name", raw_config.get("name", "default")))
            if not name or len(name) > 128 or name in config_names:
                raise ValidationError(
                    "invalid_configs", f"Config name {name!r} is empty, duplicated, or too long."
                )
            config_names.add(name)
            if "data_files" not in raw_config:
                raise ValidationError(
                    "invalid_configs", f"Config {name!r} must declare data_files."
                )
            splits = _explicit_splits(raw_config["data_files"], available, f"configs[{index}]")
            _validate_split_names(splits, f"Config {name!r}")
            config_files = [path for split in splits for path in split.files]
            parameters = {
                key: value
                for key, value in raw_config.items()
                if key not in {"config_name", "name", "data_files"}
            }
            configs.append(DetectedConfig(name, _builder_for(config_files), parameters, splits))
        return configs

    if "data_files" in metadata:
        splits = _explicit_splits(metadata["data_files"], available, "data_files")
        _validate_split_names(splits, "data_files")
        files = [path for split in splits for path in split.files]
        config_name = str(metadata.get("config_name", "default"))
        if not config_name or len(config_name) > 128:
            raise ValidationError("invalid_configs", f"Invalid config name: {config_name!r}.")
        return [DetectedConfig(config_name, _builder_for(files), {}, splits)]

    data_paths = sorted(
        path
        for path in paths
        if PurePosixPath(path).suffix.lower() in TABULAR_SUFFIXES
        and PurePosixPath(path).name.lower() not in METADATA_NAMES
    )
    image_paths = sorted(
        path for path in paths if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES
    )
    metadata_paths = sorted(
        path for path in paths if PurePosixPath(path).name.lower() in METADATA_NAMES
    )

    parquet_paths = [
        path for path in data_paths if PurePosixPath(path).suffix.lower() == ".parquet"
    ]
    if parquet_paths:
        data_paths = parquet_paths
    if not data_paths and metadata_paths:
        data_paths = metadata_paths
    if not data_paths:
        if image_paths:
            files = metadata_paths + image_paths
            return [DetectedConfig("default", "imagefolder", {}, [DetectedSplit("train", files)])]
        return []

    grouped: dict[str, list[str]] = {}
    for path in data_paths:
        grouped.setdefault(detect_split_name(path), []).append(path)
    splits = [DetectedSplit(name, sorted(files)) for name, files in sorted(grouped.items())]
    return [DetectedConfig("default", _builder_for(data_paths), {}, splits)]
