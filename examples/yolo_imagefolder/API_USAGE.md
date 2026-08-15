# Upload the converted ImageFolder repository

These commands use the Data Studio REST API documented in
[`docs/API_USAGE.md`](../../docs/API_USAGE.md). Run them with Bash because the
batched upload example uses Bash arrays and `mapfile`.

## 1. Configure authentication

Create a write-capable personal API token in **Account settings**. Do not put the
token in a script or commit it to Git.

```bash
export STUDIO=http://localhost:3000
export API="$STUDIO/api/v1"
export TOKEN='ds_pat_replace_me'
export DATASET=tungn197/plate-2026-preview
export REPO=/root/tungn197/AI-Traffic-Analysis/data/plate_2026_imagefolder

ds() {
  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --header "Authorization: Bearer $TOKEN" \
    "$@"
}

ds_json() {
  ds --header 'Content-Type: application/json' "$@"
}
```

## 2. Create the dataset

```bash
ds_json \
  --data '{
    "namespace": "tungn197",
    "slug": "plate-2026-preview",
    "visibility": "private",
    "description": "License-plate detection data with previewable images",
    "data_stage": "raw"
  }' \
  "$API/datasets" \
  | jq
```

Skip this step when the dataset already exists and you are publishing another
immutable revision.

## 3. Open an upload

```bash
UPLOAD=$(
  ds_json \
    --data '{
      "data_stage": "raw",
      "commit_message": "Convert YOLO labels to previewable ImageFolder metadata"
    }' \
    "$API/datasets/$DATASET/uploads" \
  | jq --raw-output '.id'
)
```

## 4. Upload all files in batches

The API requires one `paths` field for every `files` field. The relative path is
the path stored in the immutable dataset repository.

```bash
mapfile -d '' FILES < <(find "$REPO" -type f -print0 | sort -z)
BATCH_SIZE=100

for ((start = 0; start < ${#FILES[@]}; start += BATCH_SIZE)); do
  form=()
  batch=("${FILES[@]:start:BATCH_SIZE}")
  for file in "${batch[@]}"; do
    relative=${file#"$REPO"/}
    form+=(--form "files=@$file")
    form+=(--form-string "paths=$relative")
  done
  ds "${form[@]}" "$API/uploads/$UPLOAD/files" >/dev/null
  printf 'Uploaded %d/%d files\n' "$((start + ${#batch[@]}))" "${#FILES[@]}"
done
```

Do not retry a batch blindly after an ambiguous network failure: repository
paths may already have been accepted, and duplicate paths are rejected. Check
`GET /uploads/$UPLOAD` first.

## 5. Publish the revision

```bash
FILE_COUNT=${#FILES[@]}

ds_json \
  --data "{\"expected_file_count\":$FILE_COUNT}" \
  "$API/uploads/$UPLOAD/complete?include_files=false" \
  | jq '{revision_id, status, commit_message}'
```

For a large repository, a reverse proxy can time out while the API continues
processing. Check the upload before retrying the idempotent publish operation:

```bash
ds "$API/uploads/$UPLOAD" | jq '{status, file_count, bytes_received}'
ds "$API/datasets/$DATASET/revisions" | jq
```

Wait until the upload is `complete` and the revision is `ready`.

## 6. Verify the preview

Discover the detected config and splits:

```bash
ds \
  --get \
  --data-urlencode 'revision=main' \
  "$API/datasets/$DATASET/configs" \
  | jq
```

Fetch several rows from the training split. `file_name` should be returned as an
image cell rather than a plain string:

```bash
ds \
  --get \
  --data-urlencode 'revision=main' \
  --data-urlencode 'limit=5' \
  "$API/datasets/$DATASET/viewer/default/train" \
  | jq '.rows'
```

Open `$STUDIO/datasets/$DATASET` and select **Data Studio** to view the image
rows. The table displays the image and keeps `objects.bbox`, `objects.category`,
and the other annotation fields available for inspection.
