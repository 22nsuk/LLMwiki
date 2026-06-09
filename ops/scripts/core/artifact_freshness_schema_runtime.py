#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from ops.scripts.core.artifact_freshness_debt_runtime import is_historical_schema_drift

SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS = {
    "ops/reports/eval-initial-2026-04-12.json",
    "ops/reports/lint-initial-2026-04-12.json",
    "ops/reports/manifest-2026-04-12.json",
    "ops/reports/archive/eval-initial-2026-04-12.json",
    "ops/reports/archive/lint-initial-2026-04-12.json",
    "ops/reports/archive/manifest-2026-04-12.json",
}
RAW_INTAKE_RUN_ARTIFACT_PREFIX = "runs/run-20260422-raw-intake-registration-and-promotion/"
NONCANONICAL_JSON_ARCHIVE_PATHS = {
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/"
        "promotion/concept-continuity-integration-2026-04-22.json"
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/"
        "registration/source-english-summary-reregistration-2026-04-22.json"
    ),
}
NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES = {
    "auto-improve-goal-session-result.json",
    "repo-health-artifact-freshness-report-check.json",
    "scope-freeze.json",
    "subagent-routing.validator.json",
    "subagent-routing.worker.json",
    "validator-executor-report.json",
    "validator-last-message.json",
    "worker-executor-report.json",
    "worker-last-message.json",
}


def is_noncanonical_json_archive_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    if normalized in NONCANONICAL_JSON_ARCHIVE_PATHS:
        return True
    if not normalized.startswith("runs/"):
        return False
    filename = Path(normalized).name
    if filename in NONCANONICAL_ARCHIVED_RUN_AUXILIARY_FILENAMES:
        return True
    if filename.startswith("subagent-routing.") and filename.endswith(".json"):
        return True
    if filename.endswith("-executor-report.json"):
        return True
    return bool(filename.endswith("-last-message.json"))


def schema_contract(
    rel_path: str,
    *,
    has_schema: bool,
    schema_validation_status: str,
) -> dict[str, str]:
    if is_noncanonical_json_archive_path(rel_path):
        return {
            "status": "not_applicable",
            "classification": "noncanonical_archived_run_note",
            "reason": (
                "auxiliary run JSON is retained for audit context "
                "but is not canonical release evidence"
            ),
            "recommended_next_action": "none",
        }
    if has_schema:
        if schema_validation_status == "pass":
            return {
                "status": "present",
                "classification": "schema_backed",
                "reason": "artifact declares a loadable schema and validates against it",
                "recommended_next_action": "none",
            }
        if schema_validation_status == "fail":
            return {
                "status": "invalid",
                "classification": "schema_invalid",
                "reason": "artifact declares a schema but current payload fails validation",
                "recommended_next_action": "regenerate_artifact_from_current_schema",
            }
        if is_historical_schema_drift(
            rel_path=rel_path,
            schema_validation_status=schema_validation_status,
        ):
            return {
                "status": "invalid",
                "classification": "historical_run_schema_drift",
                "reason": (
                    "run-local artifact is retained as historical audit evidence "
                    "but predates the current schema contract"
                ),
                "recommended_next_action": "archive_or_classify_historical_run_artifact",
            }
        if schema_validation_status == "schema_unavailable":
            return {
                "status": "unavailable",
                "classification": "schema_reference_unavailable",
                "reason": "artifact declares a schema path or URI that cannot be loaded in this vault",
                "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
            }
        return {
            "status": "not_applicable",
            "classification": "schema_not_applicable",
            "reason": "artifact payload was not schema-validated",
            "recommended_next_action": "none",
        }

    if rel_path in SCHEMALESS_HISTORICAL_BOOTSTRAP_REPORTS:
        return {
            "status": "missing",
            "classification": "historical_bootstrap_report_pending_schema_decision",
            "reason": "bootstrap ops report predates the generated artifact schema contract",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith(RAW_INTAKE_RUN_ARTIFACT_PREFIX):
        return {
            "status": "missing",
            "classification": "raw_intake_run_artifact_family_pending_schema",
            "reason": "raw-intake run artifact belongs to a family that needs shared schema or archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("runs/"):
        return {
            "status": "missing",
            "classification": "run_artifact_pending_schema_decision",
            "reason": "run-local JSON artifact lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("ops/reports/"):
        return {
            "status": "missing",
            "classification": "ops_report_pending_schema_decision",
            "reason": "ops report lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    if rel_path.startswith("ops/operator/"):
        return {
            "status": "missing",
            "classification": "operator_report_pending_schema_decision",
            "reason": "operator report lacks a declared schema or noncanonical archive classification",
            "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
        }
    return {
        "status": "missing",
        "classification": "json_artifact_pending_schema_decision",
        "reason": "JSON artifact lacks a declared schema or noncanonical classification",
        "recommended_next_action": "add_schema_or_exclude_noncanonical_json",
    }


def safe_to_backfill(
    *,
    utf8_ok: bool,
    json_ok: bool,
    schema_validation_status: str,
    mtime_status: str,
) -> bool:
    if not utf8_ok or not json_ok:
        return False
    if schema_validation_status == "fail":
        return False
    return mtime_status != "stale"
