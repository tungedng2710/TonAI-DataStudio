import json
from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as parquet
from data_studio_api.config import get_settings
from fastapi.testclient import TestClient
from PIL import Image


def _register(client: TestClient, username: str = "owner") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "secure-password"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_repository(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/v1/datasets",
        json={
            "namespace": "research",
            "slug": "sentiment",
            "visibility": "internal",
            "description": "Small sentiment fixture",
        },
    )
    assert response.status_code == 201, response.text


def _upload_fixture(client: TestClient) -> dict:
    create = client.post(
        "/api/v1/datasets/research/sentiment/uploads",
        json={},
    )
    assert create.status_code == 201, create.text
    upload_id = create.json()["id"]
    card = b"""---
license: mit
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train-*.jsonl
      - split: test
        path: data/test.jsonl
---
# Sentiment demo

Rows uploaded without conversion.
"""
    train = (
        b'{"text":"excellent","label":1,"meta":{"lang":"en"}}\n'
        b'{"text":"bad","label":0,"meta":{"lang":"en"}}\n'
    )
    test = b'{"text":"fine","label":1,"meta":{"lang":"en"}}\n'
    files = [
        ("files", ("README.md", card, "text/markdown")),
        ("files", ("train.jsonl", train, "application/x-ndjson")),
        ("files", ("test.jsonl", test, "application/x-ndjson")),
        ("paths", (None, "README.md")),
        ("paths", (None, "data/train-00000-of-00001.jsonl")),
        ("paths", (None, "data/test.jsonl")),
    ]
    uploaded = client.post(f"/api/v1/uploads/{upload_id}/files", files=files)
    assert uploaded.status_code == 200, uploaded.text
    complete = client.post(f"/api/v1/uploads/{upload_id}/complete", json={"expected_file_count": 3})
    assert complete.status_code == 200, complete.text
    return {"revision": complete.json(), "train": train}


def test_upload_to_viewer_and_byte_identical_download(client: TestClient) -> None:
    _create_repository(client)
    uploaded = _upload_fixture(client)
    revision = uploaded["revision"]

    assert revision["status"] == "ready"
    assert revision["commit_message"] == revision["revision_id"]
    assert len(revision["git_commit"]) == 40
    assert revision["dvc_revision"].startswith("md5:")
    assert len(revision["source_object_set_checksum"]) == 64
    assert revision["card_metadata"]["license"] == "mit"
    assert [config["name"] for config in revision["configs"]] == ["default"]
    assert {split["name"] for split in revision["configs"][0]["splits"]} == {"train", "test"}

    viewer = client.get(
        "/api/v1/datasets/research/sentiment/viewer/default/train",
        params={"revision": revision["revision_id"], "limit": 1},
    )
    assert viewer.status_code == 200, viewer.text
    assert viewer.json()["rows"] == [{"text": "excellent", "label": 1, "meta": {"lang": "en"}}]
    assert viewer.json()["row_indices"] == [0]
    assert viewer.json()["available_rows"] == 2
    assert viewer.json()["capabilities"]["preview_is_bounded"] is False

    download = client.get(
        f"/api/v1/datasets/research/sentiment/blob/{revision['revision_id']}/"
        "data/train-00000-of-00001.jsonl"
    )
    assert download.status_code == 200
    assert download.content == uploaded["train"]
    assert download.headers["content-disposition"].startswith("attachment;")

    inline = client.get(
        f"/api/v1/datasets/research/sentiment/blob/{revision['revision_id']}/"
        "data/train-00000-of-00001.jsonl",
        params={"inline": True},
    )
    assert inline.headers["content-disposition"].startswith("inline;")

    dataset = client.get("/api/v1/datasets/research/sentiment").json()
    assert dataset["latest_revision"]["revision_id"] == revision["revision_id"]

    lightweight = client.get(
        f"/api/v1/datasets/research/sentiment/revisions/{revision['revision_id']}",
        params={"include_files": False},
    )
    assert lightweight.status_code == 200
    assert lightweight.json()["files"] == []
    assert lightweight.json()["configs"][0]["name"] == "default"

    file_page = client.get(
        f"/api/v1/datasets/research/sentiment/tree/{revision['revision_id']}/page",
        params={"limit": 1, "search": "train"},
    )
    assert file_page.status_code == 200
    assert file_page.json()["total"] == 1
    assert file_page.json()["items"][0]["path"] == "data/train-00000-of-00001.jsonl"


