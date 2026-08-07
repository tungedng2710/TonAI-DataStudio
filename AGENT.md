# Data Studio Coding Agent Instructions

## 1. Mission

Build a self-hosted Data Studio for managing, versioning, exploring, and sharing machine-learning datasets.

The product should feel familiar to users of the Hugging Face Dataset Hub and Dataset Viewer. A user who already has a Hugging Face-compatible dataset repository must be able to upload that repository to this Studio without reorganizing or converting the data.

The core stack is:

- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- Frontend: React, Vite, TypeScript, Tailwind CSS
- Metadata database: PostgreSQL
- Object storage: RustFS through its S3-compatible API
- Dataset versioning: DVC with an S3 remote hosted by RustFS
- Preview/query engine: PyArrow, Polars, and DuckDB
- Background processing: Celery and Redis
- Local deployment: Docker Compose

Treat this file as the primary implementation specification unless a newer explicit user instruction overrides it.

## 2. Product Definition

This project is a private dataset hub with:

- Hugging Face-compatible dataset repository layouts
- Dataset cards rendered from `README.md`
- Repository files and immutable revisions
- Config/subset and split detection
- Browser-based dataset previews
- Schema and basic statistics
- Upload and download APIs
- Internal DVC-backed versioning
- RustFS-backed object storage

Compatibility means that the Studio accepts the same repository structure and declarative data formats commonly accepted by the Hugging Face Dataset Hub. It does not initially mean complete protocol compatibility with every `huggingface_hub` endpoint.

## 3. MVP Scope

Implement the following vertical slice first:

1. Create a dataset repository under a namespace.
2. Upload a Hugging Face-compatible local folder.
3. Preserve relative paths exactly.
4. Read Dataset Card metadata and data configuration from `README.md`.
5. Detect configs/subsets and train/validation/test splits.
6. Support Parquet, CSV, TSV, JSON, JSONL, TXT, and ImageFolder repositories.
7. Store source objects in RustFS.
8. Create an immutable revision using Git metadata and DVC pointers.
9. Generate a preview index asynchronously.
10. Browse the Dataset Card, data rows, files, schema, statistics, and versions in the web UI.
11. Download a file or a complete revision.

Defer these features unless explicitly requested:

- Full drop-in Hugging Face Hub API compatibility
- Git smart HTTP server and direct `git push`
- Arbitrary uploaded Python dataset scripts
- Audio/video playback and transcoding
- Dataset editing in the browser
- Pull requests, discussions, likes, and social features
- Real-time collaborative annotation
- Kubernetes deployment

## 4. Non-Negotiable Compatibility Rules

The ingestion layer must preserve and understand repositories such as:

```text
my-dataset/
├── README.md
├── data/
│   ├── train-00000-of-00002.parquet
│   ├── train-00001-of-00002.parquet
│   └── test-00000-of-00001.parquet
├── images/
│   ├── 000001.jpg
│   └── 000002.jpg
└── metadata.jsonl
```

Support:

- YAML front matter in `README.md`
- Dataset Card Markdown content
- `configs` declarations
- `config_name`
- `data_files`
- Explicit split/path mappings
- Automatic split detection from conventional file and directory names
- Sharded file names
- `metadata.csv`, `metadata.jsonl`, and `metadata.parquet`
- Relative media paths referenced by metadata rows
- ImageFolder label inference from directory names
- Revisions identified by immutable IDs

Do not mutate uploaded source files during ingestion. Derived files, normalized manifests, previews, thumbnails, and statistics must be stored separately.

## 5. Security Boundary

Uploaded repositories are untrusted input.

- Never execute an uploaded `.py` file.
- Do not enable remote/custom dataset loading code in the MVP.
- Do not use `trust_remote_code=True`.
- Reject archive path traversal, absolute paths, symlink escapes, and unsafe filenames.
- Enforce configurable upload, extracted-size, row-size, and file-count limits.
- Validate MIME type and file signatures where relevant; do not trust extensions alone.
- Stream uploads and downloads. Do not load large files completely into memory.
- Use presigned S3 URLs for large object transfer where possible.
- Do not expose RustFS credentials to the browser.
- Do not log access tokens, credentials, presigned URLs, or raw sensitive dataset rows.
- Render Dataset Card Markdown using a sanitizer. Raw HTML must not enable script execution.
- Run preview/index jobs with CPU, memory, time, and temporary-disk limits.

## 6. Architecture

Use a monorepo:

```text
data-studio/
├── apps/
│   ├── api/
│   ├── web/
│   └── worker/
├── packages/
│   └── shared/
├── infrastructure/
│   ├── docker-compose.yml
│   └── rustfs/
├── dataset-repositories/
├── tests/
├── .env.example
├── Makefile
└── README.md
```

