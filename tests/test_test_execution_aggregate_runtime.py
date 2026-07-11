from __future__ import annotations

from pathlib import Path

from ops.scripts.test.test_execution_aggregate_runtime import (
    aggregate_counts,
    aggregate_nodeid_digest,
    aggregate_status,
    summary_shard_paths,
)


def test_single_shard_aggregate_preserves_exact_collection_manifest_binding() -> None:
    digest = {
        "status": "collected",
        "command": "python -m pytest --collect-only",
        "nodeid_count": 2,
        "sha256": "a" * 64,
        "reason": "",
        "manifest_path": "build/release-payloads/full.collection.json",
        "manifest_sha256": "b" * 64,
        "manifest_schema": "ops/schemas/test-execution-collection-manifest.schema.json",
        "manifest_nodeids_sha256": "a" * 64,
        "source_tree_fingerprint": "tree",
        "source_revision": "revision",
    }

    aggregate = aggregate_nodeid_digest([{"pytest_collect_nodeid_digest": digest}])

    assert aggregate["sha256"] == digest["sha256"]
    assert aggregate["nodeid_count"] == digest["nodeid_count"]
    assert aggregate["manifest_sha256"] == digest["manifest_sha256"]


def test_aggregate_status_and_counts_are_separate_from_cli_runtime() -> None:
    shards = [
        {"status": "pass", "counts": {"passed": 2, "warnings": 1}},
        {"status": "partial-pass", "counts": {"passed": 1, "failed": 1}},
    ]

    assert aggregate_status([str(shard["status"]) for shard in shards]) == "partial-pass"
    assert aggregate_counts(shards) == {
        "passed": 3,
        "failed": 1,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "warnings": 1,
        "subtests_passed": 0,
    }


def test_summary_shard_paths_prefers_explicit_inputs(tmp_path: Path) -> None:
    shard_dir = tmp_path / "ops" / "reports" / "test-execution-summary-shards"
    shard_dir.mkdir(parents=True)
    (shard_dir / "beta.json").write_text("{}", encoding="utf-8")
    (shard_dir / "alpha.json").write_text("{}", encoding="utf-8")

    assert summary_shard_paths(tmp_path, [], "ops/reports/test-execution-summary-shards") == [
        "ops/reports/test-execution-summary-shards/alpha.json",
        "ops/reports/test-execution-summary-shards/beta.json",
    ]
    assert summary_shard_paths(
        tmp_path,
        ["custom/beta.json", "custom/alpha.json"],
        "ops/reports/test-execution-summary-shards",
    ) == ["custom/alpha.json", "custom/beta.json"]