def test_viewer_pages_and_filters_rows_beyond_the_ingestion_preview(
    client: TestClient,
) -> None:
    _create_repository(client)
    create = client.post(
        "/api/v1/datasets/research/sentiment/uploads",
        json={"commit_message": "Upload more than one preview page"},
    )
    assert create.status_code == 201, create.text
    upload_id = create.json()["id"]
    content = b"".join(
        (
            json.dumps(
                {
                    "id": index,
                    "text": "find-this-row" if index == 129 else f"row-{index}",
                }
            ).encode()
            + b"\n"
        )
        for index in range(130)
    )
    uploaded = client.post(
        f"/api/v1/uploads/{upload_id}/files",
        files=[
            ("files", ("train.jsonl", content, "application/x-ndjson")),
            ("paths", (None, "train.jsonl")),
        ],
    )
    assert uploaded.status_code == 200, uploaded.text
    complete = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"expected_file_count": 1},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["commit_message"] == "Upload more than one preview page"
    revision_id = complete.json()["revision_id"]
    viewer_path = "/api/v1/datasets/research/sentiment/viewer/default/train"

    third_page = client.get(
        viewer_path,
        params={"revision": revision_id, "offset": 100, "limit": 50},
    )
    assert third_page.status_code == 200, third_page.text
    assert third_page.json()["total_rows"] == 130
    assert third_page.json()["available_rows"] == 130
    assert len(third_page.json()["rows"]) == 30
    assert third_page.json()["rows"][0]["id"] == 100
    assert third_page.json()["rows"][-1]["id"] == 129
    assert third_page.json()["row_indices"] == list(range(100, 130))
    assert third_page.json()["capabilities"]["preview_is_bounded"] is False

    filtered = client.get(
        viewer_path,
        params={
            "revision": revision_id,
            "filter": json.dumps({"column": "text", "op": "contains", "value": "find-this-row"}),
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["available_rows"] == 1
    assert filtered.json()["rows"] == [{"id": 129, "text": "find-this-row"}]
    assert filtered.json()["row_indices"] == [129]


def test_parquet_image_cells_are_served_as_cached_thumbnails(
    client: TestClient,
) -> None:
    _create_repository(client)
    image_output = BytesIO()
    Image.new("RGB", (640, 480), color=(40, 90, 180)).save(image_output, format="PNG")
    image_bytes = image_output.getvalue()
    image_type = pa.struct(
        [
            pa.field("bytes", pa.binary()),
            pa.field("path", pa.string()),
        ]
    )
    table = pa.table(
        {
            "image": pa.array(
                [{"bytes": image_bytes, "path": "example.png"}],
                type=image_type,
            ),
            "label": ["example"],
        }
    )
    parquet_output = BytesIO()
    parquet.write_table(table, parquet_output)

    create = client.post(
        "/api/v1/datasets/research/sentiment/uploads",
        json={"commit_message": "Upload embedded image Parquet"},
    )
    assert create.status_code == 201, create.text
    upload_id = create.json()["id"]
    uploaded = client.post(
        f"/api/v1/uploads/{upload_id}/files",
        files=[
            (
                "files",
                (
                    "train.parquet",
                    parquet_output.getvalue(),
                    "application/vnd.apache.parquet",
                ),
            ),
            ("paths", (None, "train.parquet")),
        ],
    )
    assert uploaded.status_code == 200, uploaded.text
    complete = client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"expected_file_count": 1},
    )
    assert complete.status_code == 200, complete.text
    revision_id = complete.json()["revision_id"]

    viewer = client.get(
        "/api/v1/datasets/research/sentiment/viewer/default/train",
        params={"revision": revision_id},
    )
    assert viewer.status_code == 200, viewer.text
    assert viewer.json()["row_indices"] == [0]
    assert viewer.json()["rows"] == [
        {
            "image": {
                "_type": "image",
                "row": 0,
                "column": "image",
                "path": "example.png",
                "size": len(image_bytes),
            },
            "label": "example",
        }
    ]

    media_path = "/api/v1/datasets/research/sentiment/viewer-media/default/train/0/image"
    thumbnail = client.get(
        media_path,
        params={"revision": revision_id},
    )
    assert thumbnail.status_code == 200, thumbnail.text
    assert thumbnail.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(thumbnail.content)) as image:
        assert image.width <= 320
        assert image.height <= 320

    cached = client.get(
        media_path,
        params={"revision": revision_id},
    )
    assert cached.content == thumbnail.content
    full_image = client.get(
        media_path,
        params={"revision": revision_id, "thumbnail": False},
    )
    assert full_image.status_code == 200
    assert full_image.headers["content-type"] == "image/png"
    assert full_image.content == image_bytes

    assert client.post("/api/v1/auth/logout").status_code == 204
    anonymous = client.get(
        media_path,
        params={"revision": revision_id},
    )
    assert anonymous.status_code == 401


