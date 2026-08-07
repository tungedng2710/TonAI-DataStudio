# Data Studio API recipes

TonAI Data Studio has a REST API under `/api/v1`. This guide starts with a short
setup, then shows one copy-pasteable recipe per task.

The examples use `curl` and `jq` against the Compose deployment at
`http://localhost:3000`. Change `STUDIO` if your deployment uses another address.

## Quick setup

The easiest way to get a token is through the web app:

1. Sign in.
2. Open **Account settings**.
3. Under **Personal API tokens**, generate a token and copy it immediately.

Set three variables, then define two helpers so every later command stays short:

```bash
export STUDIO=http://localhost:3000
export API="$STUDIO/api/v1"
export TOKEN='ds_pat_paste_your_token_here'
export DATASET=owner/sentiment-demo

ds() {
  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --header "Authorization: Bearer $TOKEN" \
    "$@"
}

ds_json() {
  ds \
    --header 'Content-Type: application/json' \
    "$@"
}
```

- `ds` sends an authenticated request.
- `ds_json` does the same and marks the body as JSON.
- `jq` only formats or selects fields from a response; the API does not require it.

Keep tokens out of source control and shell scripts that will be shared. Use a
`read`-only token when a client never creates, uploads, updates, or deletes datasets.

## Repository compatibility

The upload API accepts Hugging Face-compatible dataset repository layouts. This
includes Dataset Cards with YAML front matter, declarative configs, conventional
train/validation/test splits, sharded data files, metadata files, and ImageFolder
structures.

Uploaded source paths and bytes are preserved. The Studio provides its own REST
API and does not implement the complete `huggingface_hub` protocol.

## Create a dataset

The namespace is usually your username. Visibility can be `private`, `internal`,
or `public`.

Dataset names are normalized when they are created. For example,
`License plate` becomes `license-plate`.

```bash
ds_json \
  --data '{
    "namespace": "owner",
    "slug": "sentiment-demo",
    "visibility": "private",
    "description": "Sentiment examples"
  }' \
  "$API/datasets" \
  | jq
```

The `--data` flag makes this a `POST` request, so a separate `--request POST` is
unnecessary.

## Upload files and publish a revision

Uploading has three steps: open an upload, send files, then publish it.

### 1. Open an upload

```bash
UPLOAD=$(
  ds_json \
    --data '{"data_stage":"raw"}' \
    "$API/datasets/$DATASET/uploads" \
  | jq --raw-output '.id'
)
```

When `commit_message` is omitted, the published revision uses its generated
revision ID as the message. To set a custom message, send a value such as
`{"commit_message":"Refresh training labels"}` when opening the upload.
The optional `data_stage` field sets the lifecycle stage recorded on the first
revision.

### 2. Send files

Each `files` entry needs a matching `paths` entry. Paths are relative to the
repository root and always use `/`.

```bash
ds \
  --form 'files=@README.md' \
  --form 'paths=README.md' \
  --form 'files=@data/train.parquet' \
  --form 'paths=data/train.parquet' \
  "$API/uploads/$UPLOAD/files" \
  | jq
```

Large folders can be split across several requests. Do not send the same
repository path twice.

### 3. Publish

```bash
REVISION=$(
  ds_json \
    --data '{"expected_file_count":2}' \
    "$API/uploads/$UPLOAD/complete?include_files=false" \
  | jq --raw-output '.revision_id'
)

echo "Published revision: $REVISION"
```

Publishing is content-addressed and idempotent. Retrying the same completed
repository tree returns the existing immutable revision.

### Change data stage

Changing stage creates a metadata-only immutable revision that reuses the
existing source objects, previews, and DVC data. A commit message is required.

```bash
ds_json \
  --data '{
    "data_stage": "raw_validated",
    "commit_message": "Validated the raw collection"
  }' \
  "$API/datasets/$DATASET/stage" \
  | jq
```

## Browse datasets

List every dataset visible to the current token:

```bash
ds \
  "$API/datasets" \
  | jq '.items[] | {
      name: (.namespace + "/" + .slug),
      visibility,
      description
    }'
```

Read one dataset or its revision history:

```bash
ds \
  "$API/datasets/$DATASET" \
  | jq

ds \
  "$API/datasets/$DATASET/revisions" \
  | jq
```

List repository files:

```bash
ds \
  --get \
  --data-urlencode 'offset=0' \
  --data-urlencode 'limit=100' \
  "$API/datasets/$DATASET/tree/main/page" \
  | jq
```

Use `main` for the latest revision or replace it with an immutable revision ID.

## Preview rows

