# Convert YOLO detection data for image preview

Data Studio and the Hugging Face Dataset Viewer can preview an object-detection
dataset when images are stored in an ImageFolder repository and each split has a
`metadata.jsonl` file. Raw YOLO `labels/*.txt` files are useful to training
frameworks, but they do not tell a generic dataset viewer which image and
annotations form one row.

Use this repository shape:

```text
dataset/
├── README.md
├── train/
│   ├── metadata.jsonl
│   └── images/
│       └── example.jpg
├── validation/
│   ├── metadata.jsonl
│   └── images/
└── test/
    ├── metadata.jsonl
    └── images/
```

Each JSON Lines record represents one image:

```json
{"file_name":"images/example.jpg","image_id":"train/example","width":1280,"height":720,"objects":{"id":[0],"bbox":[[100.0,80.0,240.0,120.0]],"area":[28800.0],"category":[0],"category_name":["plate"]}}
```

Important rules:

- Use `file_name` for the image path, relative to the split's
  `metadata.jsonl`.
- Store boxes as pixel-space COCO boxes: `[x_min, y_min, width, height]`.
- Keep parallel `objects` arrays the same length.
- Use the conventional directory name `validation`; `valid` and `val` are also
  recognized by Data Studio, but `validation` is more portable.
- Make the filename extension match the actual image bytes. Upload validation
  rejects, for example, PNG bytes stored under a `.jpg` path.
- Include a Dataset Card (`README.md`) with license, task, provenance, class
  names, and any restrictions users need to know.

## Run the converter

The script needs Python 3.11+, PyYAML, and Pillow. Those dependencies are already
included in the Data Studio environment.

```bash
python examples/yolo_imagefolder/convert_yolo_imagefolder.py \
  /path/to/yolo-dataset \
  /path/to/preview-dataset
```

For the local license-plate example:

```bash
python examples/yolo_imagefolder/convert_yolo_imagefolder.py \
  /root/tungn197/AI-Traffic-Analysis/data/plate_2026 \
  /root/tungn197/AI-Traffic-Analysis/data/plate_2026_imagefolder \
  --image-mode hardlink
```

`--image-mode hardlink` avoids duplicating image bytes when input and output are
on the same filesystem. Use the default `copy` mode for a self-contained output
that may be moved independently. The converter:

1. reads split paths and class names from `data.yaml`;
2. validates image bytes and corrects mismatched output extensions;
3. converts normalized YOLO boxes to clipped pixel-space COCO boxes;
4. creates one metadata row per image, including background images; and
5. writes a Dataset Card with class and split summaries.

The input tree is never changed. An existing output is rejected unless
`--overwrite` is supplied. Use `--require-labels` when every image must have a
matching label file; otherwise a missing label becomes an empty `objects`
record.

See [API_USAGE.md](API_USAGE.md) to upload and verify the converted repository.