def test_retrying_same_tree_is_idempotent(client: TestClient) -> None:
    _create_repository(client)
    first = _upload_fixture(client)["revision"]
    second = _upload_fixture(client)["revision"]

    assert second["revision_id"] == first["revision_id"]
    revisions = client.get("/api/v1/datasets/research/sentiment/revisions").json()
    assert len(revisions) == 1


def test_anonymous_user_cannot_create_dataset(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets",
        json={"namespace": "research", "slug": "blocked"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_dataset_name_is_normalized_when_created(client: TestClient) -> None:
    _register(client, "owner")

    response = client.post(
        "/api/v1/datasets",
        json={"namespace": "owner", "slug": "License plate"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "license-plate"
    assert response.json()["data_stage"] is None
    assert response.json()["tags"] == []
    assert client.get("/api/v1/datasets/owner/license-plate").status_code == 200


def test_dataset_stage_and_optional_tags_can_be_updated(client: TestClient) -> None:
    _register(client, "owner")
    created = client.post(
        "/api/v1/datasets",
        json={"namespace": "owner", "slug": "plate-data"},
    )
    assert created.status_code == 201, created.text

    tagged = client.patch(
        "/api/v1/datasets/owner/plate-data",
        json={
            "tags": ["License Plates", "Vietnam", "license-plates"],
        },
    )
    assert tagged.status_code == 200, tagged.text
    assert tagged.json()["tags"] == ["license-plates", "vietnam"]

    stage_before_upload = client.patch(
        "/api/v1/datasets/owner/plate-data",
        json={"data_stage": "raw"},
    )
    assert stage_before_upload.status_code == 422
    assert stage_before_upload.json()["code"] == "initial_stage_requires_upload"

    upload = client.post(
        "/api/v1/datasets/owner/plate-data/uploads",
        json={"commit_message": "Initial data", "data_stage": "raw"},
    )
    assert upload.status_code == 201, upload.text
    content = b'{"image":"plate.jpg","label":"car"}\n'
    uploaded = client.post(
        f"/api/v1/uploads/{upload.json()['id']}/files",
        files=[
            ("files", ("train.jsonl", content, "application/x-ndjson")),
            ("paths", (None, "train.jsonl")),
        ],
    )
    assert uploaded.status_code == 200, uploaded.text
    initial = client.post(
        f"/api/v1/uploads/{upload.json()['id']}/complete",
        json={"expected_file_count": 1},
    )
    assert initial.status_code == 200, initial.text
    assert initial.json()["data_stage"] == "raw"

    upload_stage_without_message = client.post(
        "/api/v1/datasets/owner/plate-data/uploads",
        json={"data_stage": "raw_validated"},
    )
    assert upload_stage_without_message.status_code == 422
    assert upload_stage_without_message.json()["code"] == "stage_commit_message_required"

    direct_patch = client.patch(
        "/api/v1/datasets/owner/plate-data",
        json={"data_stage": "raw_validated"},
    )
    assert direct_patch.status_code == 422
    assert direct_patch.json()["code"] == "data_stage_revision_required"

    missing_message = client.post(
        "/api/v1/datasets/owner/plate-data/stage",
        json={"data_stage": "raw_validated"},
    )
    assert missing_message.status_code == 422

    changed = client.post(
        "/api/v1/datasets/owner/plate-data/stage",
        json={
            "data_stage": "raw_validated",
            "commit_message": "Validated the raw collection",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data_stage"] == "raw_validated"
    assert changed.json()["latest_revision"]["commit_message"] == ("Validated the raw collection")
    assert changed.json()["latest_revision"]["data_stage"] == "raw_validated"

    revisions = client.get("/api/v1/datasets/owner/plate-data/revisions").json()
    assert [item["data_stage"] for item in revisions] == ["raw_validated", "raw"]
    assert revisions[0]["revision_id"] != revisions[1]["revision_id"]
    copied = client.get(
        f"/api/v1/datasets/owner/plate-data/blob/{revisions[0]['revision_id']}/train.jsonl"
    )
    assert copied.content == content


def test_public_read_and_owner_only_mutations(client: TestClient) -> None:
    _register(client, "owner")
    created = client.post(
        "/api/v1/datasets",
        json={
            "namespace": "owner",
            "slug": "public-demo",
            "visibility": "public",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner"] == "owner"
    assert created.json()["can_edit"] is True

    assert client.post("/api/v1/auth/logout").status_code == 204
    public_list = client.get("/api/v1/datasets")
    assert [item["slug"] for item in public_list.json()["items"]] == ["public-demo"]
    assert client.get("/api/v1/datasets/owner/public-demo").status_code == 200
    assert (
        client.patch(
            "/api/v1/datasets/owner/public-demo", json={"description": "anonymous"}
        ).status_code
        == 401
    )

    _register(client, "stranger")
    assert (
        client.patch(
            "/api/v1/datasets/owner/public-demo", json={"description": "not mine"}
        ).status_code
        == 403
    )
    assert client.delete("/api/v1/datasets/owner/public-demo").status_code == 403

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secure-password"},
    )
    assert logged_in.status_code == 200
    renamed = client.patch("/api/v1/datasets/owner/public-demo", json={"slug": "renamed-demo"})
    assert renamed.status_code == 200
    assert renamed.json()["slug"] == "renamed-demo"
    assert client.get("/api/v1/datasets/owner/public-demo").status_code == 404
    assert client.get("/api/v1/datasets/owner/renamed-demo").status_code == 200
    assert client.delete("/api/v1/datasets/owner/renamed-demo").status_code == 204


def test_zero_upload_limits_disable_resource_caps(client: TestClient) -> None:
    settings = get_settings()
    original = (
        settings.max_upload_bytes,
        settings.max_file_bytes,
        settings.max_file_count,
    )
    settings.max_upload_bytes = 0
    settings.max_file_bytes = 0
    settings.max_file_count = 0
    try:
        _create_repository(client)
        revision = _upload_fixture(client)["revision"]
        assert revision["status"] == "ready"
    finally:
        (
            settings.max_upload_bytes,
            settings.max_file_bytes,
            settings.max_file_count,
        ) = original