The logical services are:

- Web: user interface only; never talks directly to PostgreSQL or RustFS using permanent credentials.
- API: authentication, authorization, repository metadata, upload orchestration, browsing, and signed URL issuance.
- Worker: validation, repository parsing, DVC operations, preview generation, thumbnails, schema inference, and statistics.
- PostgreSQL: operational metadata and job state.
- RustFS: source objects, DVC object cache, derived previews, thumbnails, and exports.
- Redis: job queue and short-lived coordination only; it is not the source of truth.

Keep business logic out of FastAPI route handlers. Routes validate transport-level input and call application services.

## 7. Storage and Versioning Model

Users should not need to install or understand DVC. DVC is an internal implementation detail.

For each published revision:

1. Receive or finalize source uploads.
2. Validate the repository tree.
3. Store immutable source objects in RustFS.
4. Generate a deterministic repository manifest containing paths, sizes, checksums, media types, and object keys.
5. Track the manifest or materialized dataset path with DVC.
6. Push DVC objects to the RustFS S3 remote.
7. Commit the Dataset Card, manifest, and DVC pointer files to the dataset's internal Git repository.
8. Record the Git commit and DVC revision in PostgreSQL.
9. Queue indexing and preview generation.
10. Mark the revision ready only after required processing succeeds.

Use separate RustFS bucket/prefix concerns:

```text
datasets/source/{namespace}/{dataset}/{content-hash}/...
datasets/derived/{namespace}/{dataset}/{revision}/...
dvc/cache/...
uploads/staging/{upload-id}/...
```

Do not use a mutable object path as the identity of a revision. Prefer content hashes and immutable object keys.

Make revision creation idempotent. Retrying a failed publish operation must not create duplicate revisions or corrupt the repository.

## 8. Core Domain Model

At minimum, model these entities:

### User

- `id`
- `username`
- `display_name`
- `email`
- `password_hash` or external identity reference
- `created_at`

### Namespace

- `id`
- `slug`
- `display_name`
- `owner_type`
- `created_at`

### DatasetRepository

- `id`
- `namespace_id`
- `slug`
- `visibility`: private, internal, public
- `description`
- `default_branch`
- `created_by`
- `created_at`
- `updated_at`

Enforce uniqueness on `(namespace_id, slug)`.

### DatasetRevision

- `id`
- `repository_id`
- `parent_revision_id`
- `branch`
- `commit_message`
- `git_commit`
- `dvc_revision`
- `manifest_object_key`
- `status`: uploading, validating, indexing, ready, failed
- `error_code`
- `error_message`
- `created_by`
- `created_at`

### RepositoryFile

- `id`
- `revision_id`
- `path`
- `size_bytes`
- `sha256`
- `media_type`
- `storage_object_key`
- `is_previewable`

Enforce normalized, unique paths within each revision.

### DatasetConfig

- `id`
- `revision_id`
- `name`
- `builder_name`
- `builder_parameters`

### DatasetSplit

- `id`
- `config_id`
- `name`
- `data_files`
- `num_rows`
- `num_bytes`
- `schema_json`
- `preview_object_key`
- `statistics_object_key`

### ProcessingJob

- `id`
- `repository_id`
- `revision_id`
- `job_type`
- `status`
- `progress`
- `attempt_count`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

Use UUIDs or ULIDs consistently. Store timestamps in UTC.

## 9. Repository Manifest

Define and version a deterministic manifest schema. Example:

```json
{
  "manifest_version": 1,
  "repository": "edward/example-dataset",
  "parent_revision": null,
  "files": [
    {
      "path": "data/train-00000-of-00001.parquet",
      "size_bytes": 123456,
      "sha256": "...",
      "media_type": "application/vnd.apache.parquet",
      "object_key": "datasets/source/..."
    }
  ]
}
```

Sort files by normalized path before serialization. Use stable JSON serialization so identical inputs produce identical manifest hashes.

## 10. Ingestion Pipeline

Implement ingestion as explicit stages:

1. `receive`: obtain uploaded objects or register an import.
2. `validate_tree`: validate paths, counts, sizes, file types, and checksums.
3. `parse_card`: parse and validate `README.md` YAML front matter and Markdown.
4. `detect_layout`: find candidate builders, configs, splits, shards, and metadata files.
5. `inspect_schema`: infer Arrow-compatible features without reading the entire dataset where possible.
6. `commit_revision`: create manifest, DVC state, Git commit, and database revision atomically from the application's perspective.
7. `build_preview`: generate bounded preview/index artifacts.
8. `compute_statistics`: calculate safe, bounded column statistics.
9. `finalize`: mark the revision ready.