First discover the config and split names detected from the repository:

```bash
ds \
  --get \
  --data-urlencode 'revision=main' \
  "$API/datasets/$DATASET/configs" \
  | jq
```

Then fetch a small page. This example assumes the config is `default` and the
split is `train`:

```bash
ds \
  --get \
  --data-urlencode 'revision=main' \
  --data-urlencode 'limit=10' \
  "$API/datasets/$DATASET/viewer/default/train" \
  | jq '.rows'
```

Select columns and filter rows when needed:

```bash
ds \
  --get \
  --data-urlencode 'revision=main' \
  --data-urlencode 'columns=text,label' \
  --data-urlencode 'filter={"column":"label","op":"eq","value":1}' \
  "$API/datasets/$DATASET/viewer/default/train" \
  | jq '.rows'
```

Supported filter operations are `eq`, `ne`, `contains`, `gt`, `gte`, `lt`, and
`lte`. Preview rows are a bounded sample; check `capabilities` in the response
before assuming a full-dataset operation.

## Download data

### Download the complete repository

This downloads the latest source tree as a ZIP while preserving every original path:

```bash
ds \
  --location \
  --output sentiment-demo.zip \
  "$API/datasets/$DATASET/archive/main"

unzip -l sentiment-demo.zip
```

For a reproducible snapshot, replace `main` with an immutable revision ID.

### Download one file

```bash
ds \
  --location \
  --output train.parquet \
  "$API/datasets/$DATASET/blob/main/data/train.parquet"
```

Public datasets do not need a token. Download one with ordinary `curl`:

```bash
curl \
  --fail-with-body \
  --location \
  --output public-data.zip \
  "$API/datasets/public/demo/archive/main"
```

The Studio preserves Hugging Face-compatible layouts but does not implement the
Hub download protocol, so use these REST endpoints instead of `hf download`.

## Update or delete a dataset

Update only the fields that need to change:

```bash
ds_json \
  --request PATCH \
  --data '{
    "description": "Updated description",
    "visibility": "internal",
    "data_stage": "training_ready",
    "tags": ["license-plates", "vietnam"]
  }' \
  "$API/datasets/$DATASET" \
  | jq
```

`data_stage` can be `raw`, `raw_validated`, `prelabeled`, `human_labeled`,
`verified`, `training_ready`, `rejected`, or `null`. Optional tags are
lowercased, spaces become hyphens, and duplicates are removed.

Renaming changes the URL. Update `DATASET` after changing the slug:

```bash
ds_json \
  --request PATCH \
  --data '{"slug":"sentiment-v2"}' \
  "$API/datasets/$DATASET" \
  | jq

export DATASET=owner/sentiment-v2
```

Deletion permanently removes the dataset and its stored source and derived objects:

```bash
ds \
  --request DELETE \
  "$API/datasets/$DATASET"
```

## Optional: sign in from the command line

Most people can generate a token in **Account settings** and skip this section.
For a fully terminal-based workflow, sign in to a cookie jar, then create a token:

```bash
curl \
  --fail-with-body \
  --silent \
  --show-error \
  --cookie-jar data-studio.cookies \
  --header 'Content-Type: application/json' \
  --data '{
    "username": "owner",
    "password": "your-password"
  }' \
  "$API/auth/login" \
  | jq

TOKEN=$(
  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --cookie data-studio.cookies \
    --header 'Content-Type: application/json' \
    --data '{
      "name": "local-cli",
      "scopes": ["read", "write"]
    }' \
    "$API/auth/tokens" \
  | jq --raw-output '.token'
)

export TOKEN
```

The first registered account becomes the workspace administrator. To create it
through the API, send the same payload to `$API/auth/register` instead of
`$API/auth/login`.

## Understand errors

Errors use a consistent problem document:

```json
{
  "title": "Access denied",
  "status": 403,
  "detail": "Only the dataset owner can change this dataset.",
  "code": "forbidden",
  "instance": "/api/v1/datasets/owner/sentiment-demo"
}
```

Because the examples use `--fail-with-body`, `curl` exits unsuccessfully without
hiding that useful response body.

| Status | Meaning |
| --- | --- |
| `401` | The credential is missing, invalid, or expired. |
| `403` | The token lacks the required scope or the user does not own the dataset. |
| `404` | The requested resource does not exist or is not visible. |
| `409` | A username, email, dataset, or upload conflicts with existing state. |
| `422` | The request body or uploaded repository is invalid. |

Interactive OpenAPI documentation is available at `http://localhost:8001/docs`
for the default Compose API port, or at `http://localhost:8000/docs` when running
the API development server directly.
