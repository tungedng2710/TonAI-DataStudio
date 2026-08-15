#!/usr/bin/env python3
"""Convert a YOLO detection dataset to metadata-backed ImageFolder format."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

SPLIT_KEYS = {"train": "train", "val": "validation", "validation": "validation", "test": "test"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
FORMAT_SUFFIXES = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
}


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    suffix: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert YOLO images and normalized labels into Hugging Face-compatible "
            "ImageFolder splits with metadata.jsonl files."
        )
    )
    parser.add_argument("input", type=Path, help="YOLO dataset root")
    parser.add_argument("output", type=Path, help="New ImageFolder repository root")
    parser.add_argument(
        "--data-yaml",
        type=Path,
        help="YOLO data YAML; defaults to INPUT/data.yaml",
    )
    parser.add_argument(
        "--image-mode",
        choices=("copy", "hardlink"),
        default="copy",
        help="Copy images or hard-link them into the output (default: copy)",
    )
    parser.add_argument(
        "--require-labels",
        action="store_true",
        help="Fail when an image has no matching label file instead of treating it as background",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not read YOLO data YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"YOLO data YAML {path} must contain a mapping")
    return value


def class_names(config: dict[str, Any]) -> list[str]:
    raw = config.get("names")
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        names = raw
    elif isinstance(raw, dict):
        try:
            pairs = sorted((int(key), str(value)) for key, value in raw.items())
        except (TypeError, ValueError) as exc:
            raise ValueError("YOLO class-name keys must be integer class IDs") from exc
        if [key for key, _ in pairs] != list(range(len(pairs))):
            raise ValueError("YOLO class-name IDs must be contiguous and start at zero")
        names = [value for _, value in pairs]
    else:
        raise ValueError("YOLO data YAML must define 'names' as a list or ID-to-name mapping")

    declared_count = config.get("nc")
    if declared_count is not None and int(declared_count) != len(names):
        raise ValueError(f"YOLO nc={declared_count} does not match {len(names)} class names")
    return names


def _directory_candidates(input_root: Path, yaml_path: Path, config: dict[str, Any]) -> list[Path]:
    candidates = [input_root, yaml_path.parent]
    configured_root = config.get("path")
    if isinstance(configured_root, str):
        path = Path(configured_root).expanduser()
        if not path.is_absolute():
            path = yaml_path.parent / path
        candidates.insert(0, path)
    return candidates


def resolve_split_directory(
    value: str, input_root: Path, yaml_path: Path, config: dict[str, Any]
) -> Path:
    requested = Path(value).expanduser()
    if requested.is_absolute() and requested.is_dir():
        return requested.resolve()
    for root in _directory_candidates(input_root, yaml_path, config):
        candidate = (root / requested).resolve()
        if candidate.is_dir():
            return candidate
    raise ValueError(f"Split directory {value!r} does not exist relative to the dataset root")


def split_directories(
    input_root: Path, yaml_path: Path, config: dict[str, Any]
) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for source_name, output_name in SPLIT_KEYS.items():
        raw = config.get(source_name)
        if raw is None or (source_name == "validation" and "val" in config):
            continue
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(
                f"YOLO split {source_name!r} must be a directory or list of directories"
            )
        result.setdefault(output_name, []).extend(
            resolve_split_directory(value, input_root, yaml_path, config) for value in values
        )
    if not result:
        raise ValueError("YOLO data YAML does not define train, val/validation, or test splits")
    return result


def inspect_image(path: Path) -> ImageInfo:
    try:
        with Image.open(path) as image:
            image.load()
            image_format = image.format or ""
            width, height = image.size
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid image {path}: {exc}") from exc
    suffix = FORMAT_SUFFIXES.get(image_format)
    if suffix is None:
        raise ValueError(f"Unsupported image format {image_format!r} in {path}")
    return ImageInfo(width=width, height=height, suffix=suffix)


def label_path(image_path: Path, image_directory: Path) -> Path:
    if image_directory.name.lower() == "images":
        return image_directory.parent / "labels" / f"{image_path.stem}.txt"
    return image_path.with_suffix(".txt")


def parse_objects(
    path: Path,
    width: int,
    height: int,
    names: list[str],
    require_labels: bool,
) -> dict[str, list[Any]]:
    objects: dict[str, list[Any]] = {
        "id": [],
        "bbox": [],
        "area": [],
        "category": [],
        "category_name": [],
    }
    if not path.exists():
        if require_labels:
            raise ValueError(f"Missing YOLO label file {path}")
        return objects

    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_number}: expected 5 YOLO fields, got {len(fields)}")
        try:
            category = int(fields[0])
            center_x, center_y, box_width, box_height = map(float, fields[1:])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: invalid numeric YOLO label") from exc
        if not 0 <= category < len(names):
            raise ValueError(f"{path}:{line_number}: class ID {category} is not declared")
        if not (
            0 <= center_x <= 1
            and 0 <= center_y <= 1
            and 0 < box_width <= 1
            and 0 < box_height <= 1
        ):
            raise ValueError(f"{path}:{line_number}: normalized YOLO coordinates must be in [0, 1]")

        x_min = max(0.0, (center_x - box_width / 2) * width)
        y_min = max(0.0, (center_y - box_height / 2) * height)
        x_max = min(float(width), (center_x + box_width / 2) * width)
        y_max = min(float(height), (center_y + box_height / 2) * height)
        pixel_width = max(0.0, x_max - x_min)
        pixel_height = max(0.0, y_max - y_min)
        objects["id"].append(len(objects["id"]))
        objects["bbox"].append([x_min, y_min, pixel_width, pixel_height])
        objects["area"].append(pixel_width * pixel_height)
        objects["category"].append(category)
        objects["category_name"].append(names[category])
    return objects


def transfer_image(source: Path, destination: Path, mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        os.link(source, destination)
    else:
        shutil.copy2(source, destination)


def unique_destination_name(image: Path, actual_suffix: str, used: set[str]) -> str:
    candidate = f"{image.stem}{actual_suffix}"
    if candidate in used:
        raise ValueError(
            f"Two source images map to the same output name {candidate!r}; rename them first"
        )
    used.add(candidate)
    return candidate


def write_split(
    output_root: Path,
    split_name: str,
    image_directories: list[Path],
    names: list[str],
    mode: str,
    require_labels: bool,
) -> tuple[int, int, int]:
    split_root = output_root / split_name
    split_root.mkdir(parents=True, exist_ok=False)
    used_names: set[str] = set()
    image_count = 0
    object_count = 0
    missing_labels = 0
    with (split_root / "metadata.jsonl").open("w", encoding="utf-8") as metadata:
        for image_directory in image_directories:
            images = sorted(
                path
                for path in image_directory.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
            for image_path in images:
                info = inspect_image(image_path)
                destination_name = unique_destination_name(image_path, info.suffix, used_names)
                destination = split_root / "images" / destination_name
                source_label = label_path(image_path, image_directory)
                if not source_label.exists():
                    missing_labels += 1
                objects = parse_objects(
                    source_label,
                    info.width,
                    info.height,
                    names,
                    require_labels,
                )
                transfer_image(image_path, destination, mode)
                row = {
                    "file_name": f"images/{destination_name}",
                    "image_id": f"{split_name}/{Path(destination_name).stem}",
                    "width": info.width,
                    "height": info.height,
                    "objects": objects,
                }
                metadata.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                image_count += 1
                object_count += len(objects["id"])
    return image_count, object_count, missing_labels


def normalized_license(config: dict[str, Any]) -> str | None:
    roboflow = config.get("roboflow")
    raw = roboflow.get("license") if isinstance(roboflow, dict) else None
    if not isinstance(raw, str):
        return None
    known = {
        "cc by 4.0": "cc-by-4.0",
        "cc0 1.0": "cc0-1.0",
        "mit": "mit",
        "apache 2.0": "apache-2.0",
    }
    return known.get(raw.strip().lower())


def write_dataset_card(
    output_root: Path,
    source_root: Path,
    names: list[str],
    split_counts: dict[str, tuple[int, int, int]],
    license_id: str | None,
) -> None:
    front_matter = ["---", "task_categories:", "  - object-detection"]
    if license_id:
        front_matter.extend([f"license: {license_id}"])
    front_matter.extend(["tags:", "  - yolo", "  - imagefolder", "---"])
    rows = "\n".join(
        f"| {split} | {counts[0]} | {counts[1]} |"
        for split, counts in split_counts.items()
    )
    class_rows = "\n".join(f"- `{index}`: {name}" for index, name in enumerate(names))
    rendered_front_matter = "\n".join(front_matter)
    card = f"""{rendered_front_matter}
