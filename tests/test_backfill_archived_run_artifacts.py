from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

import pytest

from ops.scripts.core.artifact_freshness_runtime import (
    EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
    build_report,
)
from ops.scripts.core.backfill_archived_run_artifacts import (
    ARCHIVE_REASON,
    BACKFILL_PROVENANCE_PROPERTY,
    backfill_archived_run_artifacts,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVED_RUN_REL = Path("runs/archive/run-20260415-mechanism-planning-gate-second-retry")
ARCHIVED_RUN_SOURCE = REPO_ROOT / ARCHIVED_RUN_REL
ACTIVE_RUN_REL = Path("runs/run-20260422-auto-improve-decision-record-fallback-retry")
ACTIVE_RUN_SOURCE = REPO_ROOT / ACTIVE_RUN_REL
RAW_INTAKE_RUN_REL = Path("runs/run-20260422-raw-intake-registration-and-promotion")
RAW_INTAKE_RUN_SOURCE = REPO_ROOT / RAW_INTAKE_RUN_REL
FIXED_CHECKED_AT = "2026-04-28T06:00:00Z"
TARGET_CASES = (
    (
        "changed-files-manifest.json",
        REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json",
        "changed_files_manifest",
        "2026-04-14T15:33:16Z",
        "payload.generated_at",
    ),
    (
        "planning-validation.json",
        REPO_ROOT / "ops" / "schemas" / "planning-validation.schema.json",
        "planning_validation",
        "2026-04-15T00:21:00Z",
        "promotion-report.history.ts",
    ),
    (
        "promotion-report.json",
        REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json",
        "promotion_report",
        "2026-04-15T00:21:00Z",
        "history.ts",
    ),
    (
        "run-ledger.json",
        REPO_ROOT / "ops" / "schemas" / "run-ledger.schema.json",
        "run_ledger",
        "2026-04-14T15:33:16Z",
        "events[5].ts",
    ),
)
MECHANISM_ASSESSMENT_FILENAMES = (
    "baseline-mechanism-assessment.json",
    "candidate-mechanism-assessment.json",
)
FULL_VAULT_FIXTURE_SENTINELS = (
    ARCHIVED_RUN_SOURCE / "changed-files-manifest.json",
    ACTIVE_RUN_SOURCE / "changed-files-manifest.json",
    RAW_INTAKE_RUN_SOURCE / "absorption/raw-intake-absorption-matrix-2026-04-22.json",
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 28, 6, 0, tzinfo=dt.UTC),
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_full_vault_run_fixtures() -> None:
    if all(path.exists() for path in FULL_VAULT_FIXTURE_SENTINELS):
        return
    pytest.skip("requires full-vault run fixtures excluded from the public mirror")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_mtime_to_generated_at(path: Path, payload: dict) -> None:
    generated_at = str(payload.get("generated_at", "")).strip()
    if not generated_at:
        return
    timestamp = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    os.utime(path, (timestamp, timestamp))


def _metadata_property(payload: dict, name: str) -> str | None:
    properties = payload.get("metadata", {}).get("properties", [])
    for item in properties:
        if isinstance(item, dict) and item.get("name") == name and isinstance(item.get("value"), str):
            return item["value"]
    return None


def _seed_pre_backfill_archived_run(vault: Path) -> None:
    run_dir = vault / ARCHIVED_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename, _, _, _, _ in TARGET_CASES:
        payload = _read_json(ARCHIVED_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        _write_json(run_dir / filename, payload)


def _seed_pre_backfill_active_run(vault: Path) -> None:
    run_dir = vault / ACTIVE_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "changed-files-manifest.json",
        "planning-validation.json",
        "promotion-report.json",
        "run-ledger.json",
        "behavior-delta.json",
        "run-artifact-fingerprint.json",
        "baseline-mechanism-assessment.json",
        "candidate-mechanism-assessment.json",
        "run-telemetry.json",
    ):
        payload = _read_json(ACTIVE_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        path = run_dir / filename
        _write_json(path, payload)
        _set_mtime_to_generated_at(path, payload)


def _seed_pre_backfill_mechanism_assessment_pair(vault: Path) -> None:
    run_dir = vault / ARCHIVED_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in MECHANISM_ASSESSMENT_FILENAMES:
        payload = _read_json(ARCHIVED_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        for key in ("structural_metrics", "total_structural_metrics"):
            payload[key].pop("test_guardrail_count", None)
        verification_cost = payload["complexity_profile"]["dimension_evidence"][
            "verification_cost"
        ]
        verification_cost.pop("test_guardrail_count", None)
        _write_json(run_dir / filename, payload)


def _seed_pre_backfill_raw_intake_run(vault: Path) -> list[str]:
    rel_paths = [
        RAW_INTAKE_RUN_REL / "absorption/raw-intake-absorption-matrix-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "registration/source-english-summary-slug-manifest-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-profiles-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-render-after-concept-integration-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-validate-after-concept-integration-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/raw-intake-promotion-validate-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/raw-registry-preflight-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/source-english-summary-slug-validate-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/wiki-lint-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/wiki-stage2-final-tree-2026-04-22.json",
    ]
    target_rel_paths: list[str] = []
    for rel_path in rel_paths:
        payload = _read_json(REPO_ROOT / rel_path)
        payload.pop("metadata", None)
        target_path = vault / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target_path, payload)
        target_rel_paths.append(rel_path.as_posix())
    return target_rel_paths


def test_backfill_archived_run_artifacts_supports_convergence_and_timeout_auxiliary_reports() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_id = "legacy-generated-artifact-auxiliary-run"
        run_dir = vault / "runs" / "archive" / run_id
        run_dir.mkdir(parents=True)
        convergence_rel_path = f"runs/archive/{run_id}/generated-artifact-convergence.json"
        timeout_rel_path = f"runs/archive/{run_id}/repo-health-timeout-failure.json"
        _write_json(
            vault / convergence_rel_path,
            {
                "$schema": "ops/schemas/generated-artifact-convergence.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-28T05:30:00Z",
                "phase": "post_mutation_generated_artifact_convergence",
                "status": "refreshed",
                "selected_targets": ["artifact-freshness-refresh-check"],
                "refreshed_targets": ["artifact-freshness-refresh-check"],
                "artifacts": ["ops/reports/artifact-freshness-report.json"],
                "summary": {
                    "selected_target_count": 1,
                    "refreshed_target_count": 1,
                    "artifact_count": 1,
                },
                "details": [
                    {
                        "target": "artifact-freshness-refresh-check",
                        "status": "refreshed",
                        "artifacts": ["ops/reports/artifact-freshness-report.json"],
                        "reproducibility_status": "pass",
                        "reproducibility_diff_status": "clean",
                    }
                ],
            },
        )
        _write_json(
            vault / timeout_rel_path,
            {
                "$schema": "ops/schemas/timeout-failure.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-28T05:35:00Z",
                "phase": "repo_health",
                "role": "repo-health",
                "command": {
                    "command": "make static",
                    "argv": ["make", "static"],
                },
                "result": {
                    "returncode": -15,
                    "timed_out": True,
                    "timeout_seconds": 5,
                    "termination_reason": "timeout",
                    "launch_succeeded": True,
                    "signal_sent": "TERM",
                    "final_state_observed": "terminated",
                    "stdout_received": True,
                    "stderr_received": True,
                },
                "artifacts": {
                    "stdout": f"runs/archive/{run_id}/repo-health.stdout.txt",
                    "stderr": f"runs/archive/{run_id}/repo-health.stderr.txt",
                },
            },
        )

        written = backfill_archived_run_artifacts(vault, context=fixed_context())

        assert set(written) == {convergence_rel_path, timeout_rel_path}
        freshness_report = build_report(vault, context=fixed_context())
        expectations = {
            convergence_rel_path: (
                REPO_ROOT / "ops" / "schemas" / "generated-artifact-convergence.schema.json",
                "generated_artifact_convergence",
                "2026-04-28T05:30:00Z",
            ),
            timeout_rel_path: (
                REPO_ROOT / "ops" / "schemas" / "timeout-failure.schema.json",
                "timeout_failure",
                "2026-04-28T05:35:00Z",
            ),
        }
        for rel_path, (schema_path, artifact_kind, generated_at) in expectations.items():
            payload = _read_json(vault / rel_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == rel_path
            )

            assert validate_with_schema(payload, load_schema(schema_path)) == []
            assert embedded_envelope.get("artifact_kind") == artifact_kind
            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("generated_at") == generated_at
            assert embedded_envelope.get("currentness", {}).get("status") == "current"
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("source_artifact") == rel_path
            assert provenance.get("generated_at") == generated_at
            assert provenance.get("generated_at_source") == "payload.generated_at"
            assert provenance.get("normalized_at") == FIXED_CHECKED_AT
            assert record.get("artifact_kind") == artifact_kind
            assert record.get("artifact_status") == "archived"
            assert record.get("retention_policy") == "archive"
            assert record.get("has_artifact_envelope") is True
            assert record.get("has_generated_at") is True
            assert record.get("currentness_status") == "current"
            assert record.get("mtime_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_archived_run_artifacts_supports_command_log_summary() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_id = "legacy-command-log-summary-run"
        rel_path = f"runs/archive/{run_id}/command-log-summary.json"
        (vault / rel_path).parent.mkdir(parents=True, exist_ok=True)
        _write_json(
            vault / rel_path,
            {
                "$schema": "ops/schemas/command-log-summary.schema.json",
                "artifact_kind": "command_log_summary",
                "schema_version": 1,
                "run_id": run_id,
                "generated_at": "2026-04-28T05:40:00Z",
                "producer": "ops.scripts.command_log_summary_runtime",
                "summary": {
                    "stream_count": 1,
                    "truncated_stream_count": 0,
                    "original_total_bytes": 5,
                    "trace_total_bytes": 5,
                },
                "streams": [
                    {
                        "prefix": "repo-health",
                        "stream": "stdout",
                        "original_path": f"runs/archive/{run_id}/repo-health.stdout.txt",
                        "original_size_bytes": 5,
                        "original_sha256": "0" * 64,
                        "trace_path": f"runs/archive/{run_id}/repo-health.stdout-trace.txt",
                        "trace_size_bytes": 5,
                        "trace_sha256": "0" * 64,
                        "head_limit_bytes": 16384,
                        "tail_limit_bytes": 16384,
                        "head_retained_bytes": 5,
                        "tail_retained_bytes": 0,
                        "truncated": False,
                        "command": "make static",
                        "argv": ["make", "static"],
                        "returncode": 0,
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                        "diagnostic_flags": [],
                        "generated_at": "2026-04-28T05:40:00Z",
                    }
                ],
            },
        )

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        freshness_report = build_report(vault, context=fixed_context())
        payload = _read_json(vault / rel_path)
        embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
        provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
        record = next(
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == rel_path
        )

        assert written == [rel_path]
        assert validate_with_schema(
            payload,
            load_schema(REPO_ROOT / "ops" / "schemas" / "command-log-summary.schema.json"),
        ) == []
        assert embedded_envelope.get("artifact_kind") == "command_log_summary"
        assert embedded_envelope.get("artifact_status") == "archived"
        assert embedded_envelope.get("retention_policy") == "archive"
        assert embedded_envelope.get("generated_at") == "2026-04-28T05:40:00Z"
        assert embedded_envelope.get("currentness", {}).get("status") == "current"
        assert provenance.get("source_artifact") == rel_path
        assert provenance.get("generated_at_source") == "payload.generated_at"
        assert record.get("has_artifact_envelope") is True
        assert record.get("schema_validation_status") == "pass"
        assert "missing_artifact_envelope" not in record.get("issues", [])
        assert "unknown_currentness" not in record.get("issues", [])


def test_backfill_archived_run_artifacts_embeds_archived_envelopes_and_clears_freshness_debt() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        expected_written = {str((ARCHIVED_RUN_REL / filename).as_posix()) for filename, _, _, _, _ in TARGET_CASES}

        assert set(written) == expected_written

        freshness_report = build_report(vault, context=fixed_context())
        for filename, schema_path, artifact_kind, generated_at, generated_at_source in TARGET_CASES:
            path = vault / ARCHIVED_RUN_REL / filename
            payload = _read_json(path)
            schema = load_schema(schema_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == str((ARCHIVED_RUN_REL / filename).as_posix())
            )

            assert validate_with_schema(payload, schema) == []
            assert embedded_envelope.get("artifact_kind") == artifact_kind
            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("generated_at") == generated_at
            assert embedded_envelope.get("currentness", {}).get("status") == "current"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("generated_at") == generated_at
            assert provenance.get("generated_at_source") == generated_at_source
            assert provenance.get("normalized_at") == FIXED_CHECKED_AT

            assert record.get("artifact_kind") == artifact_kind
            assert record.get("artifact_status") == "archived"
            assert record.get("retention_policy") == "archive"
            assert record.get("has_artifact_envelope") is True
            assert record.get("has_generated_at") is True
            assert record.get("currentness_status") == "current"
            assert record.get("mtime_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_run_artifacts_supports_top_level_historical_run_tranche() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_active_run(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        expected_written = {
            str((ACTIVE_RUN_REL / filename).as_posix())
            for filename in (
                "changed-files-manifest.json",
                "planning-validation.json",
                "promotion-report.json",
                "run-ledger.json",
                "behavior-delta.json",
                "run-artifact-fingerprint.json",
                "baseline-mechanism-assessment.json",
                "candidate-mechanism-assessment.json",
                "run-telemetry.json",
            )
        }

        assert set(written) == expected_written

        freshness_report = build_report(vault, context=fixed_context())
        for rel_path in expected_written:
            payload = _read_json(vault / rel_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == rel_path
            )

            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("source_artifact") == rel_path
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_run_telemetry_restores_legacy_discard_check_statuses() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_id = "legacy-discard-run"
        run_dir = vault / "runs" / run_id
        run_dir.mkdir(parents=True)
        promotion_report_rel = f"runs/{run_id}/promotion-report.json"
        _write_json(
            vault / promotion_report_rel,
            {
                "checks": [
                    {"id": "candidate_eval_pass", "status": "PASS"},
                    {"id": "eval_score_improves", "status": "WARN"},
                    {"id": "lint_non_regression", "status": "PASS"},
                    {"id": "structural_complexity_non_regression", "status": "FAIL"},
                    {"id": "tests_non_regression", "status": "not-a-gate-status"},
                ]
            },
        )
        run_telemetry_rel = f"runs/{run_id}/run-telemetry.json"
        _write_json(
            vault / run_telemetry_rel,
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-28T06:00:00Z",
                "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                "routing_reports": [],
                "executor_reports": [],
                "decision": "DISCARD",
                "finalized": True,
                "finalize_result": {},
                "discard_non_regression_evidence": {
                    "promotion_report_source": "path",
                    "promotion_report": promotion_report_rel,
                    "candidate_eval_pass": True,
                    "eval_score_improves": False,
                    "lint_non_regression": True,
                    "structural_complexity_non_regression": False,
                    "tests_non_regression": False,
                    "blocking_check_ids": [
                        "structural_complexity_non_regression",
                    ],
                    "decision_record_reason_code": "structural_complexity_non_regression",
                },
            },
        )

        written = backfill_archived_run_artifacts(
            vault,
            rel_paths=[run_telemetry_rel],
            context=fixed_context(),
        )

        assert written == [run_telemetry_rel]
        payload = _read_json(vault / run_telemetry_rel)
        evidence = payload["discard_non_regression_evidence"]
        assert evidence["non_regression_check_statuses"] == {
            "candidate_eval_pass": "PASS",
            "eval_score_improves": "WARN",
            "lint_non_regression": "PASS",
            "structural_complexity_non_regression": "FAIL",
            "tests_non_regression": "UNKNOWN",
        }
        assert _metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY)
        assert validate_with_schema(
            payload,
            load_schema(REPO_ROOT / "ops" / "schemas" / "run-telemetry.schema.json"),
        ) == []

        stale_payload = dict(payload)
        stale_evidence = dict(stale_payload["discard_non_regression_evidence"])
        stale_evidence.pop("non_regression_check_statuses")
        stale_payload["discard_non_regression_evidence"] = stale_evidence
        _write_json(vault / run_telemetry_rel, stale_payload)

        rewritten = backfill_archived_run_artifacts(
            vault,
            rel_paths=[run_telemetry_rel],
            context=fixed_context(),
        )

        assert rewritten == [run_telemetry_rel]
        repaired = _read_json(vault / run_telemetry_rel)
        assert repaired["discard_non_regression_evidence"]["non_regression_check_statuses"] == evidence[
            "non_regression_check_statuses"
        ]


def test_backfill_run_telemetry_does_not_read_traversal_promotion_report_path() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_id = "legacy-discard-run"
        other_run_id = "legacy-discard-other"
        (vault / "runs" / run_id).mkdir(parents=True)
        other_run_dir = vault / "runs" / other_run_id
        other_run_dir.mkdir(parents=True)
        _write_json(
            other_run_dir / "promotion-report.json",
            {
                "checks": [
                    {"id": "candidate_eval_pass", "status": "PASS"},
                    {"id": "eval_score_improves", "status": "PASS"},
                    {"id": "lint_non_regression", "status": "PASS"},
                    {"id": "structural_complexity_non_regression", "status": "PASS"},
                    {"id": "tests_non_regression", "status": "PASS"},
                ]
            },
        )
        run_telemetry_rel = f"runs/{run_id}/run-telemetry.json"
        _write_json(
            vault / run_telemetry_rel,
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-28T06:00:00Z",
                "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                "routing_reports": [],
                "executor_reports": [],
                "decision": "DISCARD",
                "finalized": True,
                "finalize_result": {},
                "discard_non_regression_evidence": {
                    "promotion_report_source": "path",
                    "promotion_report": f"runs/{run_id}/../{other_run_id}/promotion-report.json",
                    "candidate_eval_pass": False,
                    "eval_score_improves": False,
                    "lint_non_regression": False,
                    "structural_complexity_non_regression": False,
                    "tests_non_regression": False,
                    "blocking_check_ids": [
                        "candidate_eval_pass",
                    ],
                    "decision_record_reason_code": "candidate_eval_pass",
                },
            },
        )

        written = backfill_archived_run_artifacts(
            vault,
            rel_paths=[run_telemetry_rel],
            context=fixed_context(),
        )

        assert written == [run_telemetry_rel]
        payload = _read_json(vault / run_telemetry_rel)
        assert payload["discard_non_regression_evidence"]["non_regression_check_statuses"] == {
            "candidate_eval_pass": "UNKNOWN",
            "eval_score_improves": "UNKNOWN",
            "lint_non_regression": "UNKNOWN",
            "structural_complexity_non_regression": "UNKNOWN",
            "tests_non_regression": "UNKNOWN",
        }