Each stage must be observable and retryable. Store machine-readable error codes and human-readable messages.

If Dataset Card configuration is present, use it before heuristic detection. If explicit configuration is invalid, return a clear error rather than silently choosing a different layout.

## 11. Preview and Query Rules

Use Arrow-compatible schemas as the common internal representation.

- Prefer DuckDB predicate/projection pushdown for Parquet.
- Use Polars/PyArrow for schema inspection and conversions.
- Do not convert entire large datasets merely to display the first page.
- Generate derived Parquet only when the source format is inefficient for repeated previews.
- Preserve nested lists and structs in the API; do not stringify them permanently.
- Return large binary/media values as typed references, not base64 embedded in row JSON.
- Generate bounded thumbnails for images and cache them in RustFS.
- Enforce maximum cell payload sizes in preview responses.
- Use cursor or stable offset pagination tied to a specific immutable revision.

The preview API must support:

- Selecting config and split
- Pagination
- Column projection
- Basic typed filters
- Sorting when supported efficiently
- Text search for bounded/indexed data
- Raw structured value inspection
- Image thumbnails and full-object signed URLs

Return capability metadata when an operation such as global sorting is unavailable for a very large or streaming dataset.

## 12. API Design

Use versioned routes under `/api/v1`.

Minimum endpoints:

```text
POST   /api/v1/datasets
GET    /api/v1/datasets/{namespace}/{dataset}
PATCH  /api/v1/datasets/{namespace}/{dataset}

POST   /api/v1/datasets/{namespace}/{dataset}/uploads
POST   /api/v1/uploads/{upload_id}/complete
GET    /api/v1/uploads/{upload_id}

GET    /api/v1/datasets/{namespace}/{dataset}/revisions
GET    /api/v1/datasets/{namespace}/{dataset}/revisions/{revision}
GET    /api/v1/datasets/{namespace}/{dataset}/tree/{revision}
GET    /api/v1/datasets/{namespace}/{dataset}/blob/{revision}/{path:path}

GET    /api/v1/datasets/{namespace}/{dataset}/configs
GET    /api/v1/datasets/{namespace}/{dataset}/viewer/{config}/{split}
GET    /api/v1/datasets/{namespace}/{dataset}/statistics/{config}/{split}

GET    /api/v1/jobs/{job_id}
```

Use RFC 7807-style problem responses or an equally consistent error envelope. Never expose internal stack traces.

Document all APIs through OpenAPI. Add examples for upload creation, upload completion, preview filters, and pagination.

Design the upload API so a future `studio_hub` client can provide methods similar to:

```python
api.create_repo(repo_id="edward/my-dataset", repo_type="dataset")
api.upload_file(...)
api.upload_folder(...)
api.create_commit(...)
```

Do not claim full `huggingface_hub` compatibility until contract tests prove it.

## 13. Frontend Requirements

Use React with strict TypeScript. Prefer reusable components and URL-addressable state.

Dataset routes should resemble:

```text
/datasets/{namespace}/{dataset}
/datasets/{namespace}/{dataset}/viewer/{config}/{split}
/datasets/{namespace}/{dataset}/tree/{revision}
/datasets/{namespace}/{dataset}/blob/{revision}/{path}
/datasets/{namespace}/{dataset}/settings
```

Dataset page tabs:

- Dataset card
- Data Studio
- Files and versions
- Schema
- Statistics
- Settings

The Data Studio view must include:

- Config/subset selector
- Split selector
- Revision selector
- Virtualized table
- Column type indicators
- Filter and search controls
- Loading, empty, partial, and error states
- Expandable nested values
- Image thumbnails
- Copyable row JSON

Keep revision, config, split, pagination, filters, and selected columns in the URL where practical so views can be shared and restored.

The interface may be inspired by Hugging Face but must not copy protected branding, logos, or exact visual assets.

## 14. Authentication and Authorization

Implement a simple development-ready authentication boundary without embedding it deeply into business logic.

Authorization roles:

- Reader: view and download
- Contributor: upload and create revisions
- Admin: repository settings, visibility, and membership

Every repository read and write must go through authorization checks, including signed URL creation and background job initiation.

Use scoped API tokens suitable for CLI uploads. Store only token hashes. Show a token only once when created.

## 15. Observability

Use structured logs with correlation IDs.

Track at least:

- Upload bytes and duration
- Validation duration
- Indexing duration
- Preview latency
- Queue depth
- Job retries/failures
- RustFS and PostgreSQL errors
- Per-revision processing status

Do not include secrets or raw row content in telemetry.

## 16. Testing Requirements

Testing is part of the implementation, not a follow-up task.

### Unit tests