# YOLO object-detection dataset

Converted from `{source_root.name}` into metadata-backed ImageFolder format.

| Split | Images | Objects |
| --- | ---: | ---: |
{rows}

## Classes

{class_rows}

Bounding boxes in `objects.bbox` use pixel-space COCO coordinates:
`[x_min, y_min, width, height]`.
"""
    (output_root / "README.md").write_text(card, encoding="utf-8")


def prepare_output(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise ValueError(f"Output {path} already exists; use --overwrite to replace it")
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"Refusing to replace non-directory output {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def main() -> int:
    args = parse_args()
    input_root = args.input.expanduser().resolve()
    yaml_path = (args.data_yaml or input_root / "data.yaml").expanduser().resolve()
    output_root = args.output.expanduser().resolve()
    if not input_root.is_dir():
        raise ValueError(f"Input dataset root {input_root} does not exist")
    if output_root == input_root or input_root in output_root.parents:
        raise ValueError("Output must be outside the input dataset tree")

    config = load_yaml(yaml_path)
    names = class_names(config)
    splits = split_directories(input_root, yaml_path, config)
    prepare_output(output_root, args.overwrite)
    counts: dict[str, tuple[int, int, int]] = {}
    try:
        for split_name, directories in splits.items():
            counts[split_name] = write_split(
                output_root,
                split_name,
                directories,
                names,
                args.image_mode,
                args.require_labels,
            )
        write_dataset_card(
            output_root,
            input_root,
            names,
            counts,
            normalized_license(config),
        )
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise

    for split_name, (images, objects, missing) in counts.items():
        print(
            f"{split_name}: {images} images, {objects} objects, "
            f"{missing} images without label files"
        )
    print(f"Wrote preview-compatible repository: {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