def test_backfill_run_artifacts_supports_promotion_report_variant_filename() -> None:
    _require_full_vault_run_fixtures()
    variant_filename = "promotion-report.equal-score-policy-rerun.json"
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        run_dir = vault / ARCHIVED_RUN_REL
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = _read_json(ARCHIVED_RUN_SOURCE / "promotion-report.json")
        payload.pop("metadata", None)
        _write_json(run_dir / variant_filename, payload)

        variant_rel_path = (ARCHIVED_RUN_REL / variant_filename).as_posix()
        written = backfill_archived_run_artifacts(vault, rel_paths=[variant_rel_path], context=fixed_context())

        assert written == [variant_rel_path]
        payload = _read_json(vault / variant_rel_path)
        embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
        provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
        freshness_report = build_report(vault, context=fixed_context())
        record = next(
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == variant_rel_path
        )

        assert embedded_envelope.get("artifact_kind") == "promotion_report"
        assert embedded_envelope.get("artifact_status") == "archived"
        assert embedded_envelope.get("retention_policy") == "archive"
        assert provenance.get("source_artifact") == variant_rel_path
        assert record.get("has_artifact_envelope") is True
        assert record.get("has_generated_at") is True
        assert "missing_artifact_envelope" not in record.get("issues", [])


def test_backfill_run_artifacts_supports_raw_intake_safe_backfill_tranche() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        target_rel_paths = _seed_pre_backfill_raw_intake_run(vault)

        written = backfill_archived_run_artifacts(vault, rel_paths=target_rel_paths, context=fixed_context())

        assert set(written) == set(target_rel_paths)
        freshness_report = build_report(vault, context=fixed_context())
        for rel_path in target_rel_paths:
            payload = _read_json(vault / rel_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == rel_path
            )

            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("source_artifact") == rel_path
            assert record.get("has_generated_at") is True
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_archived_run_artifacts_skips_already_backfilled_payloads() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)

        first_written = backfill_archived_run_artifacts(vault, context=fixed_context())
        written = backfill_archived_run_artifacts(vault, context=fixed_context())

        assert first_written
        assert written == []


def test_backfill_archived_run_artifacts_supports_mechanism_assessment_pair() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)
        _seed_pre_backfill_mechanism_assessment_pair(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        freshness_report = build_report(vault, context=fixed_context())

        assert set(written) == {
            str((ARCHIVED_RUN_REL / filename).as_posix())
            for filename in (
                *(filename for filename, _, _, _, _ in TARGET_CASES),
                *MECHANISM_ASSESSMENT_FILENAMES,
            )
        }

        for filename in MECHANISM_ASSESSMENT_FILENAMES:
            path = vault / ARCHIVED_RUN_REL / filename
            payload = _read_json(path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == str((ARCHIVED_RUN_REL / filename).as_posix())
            )

            assert embedded_envelope.get("artifact_kind") == "mechanism_assessment_report"
            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert payload["structural_metrics"]["test_guardrail_count"] == 0
            assert payload["total_structural_metrics"]["test_guardrail_count"] == 0
            assert (
                payload["complexity_profile"]["dimension_evidence"]["verification_cost"][
                    "test_guardrail_count"
                ]
                == 0
            )
            assert record.get("safe_to_backfill") is True
            assert record.get("schema_validation_status") == "pass"
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("issues") == []
