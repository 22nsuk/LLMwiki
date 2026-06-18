from __future__ import annotations

from ops.scripts.core.artifact_freshness_schema_runtime import (
    is_noncanonical_json_archive_path,
    safe_to_backfill,
    schema_contract,
)


def test_noncanonical_run_archive_paths_are_classified() -> None:
    assert is_noncanonical_json_archive_path("runs/run-20260422-sample/worker-last-message.json")
    assert is_noncanonical_json_archive_path("runs/run-20260422-sample/subagent-routing.worker.json")
    assert is_noncanonical_json_archive_path(
        "runs/run-20260422-sample/repo-health-artifact-freshness-report-check.json"
    )
    assert is_noncanonical_json_archive_path(
        "runs/goal-run-20260422-sample/state/auto-improve-goal-session-result.json"
    )
    assert not is_noncanonical_json_archive_path("ops/reports/release-closeout-summary.json")


def test_schema_contract_distinguishes_schema_backed_and_pending_ops_reports() -> None:
    assert schema_contract(
        "ops/reports/release-closeout-summary.json",
        has_schema=True,
        schema_validation_status="pass",
    )["classification"] == "schema_backed"
    assert schema_contract(
        "ops/reports/review-archive-report.json",
        has_schema=True,
        schema_validation_status="pass",
    )["classification"] == "schema_backed"
    assert schema_contract(
        "ops/reports/example.json",
        has_schema=False,
        schema_validation_status="not_applicable",
    )["classification"] == "ops_report_pending_schema_decision"
    assert schema_contract(
        "runs/run-20260422-sample/worker-last-message.json",
        has_schema=False,
        schema_validation_status="not_applicable",
    )["classification"] == "noncanonical_archived_run_note"
    assert schema_contract(
        "runs/run-20260422-sample/repo-health-artifact-freshness-report-check.json",
        has_schema=True,
        schema_validation_status="not_applicable",
    )["classification"] == "noncanonical_archived_run_note"


def test_safe_to_backfill_rejects_invalid_or_stale_inputs() -> None:
    assert safe_to_backfill(
        utf8_ok=True,
        json_ok=True,
        schema_validation_status="pass",
        mtime_status="current",
    )
    assert not safe_to_backfill(
        utf8_ok=True,
        json_ok=True,
        schema_validation_status="fail",
        mtime_status="current",
    )
    assert not safe_to_backfill(
        utf8_ok=True,
        json_ok=True,
        schema_validation_status="pass",
        mtime_status="stale",
    )