- README YAML parsing
- Dataset Card validation
- Split/config detection
- Shard name detection
- Path normalization and traversal rejection
- Manifest determinism
- Schema serialization
- Filter validation
- Authorization decisions

### Integration tests

- PostgreSQL migrations
- RustFS/S3 upload, range read, and download
- DVC remote push/pull against RustFS
- Celery job execution and retry
- Full upload-to-ready workflow
- Failed ingestion cleanup/retry

### Compatibility fixtures

Maintain small fixture repositories for:

- Parquet with train/test shards
- CSV with automatic splits
- JSONL with nested fields
- README-defined configs and splits
- ImageFolder with inferred labels
- Image metadata with relative paths
- Invalid YAML
- Missing referenced file
- Malicious archive paths
- Oversized preview cell

### End-to-end tests

At minimum, prove that a user can:

1. Start the stack with Docker Compose.
2. Create a repository.
3. Upload a fixture repository.
4. Observe processing status.
5. View its Dataset Card.
6. Select config and split.
7. Browse rows and images.
8. Inspect files and revisions.
9. Download the original file.

## 17. Definition of Done for the MVP

The MVP is complete only when:

- `docker compose up` starts all required services.
- Database migrations run reproducibly.
- RustFS is configured as both object storage and DVC S3 remote.
- A Hugging Face-compatible repository can be uploaded without conversion.
- At least the required compatibility fixtures ingest correctly.
- Source files remain byte-identical after upload/download.
- Every publish creates an immutable revision.
- Dataset Card, files, versions, schema, statistics, and preview pages work.
- Image references render through authorized signed URLs.
- Failed jobs expose actionable errors and can be retried safely.
- Unit, integration, and end-to-end tests pass.
- The root README contains setup, architecture, configuration, and demo instructions.
- `.env.example` contains placeholders only and no real credentials.

## 18. Implementation Order

Work in small, runnable vertical slices:

1. Bootstrap monorepo, linting, formatting, tests, and Docker Compose.
2. Add PostgreSQL models, migrations, repository CRUD, and basic UI shell.
3. Add RustFS client and resumable/presigned upload flow.
4. Add safe tree validation and deterministic manifests.
5. Add DVC/Git revision creation and restore tests.
6. Add README Dataset Card parser and renderer.
7. Add Parquet preview end to end.
8. Add CSV/JSONL normalization and previews.
9. Add configs, splits, and sharded files.
10. Add ImageFolder and image metadata previews.
11. Add statistics, revision browsing, permissions, and hardening.

After every slice:

- Run the relevant tests.
- Keep Docker Compose usable.
- Update documentation when behavior or setup changes.
- Avoid leaving placeholder endpoints that return misleading success responses.

## 19. Coding Standards

- Use Python type hints throughout backend code.
- Use strict TypeScript; avoid `any` unless isolated and justified.
- Use Pydantic models at API boundaries.
- Separate domain models, persistence models, and transport schemas.
- Use dependency injection for storage, database, queue, and version-control adapters.
- Keep infrastructure-specific code behind interfaces.
- Prefer explicit transactions and idempotency keys for publish operations.
- Use Alembic for every schema change.
- Use generated API types or a checked client contract for frontend/backend integration.
- Format and lint code automatically in CI.
- Add tests for every bug fix.
- Avoid premature abstraction, but do not couple core domain logic directly to FastAPI, Celery, DVC commands, or S3 SDK calls.

Recommended tools:

- Python: `uv`, Ruff, mypy or pyright, pytest
- Frontend: ESLint, Prettier, Vitest, React Testing Library, Playwright
- API client: generated from OpenAPI where practical

## 20. Agent Working Rules

Before coding:

1. Inspect the existing repository and current changes.
2. Read all applicable local instruction files.
3. Do not overwrite unrelated user work.
4. Summarize the current architecture and propose the smallest next vertical slice.

While coding:

- Prefer working code over speculative scaffolding.
- Do not silently change the product scope.
- Make reasonable reversible decisions and document them.
- Ask before taking destructive actions or adopting a materially different architecture.
- Keep secrets out of source control.
- Do not add a dependency when the standard library or an existing dependency is adequate.
- Use official documentation for behavior that may have changed.
- Preserve compatibility fixtures as regression tests.

Before declaring completion:

1. Run formatting and static checks.
2. Run relevant unit and integration tests.
3. Exercise the affected workflow end to end when possible.
4. Report what changed, what was verified, and any remaining limitation.
5. Never describe an untested compatibility claim as complete.

## 21. Key Product Principle

The user-facing contract is the Hugging Face-compatible dataset repository. RustFS, PostgreSQL, Git, DVC, Arrow, DuckDB, and background jobs are implementation details that should make that contract reliable, secure, and scalable without forcing users to learn the internal storage system.
