from __future__ import annotations

from pathlib import Path

from ops.scripts.core.artifact_freshness_payload_runtime import (
    ENVELOPE_REQUIRED_FIELDS,
    canonical_artifact_payload,
    canonical_report_loading_issue,
    computed_currentness_status,
    embed_artifact_envelope_metadata,
    has_artifact_envelope,
)


def _envelope(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "$schema": "ops/schemas/example.schema.json",
        "artifact_kind": "example",
        "generated_at": "2026-04-29T00:00:00Z",
        "producer": "test",
        "source_command": "pytest",
        "source_revision": "abc123",
        "source_tree_fingerprint": "tree",
        "input_fingerprints": {"policy": "hash"},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {"status": "current"},
    }
    payload.update(overrides)
    return payload


def test_embedded_envelope_backfills_missing_top_level_fields() -> None:
    envelope = _envelope()
    payload = embed_artifact_envelope_metadata(
        {
            "metadata": {
                "properties": [
                    {"name": "other", "value": "kept"},
                ]
            },
            "artifact_kind": "",
        },
        envelope,
    )

    canonical = canonical_artifact_payload(payload)

    assert all(field in canonical for field in ENVELOPE_REQUIRED_FIELDS)
    assert canonical["artifact_kind"] == "example"
    assert canonical["metadata"]["properties"][0]["name"] == "other"
    assert has_artifact_envelope(payload) is True


def test_canonical_report_loading_issue_uses_envelope_status() -> None:
    assert canonical_report_loading_issue(Path("report.json"), _envelope()) is None
    assert canonical_report_loading_issue(Path("report.json"), {}) == "missing_artifact_envelope"
    assert (
        canonical_report_loading_issue(Path("report.json"), _envelope(artifact_status="archived"))
        == "artifact_status=archived"
    )
    assert (
        canonical_report_loading_issue(Path("report.json"), _envelope(currentness={"status": "stale"}))
        == "currentness_status=stale"
    )


def test_computed_currentness_status_downgrades_declared_current_on_head_drift() -> None:
    assert (
        computed_currentness_status(
            declared_currentness_status="current",
            source_tree_fingerprint_status="stale",
        )
        == "stale"
    )
    assert (
        computed_currentness_status(
            declared_currentness_status="attention",
            source_tree_fingerprint_status="current",
        )
        == "attention"
    )
    assert (
        computed_currentness_status(
            declared_currentness_status="current",
            source_tree_fingerprint_status="current",
            source_revision_status="provenance_only",
        )
        == "current"
    )
    assert (
        computed_currentness_status(
            declared_currentness_status="current",
            source_tree_fingerprint_status="current",
            input_fingerprint_status="stale",
        )
        == "stale"
    )
