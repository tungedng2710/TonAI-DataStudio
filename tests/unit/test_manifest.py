from data_studio_api.domain.manifest import ManifestFile, build_manifest


def test_manifest_is_deterministic_and_sorted() -> None:
    first = ManifestFile("z.csv", 2, "b" * 64, "text/csv", "source/b/z.csv")
    second = ManifestFile("a.csv", 1, "a" * 64, "text/csv", "source/a/a.csv")

    manifest_a, encoded_a, digest_a = build_manifest("team/demo", [first, second])
    manifest_b, encoded_b, digest_b = build_manifest("team/demo", [second, first])

    assert [item["path"] for item in manifest_a["files"]] == ["a.csv", "z.csv"]
    assert manifest_a == manifest_b
    assert encoded_a == encoded_b
    assert digest_a == digest_b


def test_manifest_digest_includes_data_stage() -> None:
    source = ManifestFile("data.jsonl", 10, "a" * 64, "application/json", "source/data")

    raw, _, raw_digest = build_manifest("team/demo", [source], data_stage="raw")
    ready, _, ready_digest = build_manifest("team/demo", [source], data_stage="training_ready")

    assert raw["data_stage"] == "raw"
    assert ready["data_stage"] == "training_ready"
    assert raw_digest != ready_digest
