import json
import subprocess
import sys
from pathlib import Path

from data_studio_api.domain.layout import detect_layout
from data_studio_api.domain.preview import preview_split
from PIL import Image


def test_yolo_example_creates_previewable_imagefolder(tmp_path: Path) -> None:
    source = tmp_path / "source"
    image_directory = source / "valid" / "images"
    label_directory = source / "valid" / "labels"
    image_directory.mkdir(parents=True)
    label_directory.mkdir(parents=True)
    image_path = image_directory / "sample.jpg"
    Image.new("RGB", (20, 10), "white").save(image_path, format="PNG")
    (label_directory / "sample.txt").write_text("0 0.5 0.5 0.5 0.4\n", encoding="utf-8")
    (source / "data.yaml").write_text(
        "val: valid/images\nnc: 1\nnames: [plate]\n",
        encoding="utf-8",
    )
    output = tmp_path / "converted"

    subprocess.run(
        [
            sys.executable,
            "examples/yolo_imagefolder/convert_yolo_imagefolder.py",
            str(source),
            str(output),
        ],
        check=True,
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
    )

    metadata_path = output / "validation" / "metadata.jsonl"
    row = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert row == {
        "file_name": "images/sample.png",
        "image_id": "validation/sample",
        "width": 20,
        "height": 10,
        "objects": {
            "id": [0],
            "bbox": [[5.0, 3.0, 10.0, 4.0]],
            "area": [40.0],
            "category": [0],
            "category_name": ["plate"],
        },
    }
    paths = sorted(
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    )
    config = detect_layout(paths, {})[0]
    assert config.builder_name == "imagefolder"
    assert config.splits[0].name == "validation"

    preview = preview_split(output, config.splits[0].files, limit=10, builder_name="imagefolder")
    assert preview.rows[0]["file_name"] == {
        "_type": "image",
        "path": "validation/images/sample.png",
    }
