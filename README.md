# TonAI Data Studio

TonAI Data Studio is a self-hosted repository and viewer for machine-learning datasets. It accepts
the folder contract used by the Hugging Face Dataset Hub: upload a repository with its `README.md`,
data shards, metadata, and media paths intact. The Studio preserves the source bytes, creates an
immutable content-addressed revision, and exposes the Dataset Card, rows, files, schema, statistics,
and revision history.

This repository currently implements the first runnable vertical slice from `AGENT.md`. Its
compatibility claims are intentionally narrower than the complete MVP; see [Current limits](#current-limits).

## What works

- Dataset repository creation under a namespace, with private/internal/public visibility metadata
- Folder upload from the browser while preserving every relative POSIX path
- Traversal, absolute-path, control-character, duplicate-path, symlink, size, and file-count checks
- UTF-8 Dataset Card parsing with safe YAML loading and sanitized Markdown rendering
- Card-declared `configs`, `config_name`, `data_files`, split/path mappings, and glob patterns
- Conventional train/validation/test detection, including sharded filenames
- Parquet, CSV, TSV, JSON, JSONL, TXT, ImageFolder, and image metadata layouts
- Bounded row previews, nested JSON values, Arrow-compatible schema display, and sample statistics
- Content-addressed RustFS objects, deterministic manifests, and idempotent immutable revisions
- Isolated internal Git repositories with DVC pointers and durable DVC cache publication
- Byte-identical streaming downloads through the authorized API boundary
- Optional dataset lifecycle stages and normalized custom tags
- URL-addressable revision/config/split views and a virtualized React data table
- PostgreSQL migrations, Redis/Celery worker wiring, and local Docker Compose deployment
- Local SQLite/filesystem adapters for fast development and tests

## Architecture

```text
Browser
  │
  ▼
React + Vite + Tailwind (apps/web)
  │ /api/v1
  ▼
FastAPI application service (apps/api)
  ├── PostgreSQL: repositories, revisions, layouts, previews, jobs
  ├── Git+DVC: immutable revision metadata and source-tree pointers
  ├── RustFS S3: immutable source objects, manifests, and the DVC remote cache
  ├── Redis/Celery: worker boundary (health task in this slice)
  └── PyArrow: bounded Parquet/schema inspection
```

Route handlers only handle transport concerns. Dataset Card parsing, layout detection, safe path
normalization, previews, and manifest generation live under
[`apps/api/data_studio_api/domain`](apps/api/data_studio_api/domain). Storage is behind local and S3
adapters. RustFS uses S3 path-style addressing, consistent with the
[official RustFS S3 guidance](https://docs.rustfs.com/integration/virtual).

## Run locally in the requested conda environment

Requirements: conda, Python 3.11+, Node 22+, and `uv`.

```bash
conda activate tungn197
uv pip install -e '.[dev]'
cd apps/web && npm ci && cd ../..
```

`uv.lock`, the exported `requirements.lock`, and `apps/web/package-lock.json` pin reproducible local
and container dependency graphs.

Start the API (SQLite and local object storage by default):

```bash
conda activate tungn197
uvicorn data_studio_api.main:app --reload --port 8000
```

In another terminal, start the web app:

```bash
conda activate tungn197
cd apps/web
npm run dev
```

Open <http://localhost:5173>. API documentation is at <http://localhost:8000/docs>.

## Run the service stack

The Compose stack includes the web app, API, worker, PostgreSQL, Redis, and a single-node RustFS
instance. RustFS ports `9000` (S3) and `9001` (console) are exposed for development by default;
set `RUSTFS_API_PORT` and `RUSTFS_CONSOLE_PORT` if either host port is already occupied.

```bash
cp .env.example .env
# Replace the placeholder database and RustFS secrets in .env.
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build
```

Open <http://localhost:3000>. The RustFS console is available at
<http://localhost:9001/rustfs/console/> (replace `9001` with `RUSTFS_CONSOLE_PORT` when overridden).
Migrations run before the API starts. Named volumes keep PostgreSQL, Redis, RustFS, internal Git
repositories, and upload-staging data across restarts.

To rebuild only the web interface without starting or recreating API, database, or RustFS
containers:

```bash
make compose-web
```

To stop the stack without deleting its named volumes:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

## Demo workflow

1. Select **New dataset**, enter a namespace and dataset name, and choose visibility. Dataset names
   are lowercased automatically, and whitespace between words becomes `-`.
2. Select **Upload revision** on the dataset page.
3. Choose one or more files, or select a compatible repository folder. Individual files are added
   at the repository root; folder uploads preserve relative paths without rewriting the source.
4. After validation, use **Dataset card**, **Data Studio**, **Files**, **Schema**, **Statistics**, and
   **Versions** to inspect the immutable revision.
5. Select any repository file to download and verify the preserved source object.

A compatible repository can be as simple as:

```text
sentiment/
├── README.md
└── data/
    ├── train-00000-of-00002.parquet
    ├── train-00001-of-00002.parquet
    └── test-00000-of-00001.parquet
```

The `README.md` may declare layouts explicitly:

```yaml
---
license: mit
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train-*.parquet
      - split: test
        path: data/test-*.parquet
---
# Sentiment dataset
```

Explicit invalid patterns fail with an actionable problem response; the ingestion layer does not
silently switch to a heuristic layout.

## API outline

All application endpoints live under `/api/v1`. The interactive OpenAPI document contains the full
request and response contracts. See the [API usage guide](docs/API_USAGE.md) for complete `curl`
examples covering authentication, tokens, repository creation, folder upload, previews, downloads,
updates, and deletion.

```text
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me
POST /auth/tokens
POST /datasets
GET  /datasets
GET  /datasets/{namespace}/{dataset}
PATCH /datasets/{namespace}/{dataset}
DELETE /datasets/{namespace}/{dataset}
POST /datasets/{namespace}/{dataset}/uploads
POST /uploads/{upload_id}/files
POST /uploads/{upload_id}/complete
GET  /datasets/{namespace}/{dataset}/revisions
GET  /datasets/{namespace}/{dataset}/tree/{revision}
GET  /datasets/{namespace}/{dataset}/blob/{revision}/{path}
GET  /datasets/{namespace}/{dataset}/archive/{revision}
GET  /datasets/{namespace}/{dataset}/viewer/{config}/{split}
GET  /datasets/{namespace}/{dataset}/statistics/{config}/{split}
```

Authentication uses signed HttpOnly session cookies for the web application. Passwords are stored as
salted PBKDF2-SHA256 hashes. Personal API tokens use `Authorization: Bearer ds_pat_...`; only their
SHA-256 hashes are persisted, and the raw value is returned only by the create-token response.

The first registered account becomes the workspace administrator and adopts repositories created
before the ownership migration. Later accounts own the datasets they create. Anonymous users can
list, browse, preview, and download public datasets. Signed-in users can also read internal datasets,
while private datasets and all mutations are restricted to the owner or workspace administrator.

## Configuration

Backend variables use the `DATA_STUDIO_` prefix. Important settings include:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_STUDIO_DATABASE_URL` | `sqlite:///./data/data-studio.db` | SQLAlchemy database URL |
| `DATA_STUDIO_STORAGE_BACKEND` | `local` | `local` or `s3` |
| `DATA_STUDIO_STORAGE_ROOT` | `./data/objects` | Local object adapter root |
| `DATA_STUDIO_STAGING_ROOT` | `./data/uploads` | Private streamed-upload staging root |
| `DATA_STUDIO_VERSIONING_ENABLED` | `true` | Publish every revision through internal Git+DVC |
| `DATA_STUDIO_VERSIONING_ROOT` | `./data/repositories` | Internal Git repositories and local DVC remote |
| `DATA_STUDIO_DVC_REMOTE_URL` | derived | Optional DVC remote override; defaults to RustFS for S3 |
| `DATA_STUDIO_S3_ENDPOINT_URL` | `http://rustfs:9000` | RustFS S3 endpoint |
| `DATA_STUDIO_S3_BUCKET` | `datasets` | Source/derived object bucket |
| `DATA_STUDIO_REDIS_URL` | `redis://localhost:6379/0` | Celery broker/result URL |
| `DATA_STUDIO_MAX_UPLOAD_BYTES` | 2 GiB | Maximum aggregate upload size |
| `DATA_STUDIO_MAX_FILE_BYTES` | 512 MiB | Maximum individual file size |
| `DATA_STUDIO_MAX_FILE_COUNT` | 10,000 | Maximum files per upload |
| `DATA_STUDIO_PREVIEW_ROWS` | 100 | Maximum persisted preview sample |
| `DATA_STUDIO_AUTH_SECRET_KEY` | development placeholder | Session-signing secret; replace in deployments |
| `DATA_STUDIO_AUTH_SESSION_TTL_SECONDS` | 604,800 | Browser session lifetime |
| `DATA_STUDIO_AUTH_COOKIE_SECURE` | `false` | Require HTTPS when sending the session cookie |
| `VITE_API_URL` | `/api/v1` | Browser API root |

`.env.example` contains placeholders only. RustFS credentials never reach the browser.
The three upload resource caps accept `0` to disable that cap for a trusted private deployment.
`RUSTFS_DATA_PATH`, `UPLOAD_STAGING_PATH`, and `VERSIONING_DATA_PATH` can bind persistent data to
host directories with enough capacity; omit them to use Docker named volumes.

## Verification

Always activate the conda environment before running project commands:

```bash
conda activate tungn197
ruff check apps/api tests migrations
ruff format --check apps/api tests migrations
mypy apps/api/data_studio_api
pytest

cd apps/web
npm run lint
npm test
npm run build
```

The integration suite proves create → upload → validate → DVC push → Git publication → preview →
byte-identical download, plus role enforcement and idempotent retries. Unit fixtures cover card YAML,
sanitization, traversal, split/config/shard detection, signature checks, deterministic manifests,
immutable revision refs, and byte-identical DVC restore.

## Security notes

- Uploaded Python is stored as an opaque source object and is never executed.
- No dataset loader is called with `trust_remote_code=True`.
- The API streams uploads and downloads; RustFS credentials remain server-side.
- Dataset Card HTML is sanitized before persistence and rendering.
- Parquet and common image extensions are checked against stable magic bytes.
- Derived rows are bounded and large/binary cells are replaced with typed references or truncation
  descriptors.

This slice has not yet undergone an external security review and should not be exposed directly to
untrusted networks.

## Current limits

The following items from the complete `AGENT.md` MVP are deliberately not claimed as finished:

- Ingestion and indexing currently complete inline in the API process. Celery/Redis are deployed and
  a smoke task exists, but the staged pipeline has not yet moved to retryable worker tasks.
- Preview rows are a bounded persisted sample. DuckDB pushdown, full-dataset cursors, global sort,
  and indexed text search are not implemented yet.
- Authentication supports local accounts, owner authorization, and scoped personal API tokens;
  external OIDC/SSO and organization membership are not implemented yet.
- Large browser uploads are streamed into the API, but multipart/resumable presigned S3 uploads are
  not implemented yet.
- The API accepts a Hugging Face-compatible repository contract; it is not a drop-in implementation
  of every `huggingface_hub` endpoint.

These boundaries are surfaced in UI capability metadata and documentation so a bounded preview is
never mistaken for a full-dataset query.
