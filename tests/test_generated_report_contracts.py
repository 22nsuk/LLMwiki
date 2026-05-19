from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ops.scripts.artifact_freshness_runtime import STABLE_CONTRACT_ISSUES, build_canonical_report_envelope
from ops.scripts.generated_artifact_index import build_report as build_generated_artifact_index_report
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_STATUS_LIKELY,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_FRESHNESS_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "artifact-freshness-report.json"
AUTO_IMPROVE_READINESS_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "auto-improve-readiness.json"
AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "auto-improve-readiness-report.schema.json"
CYCLONEDX_BOM_PATH = REPO_ROOT / "ops" / "reports" / "cyclonedx-bom.json"
GENERATED_ARTIFACT_INDEX_PATH = REPO_ROOT / "ops" / "reports" / "generated-artifact-index.json"
GENERATED_ARTIFACT_INDEX_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "generated-artifact-index.schema.json"
MANUAL_MUTATE_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "manual-mutate-defect-registry.json"
MECHANISM_REVIEW_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "mechanism-review-candidates.json"
OPENVEX_DRAFT_PATH = REPO_ROOT / "ops" / "reports" / "openvex-draft.json"
IMPROVEMENT_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260427-anti-slop-report-reconciliation"
    / "improvement-observations.json"
)

pytestmark = pytest.mark.report_contract
LEARNING_EVIDENCE_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-learning-evidence-hardening"
    / "improvement-observations.json"
)
IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "improvement-observations.schema.json"
MANUAL_MUTATE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "manual-mutate-defect-registry.schema.json"
OPENVEX_DRAFT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "openvex-draft.schema.json"
OUTCOME_METRICS_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "outcome-metrics.json"
PYTEST_RELEASE_SMOKE_HARDENING_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-pytest-release-smoke-hardening"
    / "improvement-observations.json"
)
STABLE_ARTIFACT_DEBT_TRANCHE_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-stable-artifact-debt-ops-bootstrap-backfill"
    / "improvement-observations.json"
)
ARCHIVED_RUN_BACKFILL_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-stable-artifact-debt-archived-run-backfill"
    / "improvement-observations.json"
)
REPORT_SCHEMA_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"
RAW_REGISTRY_REPRODUCTION_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-raw-registry-reproduction-protocol"
    / "improvement-observations.json"
)
REVIEW_ARCHIVE_OBSERVATIONS_PATH = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "task-improvement-observations"
    / "task-20260428-review-archive-canonicalization"
    / "improvement-observations.json"
)
REVIEW_ARCHIVE_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "review-archive-report.json"
REVIEW_ARCHIVE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "review-archive-report.schema.json"
RELEASE_SMOKE_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "release-smoke-report.json"
RELEASE_SMOKE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-smoke-report.schema.json"
RAW_REGISTRY_PREFLIGHT_REPORT_PATH = REPO_ROOT / "ops" / "reports" / "raw-registry-preflight-report.json"
RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "raw-registry-preflight-report.schema.json"
)
RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_PATH = (
    REPO_ROOT / "ops" / "reports" / "raw-registry-preflight-reproducibility.json"
)
RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "raw-registry-preflight-reproducibility.schema.json"
)
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_PATH = (
    REPO_ROOT / "ops" / "reports" / "raw-registry-cross-environment-matrix.json"
)
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "raw-registry-cross-environment-matrix.schema.json"
)
RELEASE_RISK_TAXONOMY_MATRIX_PATH = REPO_ROOT / "ops" / "reports" / "release-risk-taxonomy-matrix.json"
RELEASE_RISK_TAXONOMY_MATRIX_MARKDOWN_PATH = REPO_ROOT / "ops" / "reports" / "release-risk-taxonomy-matrix.md"
RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "release-risk-taxonomy-matrix.schema.json"
)
WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "workflow-dependency-planner.schema.json"
TEST_EXECUTION_SUMMARY_PATH = REPO_ROOT / "ops" / "reports" / "test-execution-summary.json"
TEST_EXECUTION_SUMMARY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "test-execution-summary.schema.json"
ROUTING_PROVENANCE_AGGREGATE_REPORT_DIR = (
    REPO_ROOT
    / "ops"
    / "reports"
    / "routing-provenance-aggregates"
)
EXPECTED_MISSING_GENERATED_AT_ACTION = "backfill_generated_at_or_mark_legacy_noncanonical"
EXPECTED_ARCHIVED_RUN_ID = "run-20260422-auto-improve-decision-record-fallback"
EXPECTED_CYCLONEDX_BOM_PATH = "ops/reports/cyclonedx-bom.json"
EXPECTED_MANUAL_MUTATE_REPORT_PATH = "ops/reports/manual-mutate-defect-registry.json"
EXPECTED_OPENVEX_DRAFT_PATH = "ops/reports/openvex-draft.json"
EXPECTED_AUTO_IMPROVE_READINESS_REPORT_PATH = "ops/reports/auto-improve-readiness.json"
EXPECTED_REVIEW_ARCHIVE_REPORT_PATH = "ops/reports/review-archive-report.json"
EXPECTED_RELEASE_SMOKE_REPORT_PATH = "ops/reports/release-smoke-report.json"
EXPECTED_RAW_REGISTRY_PREFLIGHT_REPORT_PATH = "ops/reports/raw-registry-preflight-report.json"
EXPECTED_RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_PATH = (
    "ops/reports/raw-registry-preflight-reproducibility.json"
)
EXPECTED_RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_PATH = (
    "ops/reports/raw-registry-cross-environment-matrix.json"
)
EXPECTED_RELEASE_RISK_TAXONOMY_MATRIX_PATH = "ops/reports/release-risk-taxonomy-matrix.json"
EXPECTED_TEST_EXECUTION_SUMMARY_PATH = "ops/reports/test-execution-summary.json"
EXPECTED_RELEASE_SMOKE_SOURCE_PATHS = [
    "ops/scripts/release_smoke.py",
    "ops/scripts/command_runtime.py",
    "ops/scripts/wiki_manifest.py",
]
EXPECTED_ROUTING_PROVENANCE_AGGREGATE_REPORT_DIR = (
    ROUTING_PROVENANCE_AGGREGATE_REPORT_DIR.relative_to(REPO_ROOT).as_posix()
)
EXPECTED_RELEASE_SMOKE_COMMANDS = {
    "raw_registry_preflight": "python -m ops.scripts.registry.raw_registry_preflight --vault .",
    "wiki_lint": "python -m ops.scripts.eval.wiki_lint --vault . --release-archive-profile",
    "wiki_eval": "python -m ops.scripts.eval.wiki_eval --vault . --release-archive-profile --require-max-score",
    "wiki_stage2_eval": "python -m ops.scripts.eval.wiki_stage2_eval --vault . --require-max-score",
    "planning_gate_validate": "python -m ops.scripts.mechanism.planning_gate_validate --vault .",
}
EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY = "urn:openai:artifact-envelope"
EXPECTED_ARCHIVED_RUN_BACKFILL_PATHS = {
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/changed-files-manifest.json": (
        REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json",
        "changed_files_manifest",
    ),
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/planning-validation.json": (
        REPO_ROOT / "ops" / "schemas" / "planning-validation.schema.json",
        "planning_validation",
    ),
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/promotion-report.json": (
        REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json",
        "promotion_report",
    ),
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/run-ledger.json": (
        REPO_ROOT / "ops" / "schemas" / "run-ledger.schema.json",
        "run_ledger",
    ),
}
EXPECTED_CURRENT_SAFE_BACKFILL_REPORTS = {
    "ops/reports/promotion-decision-trends.json": (
        REPO_ROOT / "ops" / "schemas" / "promotion-decision-trends.schema.json",
        "promotion_decision_trends",
    ),
    "ops/reports/sbom-readiness-gate-report.json": (
        REPO_ROOT / "ops" / "schemas" / "sbom-readiness-gate-report.schema.json",
        "sbom_readiness_gate_report",
    ),
    "ops/reports/supply-chain-gate-report.json": (
        REPO_ROOT / "ops" / "schemas" / "supply-chain-gate-report.schema.json",
        "supply_chain_gate_report",
    ),
}
EXPECTED_SAFE_BACKFILLED_RUN_PATHS = {
    "runs/run-20260422-auto-improve-decision-record-fallback-retry/behavior-delta.json": (
        REPO_ROOT / "ops" / "schemas" / "behavior-delta.schema.json",
        "behavior_delta",
    ),
    "runs/run-20260422-auto-improve-decision-record-fallback-retry/run-artifact-fingerprint.json": (
        REPO_ROOT / "ops" / "schemas" / "run-artifact-fingerprint.schema.json",
        "run_artifact_fingerprint",
    ),
    "runs/run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp/behavior-delta.json": (
        REPO_ROOT / "ops" / "schemas" / "behavior-delta.schema.json",
        "behavior_delta",
    ),
    "runs/run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp/run-artifact-fingerprint.json": (
        REPO_ROOT / "ops" / "schemas" / "run-artifact-fingerprint.schema.json",
        "run_artifact_fingerprint",
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/promotion/"
        "raw-intake-promotion-profiles-2026-04-22.json"
    ): (
        REPO_ROOT / "ops" / "schemas" / "raw-intake-promotion-profile-bundle.schema.json",
        "raw_intake_promotion_profile_bundle",
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/promotion/"
        "raw-intake-promotion-render-after-concept-integration-2026-04-22.json"
    ): (
        REPO_ROOT / "ops" / "schemas" / "raw-intake-promotion-report.schema.json",
        "raw_intake_promotion_report",
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/promotion/"
        "raw-intake-promotion-validate-after-concept-integration-2026-04-22.json"
    ): (
        REPO_ROOT / "ops" / "schemas" / "raw-intake-promotion-report.schema.json",
        "raw_intake_promotion_report",
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/validation/"
        "raw-intake-promotion-validate-final-tree-2026-04-22.json"
    ): (
        REPO_ROOT / "ops" / "schemas" / "raw-intake-promotion-report.schema.json",
        "raw_intake_promotion_report",
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/validation/"
        "source-english-summary-slug-validate-final-tree-2026-04-22.json"
    ): (
        REPO_ROOT / "ops" / "schemas" / "source-slug-curation-validation-report.schema.json",
        "source_slug_curation_validation_report",
    ),
}
EXPECTED_ARCHIVED_MECHANISM_ASSESSMENT_EXCLUSION_PATHS = (
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-mechanism-assessment.json",
    "runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-mechanism-assessment.json",
)
EXPECTED_MISSING_SCHEMA_PATHS: set[str] = set()
EXPECTED_NONCANONICAL_ARCHIVED_RUN_NOTE_PATHS = {
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/promotion/"
        "concept-continuity-integration-2026-04-22.json"
    ),
    (
        "runs/run-20260422-raw-intake-registration-and-promotion/registration/"
        "source-english-summary-reregistration-2026-04-22.json"
    ),
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_readiness_loop_health_aggregate(readiness: dict) -> tuple[str, dict]:
    loop_health_summary = readiness.get("diagnostics", {}).get("loop_health_summary", {})
    source_report = str(loop_health_summary.get("source_report", "")).strip()
    assert source_report.startswith(f"{EXPECTED_ROUTING_PROVENANCE_AGGREGATE_REPORT_DIR}/")
    assert source_report.endswith(".json")

    aggregate_path = REPO_ROOT / source_report
    assert aggregate_path.is_file(), f"readiness loop health source is missing: {source_report}"
    return source_report, _read_json(aggregate_path)


def _shape_signature(value: object) -> object:
    if isinstance(value, dict):
        return {key: _shape_signature(val) for key, val in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return []
        return [_shape_signature(value[0])]
    return type(value).__name__


def _observation_by_id(payload: dict, observation_id: str) -> dict:
    observation = next(
        (
            item
            for item in payload.get("observations", [])
            if isinstance(item, dict) and item.get("observation_id") == observation_id
        ),
        None,
    )
    assert observation is not None, f"expected observation {observation_id!r} is missing"
    return observation


def _runtime_context_for_generated_at(iso_z: str) -> RuntimeContext:
    instant = dt.datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
    return RuntimeContext(display_timezone=dt.timezone.utc, clock=lambda: instant)


def test_checked_in_artifact_freshness_report_has_retired_missing_generated_at_bucket() -> None:
    assert ARTIFACT_FRESHNESS_REPORT_PATH.exists(), (
        "artifact freshness canonical report is missing; regenerate ops/reports/artifact-freshness-report.json"
    )

    report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    missing_generated_at = next(
        (item for item in report.get("top_debt", []) if item.get("issue") == "missing_generated_at"),
        None,
    )

    assert missing_generated_at is None


@pytest.mark.artifact_finalization
def test_checked_in_artifact_freshness_report_keeps_stable_debt_axes_explicit() -> None:
    assert ARTIFACT_FRESHNESS_REPORT_PATH.exists(), (
        "artifact freshness canonical report is missing; regenerate ops/reports/artifact-freshness-report.json"
    )

    report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    summary = report.get("summary", {})
    artifact_records = report.get("artifact_records", [])
    run_log_placeholders = report.get("run_log_placeholders", [])
    assert isinstance(artifact_records, list)
    assert isinstance(run_log_placeholders, list)

    assert summary.get("artifact_count") == len(artifact_records)
    assert summary.get("json_artifact_count") == sum(
        1 for item in artifact_records if str(item.get("path", "")).endswith(".json")
    )
    assert summary.get("missing_artifact_envelope_count") == 0
    assert summary.get("unknown_currentness_artifact_count") == 0
    assert summary.get("missing_schema_count") == 0
    assert summary.get("schema_invalid_artifact_count") == 0
    assert summary.get("stable_contract_debt_artifact_count") == 0
    assert summary.get("stable_contract_debt_issue_count") == 0
    assert summary.get("safe_to_backfill_artifact_count") == summary.get("artifact_count")
    assert summary.get("run_log_placeholder_count") == len(run_log_placeholders)
    assert summary.get("mtime_sensitive_attention_artifact_count") == summary.get("mtime_sensitive_artifact_count")
    assert summary.get("mtime_sensitive_attention_issue_count") == summary.get("mtime_sensitive_artifact_count")

    assert set(STABLE_CONTRACT_ISSUES) == {
        "missing_artifact_envelope",
        "unknown_currentness",
        "missing_schema",
        "schema_validation_failed",
        "schema_unavailable",
    }
    top_debt_actions = {item.get("issue"): item.get("recommended_next_action") for item in report.get("top_debt", [])}
    if summary.get("stable_contract_debt_issue_count"):
        stable_top_debt_actions = {
            issue: action for issue, action in top_debt_actions.items() if issue in STABLE_CONTRACT_ISSUES
        }
        assert stable_top_debt_actions
        assert all(action and action != "none" for action in stable_top_debt_actions.values())
    else:
        assert not set(STABLE_CONTRACT_ISSUES) & set(top_debt_actions)
    assert "missing_schema" not in top_debt_actions
    debt_queues = {item.get("queue"): item for item in report.get("debt_queues", [])}
    assert set(debt_queues) == {
        "runs_historical_archive",
        "ops_reports_producer_refresh",
        "operator_reports_producer_refresh",
        "mtime_sensitive_regeneration",
    }
    assert debt_queues["runs_historical_archive"].get("exit_condition")
    assert debt_queues["ops_reports_producer_refresh"].get("exit_condition")
    assert debt_queues["operator_reports_producer_refresh"].get("exit_condition")
    assert debt_queues["mtime_sensitive_regeneration"].get("exit_condition")


def test_checked_in_missing_schema_records_are_fully_retired() -> None:
    assert ARTIFACT_FRESHNESS_REPORT_PATH.exists(), (
        "artifact freshness canonical report is missing; regenerate ops/reports/artifact-freshness-report.json"
    )

    report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    missing_schema_records = [
        item for item in report.get("artifact_records", []) if "missing_schema" in item.get("issues", [])
    ]
    missing_schema_paths = {item.get("path") for item in missing_schema_records}

    assert missing_schema_paths == EXPECTED_MISSING_SCHEMA_PATHS
    assert missing_schema_records == []


def test_checked_in_noncanonical_archived_run_notes_are_excluded_from_stable_debt() -> None:
    assert ARTIFACT_FRESHNESS_REPORT_PATH.exists(), (
        "artifact freshness canonical report is missing; regenerate ops/reports/artifact-freshness-report.json"
    )

    report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    records = {
        item.get("path"): item
        for item in report.get("artifact_records", [])
        if item.get("path") in EXPECTED_NONCANONICAL_ARCHIVED_RUN_NOTE_PATHS
    }

    assert set(records) == EXPECTED_NONCANONICAL_ARCHIVED_RUN_NOTE_PATHS
    for record in records.values():
        assert record.get("contract_issue_class") == "clean"
        assert record.get("issues") == []
        assert record.get("stable_contract_issues") == []
        assert record.get("currentness_status") == "not_applicable"
        assert record.get("schema_validation_status") == "not_applicable"
        assert record.get("schema_contract", {}).get("status") == "not_applicable"
        assert record.get("schema_contract", {}).get("classification") == "noncanonical_archived_run_note"


def test_historical_bootstrap_reports_are_archived_schema_backed_and_portable() -> None:
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    cases = (
        (
            REPO_ROOT / "ops" / "reports" / "archive" / "eval-initial-2026-04-12.json",
            REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json",
            "wiki_eval_report",
        ),
        (
            REPO_ROOT / "ops" / "reports" / "archive" / "lint-initial-2026-04-12.json",
            REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json",
            "wiki_lint_report",
        ),
        (
            REPO_ROOT / "ops" / "reports" / "archive" / "manifest-2026-04-12.json",
            REPO_ROOT / "ops" / "schemas" / "bundle-manifest.schema.json",
            "bundle_manifest",
        ),
    )

    for path, schema_path, artifact_kind in cases:
        payload = _read_json(path)
        schema = load_schema(schema_path)
        record = next(
            (
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == path.relative_to(REPO_ROOT).as_posix()
            ),
            None,
        )

        assert validate_with_schema(payload, schema) == []
        assert payload.get("artifact_kind") == artifact_kind
        assert payload.get("artifact_status") == "archived"
        assert payload.get("retention_policy") == "archive"
        assert payload.get("currentness", {}).get("status") == "current"
        assert payload.get("historical_bootstrap", {}).get("archive_reason") == (
            "historical_bootstrap_snapshot_normalized_to_archive_contract"
        )

        assert record is not None, f"artifact freshness report is missing {path.name}"
        assert record.get("artifact_status") == "archived"
        assert record.get("retention_policy") == "archive"
        assert record.get("issues") == []
        assert record.get("mtime_status") == "current"
        assert record.get("schema_validation_status") == "pass"

    eval_payload = _read_json(REPO_ROOT / "ops" / "reports" / "archive" / "eval-initial-2026-04-12.json")
    lint_payload = _read_json(REPO_ROOT / "ops" / "reports" / "archive" / "lint-initial-2026-04-12.json")

    assert eval_payload.get("vault") == "."
    assert eval_payload.get("policy") == {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 0}
    assert all("/mnt/data/" not in item.get("page", "") for item in eval_payload.get("pages", []))
    assert lint_payload.get("vault") == "."
    assert lint_payload.get("review_candidates") == []
    assert lint_payload.get("policy") == {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 0}


def test_checked_in_archived_run_safe_backfill_artifacts_embed_archived_envelopes_and_are_debt_free() -> None:
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)

    for rel_path, (schema_path, artifact_kind) in EXPECTED_ARCHIVED_RUN_BACKFILL_PATHS.items():
        payload = _read_json(REPO_ROOT / rel_path)
        schema = load_schema(schema_path)
        properties = payload.get("metadata", {}).get("properties", [])
        embedded_envelope_text = next(
            (
                item.get("value")
                for item in properties
                if isinstance(item, dict) and item.get("name") == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            ),
            None,
        )
        record = next(
            (item for item in freshness_report.get("artifact_records", []) if item.get("path") == rel_path),
            None,
        )

        assert validate_with_schema(payload, schema) == []
        assert isinstance(embedded_envelope_text, str) and embedded_envelope_text.strip(), (
            f"{rel_path} is missing the embedded archived artifact envelope"
        )

        embedded_envelope = json.loads(embedded_envelope_text)
        assert embedded_envelope.get("artifact_kind") == artifact_kind
        assert embedded_envelope.get("artifact_status") == "archived"
        assert embedded_envelope.get("retention_policy") == "archive"
        assert embedded_envelope.get("currentness", {}).get("status") == "current"

        assert record is not None, f"artifact freshness report is missing {rel_path}"
        assert record.get("artifact_kind") == artifact_kind
        assert record.get("artifact_status") == "archived"
        assert record.get("retention_policy") == "archive"
        assert record.get("issues") == []
        assert record.get("has_generated_at") is True
        assert record.get("has_artifact_envelope") is True
        assert record.get("currentness_status") == "current"
        assert record.get("schema_validation_status") == "pass"


def test_checked_in_current_safe_backfill_reports_have_envelopes_and_no_stable_debt() -> None:
    readiness = _read_json(AUTO_IMPROVE_READINESS_REPORT_PATH)
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    routing_aggregate_path, _routing_aggregate = _read_readiness_loop_health_aggregate(readiness)
    expected_reports = {
        **EXPECTED_CURRENT_SAFE_BACKFILL_REPORTS,
        routing_aggregate_path: (
            REPO_ROOT / "ops" / "schemas" / "routing-provenance-aggregate.schema.json",
            "routing_provenance_aggregate",
        ),
    }

    for rel_path, (schema_path, artifact_kind) in expected_reports.items():
        payload = _read_json(REPO_ROOT / rel_path)
        schema = load_schema(schema_path)
        record = next(
            (item for item in freshness_report.get("artifact_records", []) if item.get("path") == rel_path),
            None,
        )

        assert validate_with_schema(payload, schema) == []
        assert payload.get("artifact_kind") == artifact_kind
        assert payload.get("artifact_status") == "current"
        assert payload.get("retention_policy") == "canonical_report"
        assert payload.get("currentness", {}).get("status") == "current"

        assert record is not None, f"artifact freshness report is missing {rel_path}"
        assert record.get("artifact_kind") == artifact_kind
        assert record.get("has_artifact_envelope") is True
        assert record.get("currentness_status") == "current"
        assert record.get("schema_validation_status") == "pass"
        issues = set(record.get("issues", []))
        assert "missing_artifact_envelope" not in issues
        assert "unknown_currentness" not in issues


def test_checked_in_safe_backfilled_run_artifacts_embed_archived_envelopes_and_are_debt_free() -> None:
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)

    for rel_path, (schema_path, artifact_kind) in EXPECTED_SAFE_BACKFILLED_RUN_PATHS.items():
        payload = _read_json(REPO_ROOT / rel_path)
        schema = load_schema(schema_path)
        properties = payload.get("metadata", {}).get("properties", [])
        embedded_envelope_text = next(
            (
                item.get("value")
                for item in properties
                if isinstance(item, dict) and item.get("name") == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            ),
            None,
        )
        record = next(
            (item for item in freshness_report.get("artifact_records", []) if item.get("path") == rel_path),
            None,
        )

        assert validate_with_schema(payload, schema) == []
        assert isinstance(embedded_envelope_text, str) and embedded_envelope_text.strip(), (
            f"{rel_path} is missing the embedded archived artifact envelope"
        )

        embedded_envelope = json.loads(embedded_envelope_text)
        assert embedded_envelope.get("artifact_kind") == artifact_kind
        assert embedded_envelope.get("artifact_status") == "archived"
        assert embedded_envelope.get("retention_policy") == "archive"
        assert embedded_envelope.get("currentness", {}).get("status") == "current"

        assert record is not None, f"artifact freshness report is missing {rel_path}"
        assert record.get("artifact_kind") == artifact_kind
        assert record.get("artifact_status") == "archived"
        assert record.get("retention_policy") == "archive"
        assert record.get("issues") == []
        assert record.get("has_generated_at") is True
        assert record.get("has_artifact_envelope") is True
        assert record.get("currentness_status") == "current"
        assert record.get("schema_validation_status") == "pass"


def test_checked_in_archived_mechanism_assessment_pair_remains_schema_valid_and_debt_free() -> None:
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)

    for rel_path in EXPECTED_ARCHIVED_MECHANISM_ASSESSMENT_EXCLUSION_PATHS:
        record = next(
            (item for item in freshness_report.get("artifact_records", []) if item.get("path") == rel_path),
            None,
        )

        assert record is not None, f"artifact freshness report is missing {rel_path}"
        assert record.get("has_schema") is True
        assert record.get("has_generated_at") is True
        assert record.get("has_artifact_envelope") is True
        assert record.get("contract_issue_class") == "clean"
        assert record.get("issues") == []
        assert record.get("artifact_kind") == "mechanism_assessment_report"
        assert record.get("artifact_status") == "archived"
        assert record.get("retention_policy") == "archive"
        assert record.get("schema_validation_status") == "pass"
        assert record.get("mtime_source") == "embedded_currentness"
        assert record.get("mtime_status") == "current"
        assert record.get("stable_contract_issues", []) == []
        assert record.get("mtime_sensitive_issues", []) == []


def test_checked_in_mechanism_review_report_has_no_unclassified_skipped_runs() -> None:
    assert MECHANISM_REVIEW_REPORT_PATH.exists(), (
        "mechanism review canonical report is missing; regenerate ops/reports/mechanism-review-candidates.json"
    )

    report = _read_json(MECHANISM_REVIEW_REPORT_PATH)

    assert report.get("summary", {}).get("runs_skipped") == 0
    assert report.get("diagnostics", {}).get("skipped_runs") == []

    excluded_runs = report.get("diagnostics", {}).get("excluded_runs", [])
    archived_run = next((item for item in excluded_runs if item.get("run_id") == EXPECTED_ARCHIVED_RUN_ID), None)

    assert archived_run is not None, "expected archived run is missing from diagnostics.excluded_runs"
    assert archived_run.get("status") == "archived"


def test_checked_in_cyclonedx_bom_embeds_envelope_and_is_debt_free() -> None:
    assert CYCLONEDX_BOM_PATH.exists(), (
        "CycloneDX BOM is missing; regenerate ops/reports/cyclonedx-bom.json"
    )

    payload = _read_json(CYCLONEDX_BOM_PATH)
    properties = payload.get("metadata", {}).get("properties", [])
    embedded_envelope_text = next(
        (
            item.get("value")
            for item in properties
            if isinstance(item, dict) and item.get("name") == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
        ),
        None,
    )

    assert isinstance(embedded_envelope_text, str) and embedded_envelope_text.strip(), (
        "CycloneDX BOM is missing the embedded artifact envelope property"
    )

    embedded_envelope = json.loads(embedded_envelope_text)
    assert embedded_envelope.get("artifact_kind") == "cyclonedx_sbom"
    assert embedded_envelope.get("artifact_status") == "current"
    assert embedded_envelope.get("currentness", {}).get("status") == "current"

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (item for item in freshness_report.get("artifact_records", []) if item.get("path") == EXPECTED_CYCLONEDX_BOM_PATH),
        None,
    )

    assert record is not None, "artifact freshness report is missing the CycloneDX BOM record"
    assert record.get("artifact_kind") == "cyclonedx_sbom"
    issues = set(record.get("issues", []))
    assert "missing_artifact_envelope" not in issues
    assert "unknown_currentness" not in issues
    assert "missing_generated_at" not in issues
    assert record.get("has_generated_at") is True
    assert record.get("has_artifact_envelope") is True
    assert record.get("currentness_status") == "current"
    assert record.get("schema_validation_status") == "pass"


def test_checked_in_manual_mutate_registry_is_current_and_debt_free() -> None:
    assert MANUAL_MUTATE_REPORT_PATH.exists(), (
        "manual mutate defect registry is missing; regenerate ops/reports/manual-mutate-defect-registry.json"
    )

    payload = _read_json(MANUAL_MUTATE_REPORT_PATH)
    schema = load_schema(MANUAL_MUTATE_REPORT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "manual_mutate_defect_registry"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert "manual_mutate_scripts" in payload.get("input_fingerprints", {})

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (item for item in freshness_report.get("artifact_records", []) if item.get("path") == EXPECTED_MANUAL_MUTATE_REPORT_PATH),
        None,
    )

    assert record is not None, "artifact freshness report is missing the manual mutate registry record"
    assert record.get("issues") == []


def test_checked_in_openvex_draft_is_current_and_debt_reduced() -> None:
    assert OPENVEX_DRAFT_PATH.exists(), (
        "OpenVEX draft is missing; regenerate ops/reports/openvex-draft.json"
    )

    payload = _read_json(OPENVEX_DRAFT_PATH)
    schema = load_schema(OPENVEX_DRAFT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "openvex_draft"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("generated_at") == payload.get("timestamp")
    assert "artifact_model" in payload.get("input_fingerprints", {})

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (item for item in freshness_report.get("artifact_records", []) if item.get("path") == EXPECTED_OPENVEX_DRAFT_PATH),
        None,
    )

    assert record is not None, "artifact freshness report is missing the OpenVEX draft record"
    assert record.get("artifact_kind") == "openvex_draft"
    issues = set(record.get("issues", []))
    assert "missing_artifact_envelope" not in issues
    assert "unknown_currentness" not in issues
    assert "missing_generated_at" not in issues
    assert record.get("has_generated_at") is True
    assert record.get("has_artifact_envelope") is True
    assert record.get("currentness_status") == "current"
    assert record.get("schema_validation_status") == "pass"


def test_checked_in_review_archive_report_is_current_and_schema_backed() -> None:
    assert REVIEW_ARCHIVE_REPORT_PATH.exists(), (
        "review archive canonical report is missing; regenerate ops/reports/review-archive-report.json"
    )

    payload = _read_json(REVIEW_ARCHIVE_REPORT_PATH)
    schema = load_schema(REVIEW_ARCHIVE_REPORT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "review_archive_report"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (item for item in freshness_report.get("artifact_records", []) if item.get("path") == EXPECTED_REVIEW_ARCHIVE_REPORT_PATH),
        None,
    )

    assert record is not None, "artifact freshness report is missing the review archive record"
    assert record.get("artifact_kind") == "review_archive_report"
    issues = set(record.get("issues", []))
    assert "missing_artifact_envelope" not in issues
    assert "unknown_currentness" not in issues
    assert "missing_schema" not in issues
    assert record.get("has_schema") is True
    assert record.get("has_generated_at") is True
    assert record.get("has_artifact_envelope") is True
    assert record.get("currentness_status") == "current"
    assert record.get("schema_validation_status") == "pass"


def test_checked_in_raw_registry_preflight_report_is_schema_backed_and_debt_free() -> None:
    assert RAW_REGISTRY_PREFLIGHT_REPORT_PATH.exists(), (
        "raw registry preflight report is missing; regenerate ops/reports/raw-registry-preflight-report.json"
    )

    payload = _read_json(RAW_REGISTRY_PREFLIGHT_REPORT_PATH)
    schema = load_schema(RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "raw_registry_preflight_report"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("extraction_tool")
    assert payload.get("locale")
    assert payload.get("path_alias_resolution_mode")
    assert payload.get("alias_policy_version") == "raw_registry_alias_resolution_v1"
    assert payload.get("environment_fingerprint", {}).get("value")
    assert payload.get("metric_semantics", {}).get("path_alias_match_count")
    assert payload.get("unsupported_environment") is False

    stats = payload.get("stats", {})
    for key in (
        "entry_count",
        "error_count",
        "warning_count",
        "path_alias_match_count",
        "content_hash_fallback_count",
    ):
        assert key in stats

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_RAW_REGISTRY_PREFLIGHT_REPORT_PATH
        ),
        None,
    )

    assert record is not None, "artifact freshness report is missing the raw registry preflight record"
    assert record.get("artifact_kind") == "raw_registry_preflight_report"
    assert record.get("issues") == []


def test_checked_in_raw_registry_preflight_reproducibility_is_schema_backed_and_debt_free() -> None:
    assert RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_PATH.exists(), (
        "raw registry preflight reproducibility report is missing; "
        "regenerate ops/reports/raw-registry-preflight-reproducibility.json"
    )

    payload = _read_json(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_PATH)
    schema = load_schema(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "raw_registry_preflight_reproducibility"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("diff_status") == "match"
    assert payload.get("status") == "pass"
    assert payload.get("path_alias_resolution_mode")
    assert payload.get("alias_policy_version") == "raw_registry_alias_resolution_v1"
    assert payload.get("environment_fingerprint", {}).get("value")
    assert payload.get("metric_semantics", {}).get("path_alias_match_count")
    assert all(item.get("status") == "match" for item in payload.get("comparisons", []))

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_PATH
        ),
        None,
    )

    assert record is not None, (
        "artifact freshness report is missing the raw registry preflight reproducibility record"
    )
    assert record.get("artifact_kind") == "raw_registry_preflight_reproducibility"
    assert record.get("issues") == []


def test_checked_in_raw_registry_cross_environment_matrix_is_schema_backed_and_debt_free() -> None:
    assert RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_PATH.exists(), (
        "raw registry cross-environment matrix report is missing; "
        "regenerate ops/reports/raw-registry-cross-environment-matrix.json"
    )

    payload = _read_json(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_PATH)
    schema = load_schema(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "raw_registry_cross_environment_matrix"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("status") == "pass"
    assert payload.get("path_alias_resolution_mode")
    assert payload.get("alias_policy_version") == "raw_registry_alias_resolution_v1"
    assert payload.get("environment_fingerprint", {}).get("value")
    rows = {item.get("profile"): item for item in payload.get("matrix", [])}
    assert {"linux-c-utf8", "windows-utf8", "macos-utf8"} <= set(rows)
    assert rows["linux-c-utf8"].get("status") == "pass"
    assert rows["windows-utf8"].get("status") == "pass"
    assert rows["macos-utf8"].get("status") == "pass"
    assert rows["path-separator-fixture"].get("status") == "pass"
    assert rows["locale-utf8-fixture"].get("status") == "pass"

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_PATH
        ),
        None,
    )

    assert record is not None, (
        "artifact freshness report is missing the raw registry cross-environment matrix record"
    )
    assert record.get("artifact_kind") == "raw_registry_cross_environment_matrix"
    assert record.get("issues") == []


def test_checked_in_release_risk_taxonomy_matrix_is_schema_backed_and_markdown_backed() -> None:
    assert RELEASE_RISK_TAXONOMY_MATRIX_PATH.exists(), (
        "release risk taxonomy matrix report is missing; "
        "regenerate ops/reports/release-risk-taxonomy-matrix.json"
    )
    assert RELEASE_RISK_TAXONOMY_MATRIX_MARKDOWN_PATH.exists(), (
        "release risk taxonomy matrix Markdown is missing; "
        "regenerate ops/reports/release-risk-taxonomy-matrix.md"
    )

    payload = _read_json(RELEASE_RISK_TAXONOMY_MATRIX_PATH)
    schema = load_schema(RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "release_risk_taxonomy_matrix"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("status") == "pass"
    rows = {item.get("code"): item for item in payload.get("matrix", [])}
    assert "release_risk_taxonomy_unregistered_code" in rows
    assert "learning_blocked_by_review_required" in rows
    archive_advisory = rows.get("generated_index_archive_advisory", {})
    assert archive_advisory.get("advisory_lifecycle_effect") == "review_backlog"
    assert archive_advisory.get("clean_lane_effect") == "does_not_block_clean_lane"

    markdown = RELEASE_RISK_TAXONOMY_MATRIX_MARKDOWN_PATH.read_text(encoding="utf-8")
    assert "| Risk code | Primary lane | Clean | Conditional | Learning | Advisory | Surface |" in markdown
    assert all(code in markdown for code in rows)


@pytest.mark.artifact_finalization
def test_checked_in_release_risk_taxonomy_matrix_has_freshness_record() -> None:
    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_RELEASE_RISK_TAXONOMY_MATRIX_PATH
        ),
        None,
    )

    assert record is not None, "artifact freshness report is missing the release risk taxonomy matrix record"
    assert record.get("artifact_kind") == "release_risk_taxonomy_matrix"
    assert record.get("issues") == []


@pytest.mark.artifact_finalization
def test_checked_in_test_execution_summary_is_schema_backed_and_debt_free() -> None:
    assert TEST_EXECUTION_SUMMARY_PATH.exists(), (
        "test execution summary is missing; regenerate ops/reports/test-execution-summary.json"
    )

    payload = _read_json(TEST_EXECUTION_SUMMARY_PATH)
    schema = load_schema(TEST_EXECUTION_SUMMARY_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "test_execution_summary"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("status") in {"pass", "fail", "timeout", "interrupted", "partial-pass"}
    assert payload.get("command")
    assert payload.get("termination_reason")
    environment = payload.get("execution_environment", {})
    assert environment.get("python_version")
    assert environment.get("pytest_version")
    assert environment.get("interpreter_path_class") in {
        "path_lookup",
        "repo_virtualenv",
        "repo_relative",
        "repo_absolute",
        "relative_external",
        "external_virtualenv",
        "external_absolute",
        "unknown",
    }
    plugin_policy = environment.get("plugin_autoload_policy", {})
    assert plugin_policy.get("env_var") == "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
    assert plugin_policy.get("policy") in {"disabled", "not_set", "custom"}
    target_fingerprints = payload.get("test_target_fingerprints", [])
    assert target_fingerprints
    input_fingerprints = payload.get("input_fingerprints", {})
    if payload.get("summary_mode") == "aggregate":
        assert input_fingerprints.get("shard_1")
        assert input_fingerprints.get("summary_mode")
        assert payload.get("shards")
    else:
        assert input_fingerprints.get("test_targets")
    assert {item.get("path") for item in target_fingerprints} >= {
        "tests/test_test_execution_summary.py",
        "tests/test_generated_report_contracts.py",
    }
    collect_digest = payload.get("pytest_collect_nodeid_digest", {})
    assert collect_digest.get("status") in {"collected", "skipped"}
    assert collect_digest.get("nodeid_count", 0) > 0
    if collect_digest.get("status") == "collected":
        assert collect_digest.get("sha256")
    else:
        assert collect_digest.get("reason") == "aggregate report reuses shard nodeid digests"
    deselected_tests = payload.get("deselected_tests", [])
    assert deselected_tests == []
    lifecycle = payload.get("deselection_lifecycle", {})
    assert lifecycle.get("status") == "pass"
    assert lifecycle.get("actual_deselected_count") == 0
    assert lifecycle.get("max_allowed_deselected_count") == 0

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_TEST_EXECUTION_SUMMARY_PATH
        ),
        None,
    )

    assert record is not None, "artifact freshness report is missing the test execution summary record"
    assert record.get("artifact_kind") == "test_execution_summary"
    assert record.get("issues") == []


def test_checked_in_release_smoke_report_uses_full_profile_and_sanitized_commands() -> None:
    assert RELEASE_SMOKE_REPORT_PATH.exists(), (
        "release smoke canonical report is missing; regenerate ops/reports/release-smoke-report.json"
    )

    payload = _read_json(RELEASE_SMOKE_REPORT_PATH)
    schema = load_schema(RELEASE_SMOKE_REPORT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "release_smoke_report"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("profile") == "full"
    assert payload.get("status") == "pass"
    assert payload.get("source_command") == "python -m ops.scripts.release.release_smoke --vault . --profile full"
    assert payload.get("manifest_comparison", {}).get("pass") is True

    commands = payload.get("commands", [])
    assert [item.get("name") for item in commands] == list(EXPECTED_RELEASE_SMOKE_COMMANDS)
    for item in commands:
        expected_command = EXPECTED_RELEASE_SMOKE_COMMANDS[item["name"]]
        assert item.get("command") == expected_command
        assert "/mnt/" not in expected_command
        assert "\\Users\\" not in expected_command
        assert "<tmp>" not in expected_command

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (item for item in freshness_report.get("artifact_records", []) if item.get("path") == EXPECTED_RELEASE_SMOKE_REPORT_PATH),
        None,
    )

    assert record is not None, "artifact freshness report is missing the release smoke record"
    assert record.get("artifact_kind") == "release_smoke_report"
    assert record.get("issues") == []


@pytest.mark.artifact_finalization
def test_checked_in_release_smoke_report_matches_live_envelope_fingerprints() -> None:
    assert RELEASE_SMOKE_REPORT_PATH.exists(), (
        "release smoke canonical report is missing; regenerate ops/reports/release-smoke-report.json"
    )

    payload = _read_json(RELEASE_SMOKE_REPORT_PATH)
    policy, resolved_policy_path = load_policy(REPO_ROOT)
    expected_envelope = build_canonical_report_envelope(
        REPO_ROOT,
        generated_at=str(payload.get("generated_at")),
        artifact_kind="release_smoke_report",
        producer="ops.scripts.release_smoke",
        source_command="python -m ops.scripts.release.release_smoke --vault . --profile full",
        resolved_policy_path=resolved_policy_path,
        schema_path="ops/schemas/release-smoke-report.schema.json",
        source_paths=EXPECTED_RELEASE_SMOKE_SOURCE_PATHS,
    )

    assert payload.get("source_tree_fingerprint") == expected_envelope.get("source_tree_fingerprint"), (
        "checked-in release smoke report is stale; regenerate ops/reports/release-smoke-report.json"
    )
    assert payload.get("input_fingerprints") == expected_envelope.get("input_fingerprints"), (
        "checked-in release smoke report has drifted input fingerprints; regenerate ops/reports/release-smoke-report.json"
    )


@pytest.mark.artifact_finalization
def test_checked_in_generated_artifact_index_matches_live_inventory_and_fingerprints() -> None:
    assert GENERATED_ARTIFACT_INDEX_PATH.exists(), (
        "generated artifact index canonical report is missing; regenerate ops/reports/generated-artifact-index.json"
    )

    payload = _read_json(GENERATED_ARTIFACT_INDEX_PATH)
    schema = load_schema(GENERATED_ARTIFACT_INDEX_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    regenerated = build_generated_artifact_index_report(
        REPO_ROOT,
        context=_runtime_context_for_generated_at(str(payload.get("generated_at"))),
    )

    assert regenerated == payload, (
        "checked-in generated artifact index is stale; regenerate ops/reports/generated-artifact-index.json"
    )


@pytest.mark.artifact_finalization
def test_source_derived_workflow_planner_contract_is_covered_by_checked_in_artifacts() -> None:
    action_matrix = _read_json(REPO_ROOT / "ops" / "reports" / "external-report-action-matrix.json")
    cohort = _read_json(REPO_ROOT / "ops" / "reports" / "release-evidence-cohort.json")

    release_writer_action = next(
        item
        for item in action_matrix.get("action_items", [])
        if item.get("action_id") == "release_writer_dependency_single_source"
    )
    assert release_writer_action.get("current_status") == "implemented"
    evidence_paths = {item.get("path") for item in release_writer_action.get("evidence", [])}
    assert evidence_paths == {
        "tmp/workflow-dependency-planner.json",
        "tmp/release-workflow-order-guard.json",
    }

    ordered_targets = [item.get("target") for item in cohort.get("ordered_chain", [])]
    assert "generated-artifact-index" in ordered_targets
    assert "artifact-freshness" in ordered_targets
    assert "release-closeout-summary" in ordered_targets


def test_review_archive_checked_in_baseline_stays_in_sync_with_shared_schema_sample() -> None:
    sample = _read_json(REPORT_SCHEMA_SAMPLES_PATH).get("review_archive", {})
    payload = _read_json(REVIEW_ARCHIVE_REPORT_PATH)

    assert sample.get("$schema") == payload.get("$schema")
    assert sample.get("artifact_kind") == payload.get("artifact_kind")
    assert sample.get("producer") == payload.get("producer")
    assert sample.get("source_command") == payload.get("source_command")
    assert sample.get("exclusion_policy") == payload.get("exclusion_policy")
    assert _shape_signature(sample) == _shape_signature(payload)


@pytest.mark.artifact_finalization
def test_checked_in_auto_improve_readiness_reflects_trial_only_authority_preflight_state() -> None:
    assert AUTO_IMPROVE_READINESS_REPORT_PATH.exists(), (
        "auto-improve readiness canonical report is missing; regenerate ops/reports/auto-improve-readiness.json"
    )

    payload = _read_json(AUTO_IMPROVE_READINESS_REPORT_PATH)
    schema = load_schema(AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    assert payload.get("artifact_kind") == "auto_improve_readiness_report"
    assert payload.get("artifact_status") == "current"
    assert payload.get("currentness", {}).get("status") == "current"
    assert payload.get("learning_readiness", {}).get("status") == LEARNING_STATUS_LIKELY
    assert payload.get("can_execute_trial") is True
    can_promote_result = payload.get("can_promote_result")
    assert payload.get("execution_readiness", {}).get("can_run") is True
    assert payload.get("queue", {}).get("ready") is True
    assert int(payload.get("queue", {}).get("runnable_proposal_count", 0)) > 0
    assert payload.get("diagnostics", {}).get("loop_health_summary", {}).get("status") == "available"
    assert payload.get("learning_readiness", {}).get("metrics", {}).get("telemetry_coverage_ratio") == payload.get(
        "diagnostics", {}
    ).get("loop_health_summary", {}).get("telemetry_coverage_ratio")

    signal_ids = {
        str(item.get("id", "")).strip()
        for item in payload.get("learning_readiness", {}).get("signals", [])
        if isinstance(item, dict)
    }
    assert "mechanism_review_session_context_missing" not in signal_ids
    assert "loop_health_telemetry_coverage_missing" not in signal_ids
    assert "same_eval_typed_evidence_missing" not in signal_ids
    assert payload.get("learning_readiness", {}).get("metrics", {}).get(
        "same_eval_reason_code_coverage_ratio"
    ) == 1.0
    assert payload.get("learning_readiness", {}).get("metrics", {}).get(
        "strict_secondary_improvement_coverage_ratio"
    ) == 1.0
    assert payload.get("learning_readiness", {}).get("metrics", {}).get(
        "behavior_delta_digest_coverage_ratio"
    ) == 1.0
    assert signal_ids == set()
    for signal in payload.get("learning_readiness", {}).get("signals", []):
        assert signal.get("owner") == "runtime-maintainer"
        assert signal.get("required_evidence")
        assert int(signal.get("minimum_sample_size", 0)) >= 1
        assert str(signal.get("next_evaluation_command", "")).startswith("make ")
        assert signal.get("closure_strategy")
    assert payload.get("learning_blockers") == []
    promotion_blocker_ids = {
        str(item.get("id", "")).strip()
        for item in payload.get("promotion_blockers", [])
        if isinstance(item, dict)
    }
    closeout_summary = payload.get("diagnostics", {}).get("release_closeout_summary", {})
    assert closeout_summary.get("source_status") == "pass"
    if closeout_summary.get("release_blocking") is True:
        assert closeout_summary.get("status") == "fail"
        assert "promotion_blocked_by_release_closeout_summary_failure" in promotion_blocker_ids
    else:
        assert closeout_summary.get("status") == "pass"
        assert "promotion_blocked_by_release_closeout_summary_failure" not in promotion_blocker_ids
    batch_manifest_summary = payload.get("diagnostics", {}).get(
        "release_closeout_batch_manifest_summary", {}
    )
    if batch_manifest_summary.get("release_blocking") is True:
        assert "promotion_blocked_by_release_batch_manifest_failure" in promotion_blocker_ids
    else:
        assert batch_manifest_summary.get("status") == "pass"
        assert "promotion_blocked_by_release_batch_manifest_failure" not in promotion_blocker_ids
    assert payload.get("release_blockers") == []
    evidence_cohort_summary = payload.get("diagnostics", {}).get("release_evidence_cohort_summary", {})
    if evidence_cohort_summary.get("release_blocking") is True:
        assert evidence_cohort_summary.get("status") == "fail"
        assert "promotion_blocked_by_release_lineage_mismatch" in promotion_blocker_ids
    else:
        assert evidence_cohort_summary.get("status") == "pass"
        assert "promotion_blocked_by_release_lineage_mismatch" not in promotion_blocker_ids
    artifact_finalization = payload.get("diagnostics", {}).get("artifact_finalization_summary", {})
    assert artifact_finalization.get("status") == "pass"
    assert artifact_finalization.get("source_status") in {"pass", "finality_attested_pass"}
    authority_preflight = payload.get("diagnostics", {}).get(
        "release_authority_preflight_summary", {}
    )
    if authority_preflight.get("preflight_status") == "sealed_clean_pass":
        assert "promotion_blocked_by_release_authority_preflight_failure" not in promotion_blocker_ids
        assert authority_preflight.get("distribution_binding_status") == "pass"
        assert authority_preflight.get("authority_preflight_status") == "clean"
    else:
        assert "promotion_blocked_by_release_authority_preflight_failure" in promotion_blocker_ids
        authority_preflight_blocker = next(
            item
            for item in payload.get("promotion_blockers", [])
            if item.get("id") == "promotion_blocked_by_release_authority_preflight_failure"
        )
        assert authority_preflight_blocker.get("scope") == "release_gate"
        expected_signal_ids = [
            str(item).strip()
            for item in [
                *authority_preflight.get("blocker_reason_ids", []),
                *authority_preflight.get("failure_ids", []),
            ]
            if str(item).strip()
        ]
        assert authority_preflight_blocker.get("signal_ids") == (
            expected_signal_ids or ["release_authority_preflight_not_clean"]
        )
        if authority_preflight.get("preflight_status") == "not_run":
            assert authority_preflight.get("distribution_binding_status") == "unknown"
        else:
            assert authority_preflight.get("status") == "fail"
            assert authority_preflight.get("distribution_binding_status") in {"pass", "fail"}
            assert authority_preflight_blocker.get("signal_ids") != [
                "release_authority_preflight_not_clean"
            ]
    assert can_promote_result is (len(promotion_blocker_ids) == 0)
    if promotion_blocker_ids:
        assert payload.get("next_action", "").startswith("Trial only; do not promote.")
    else:
        assert not payload.get("next_action", "").startswith("Trial only; do not promote.")

    freshness_report = _read_json(ARTIFACT_FRESHNESS_REPORT_PATH)
    record = next(
        (
            item
            for item in freshness_report.get("artifact_records", [])
            if item.get("path") == EXPECTED_AUTO_IMPROVE_READINESS_REPORT_PATH
        ),
        None,
    )

    assert record is not None, "artifact freshness report is missing the auto-improve readiness record"
    assert record.get("artifact_kind") == "auto_improve_readiness_report"
    assert record.get("issues") == []


def test_checked_in_auto_improve_readiness_keeps_evidence_ledgers_in_sync() -> None:
    readiness = _read_json(AUTO_IMPROVE_READINESS_REPORT_PATH)
    mechanism_review = _read_json(MECHANISM_REVIEW_REPORT_PATH)
    outcome_metrics = _read_json(OUTCOME_METRICS_REPORT_PATH)
    routing_aggregate_path, routing_provenance_aggregate = _read_readiness_loop_health_aggregate(readiness)

    learning_metrics = readiness.get("learning_readiness", {}).get("metrics", {})
    learning_signals = {
        str(item.get("id", "")).strip()
        for item in readiness.get("learning_readiness", {}).get("signals", [])
        if isinstance(item, dict)
    }
    session_calibration = mechanism_review.get("diagnostics", {}).get("session_calibration", {})
    outcome_summary = outcome_metrics.get("summary", {})
    outcome_metric_block = outcome_metrics.get("metrics", {})
    loop_health_summary = readiness.get("diagnostics", {}).get("loop_health_summary", {})
    aggregate_loop_health = routing_provenance_aggregate.get("audit_rollup", {}).get("loop_health", {})

    assert learning_metrics.get("attempts_considered") == outcome_summary.get("attempts_considered")
    assert learning_metrics.get("session_reports_considered") == outcome_summary.get("session_reports_considered")
    assert learning_metrics.get("session_calibration_status") == session_calibration.get("status")
    assert learning_metrics.get("rework_count") == outcome_metric_block.get("rework_count")
    assert learning_metrics.get("hold_moving_average") == outcome_metric_block.get("moving_averages", {}).get("hold")
    assert learning_metrics.get("discard_moving_average") == outcome_metric_block.get("moving_averages", {}).get(
        "discard"
    )
    assert learning_metrics.get("defect_escape_pair_count") == outcome_metric_block.get(
        "defect_escape_proxy", {}
    ).get("count")

    assert loop_health_summary.get("source_report") == routing_aggregate_path
    assert loop_health_summary.get("source_generated_at") == routing_provenance_aggregate.get("generated_at")
    assert loop_health_summary.get("attempt_count") == aggregate_loop_health.get("attempt_count")
    assert loop_health_summary.get("rework_count") == aggregate_loop_health.get("rework_count")
    assert loop_health_summary.get("rollback_signal_count") == aggregate_loop_health.get("rollback_signal_count")
    assert loop_health_summary.get("defect_escape_count") == aggregate_loop_health.get("defect_escape_count")
    assert loop_health_summary.get("telemetry_coverage_ratio") == aggregate_loop_health.get("coverage_ratios", {}).get(
        "telemetry"
    )
    assert loop_health_summary.get("health_flags") == aggregate_loop_health.get("health_flags")

    if session_calibration.get("status") == "no_session_context":
        assert "mechanism_review_session_context_missing" in learning_signals
    if loop_health_summary.get("telemetry_coverage_ratio", 1.0) <= 0.0:
        assert "loop_health_telemetry_coverage_missing" in learning_signals
    if not readiness.get("learning_readiness", {}).get("likely_to_learn", True):
        blocker = readiness.get("release_blockers", [{}])[0]
        assert blocker.get("scope") == "learning_readiness"
        assert blocker.get("source_status") == readiness.get("learning_readiness", {}).get("status")
        assert set(blocker.get("signal_ids", [])) == learning_signals


def test_checked_in_reconciliation_observations_validate_and_keep_key_entries() -> None:
    assert IMPROVEMENT_OBSERVATIONS_PATH.exists(), (
        "reconciliation improvement observations are missing; restore the task observation artifact"
    )

    payload = _read_json(IMPROVEMENT_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []

    observation_ids = {
        str(item.get("observation_id", "")).strip()
        for item in payload.get("observations", [])
        if isinstance(item, dict)
    }

    assert "artifact_freshness_missing_generated_at_action" in observation_ids
    assert "openvex_draft_envelope_backfill" in observation_ids
    assert "promotion_input_missing_artifact_triage" in observation_ids


def test_review_archive_observations_validate_and_record_automated_parity_guard() -> None:
    assert REVIEW_ARCHIVE_OBSERVATIONS_PATH.exists(), (
        "review-archive improvement observations are missing; restore the task observation artifact"
    )

    payload = _read_json(REVIEW_ARCHIVE_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    observation = _observation_by_id(payload, "review_archive_fixture_parity_guard")
    assert observation.get("status") == "automated"


def test_learning_evidence_observations_validate_and_record_automated_guard() -> None:
    assert LEARNING_EVIDENCE_OBSERVATIONS_PATH.exists(), (
        "learning-evidence improvement observations are missing; restore the task observation artifact"
    )

    payload = _read_json(LEARNING_EVIDENCE_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    observation = _observation_by_id(payload, "learning_readiness_evidence_ledger_guard")
    assert observation.get("status") == "automated"


def test_raw_registry_reproduction_observations_validate_and_record_protocol_guard() -> None:
    assert RAW_REGISTRY_REPRODUCTION_OBSERVATIONS_PATH.exists(), (
        "raw-registry reproduction observations are missing; restore the task observation artifact"
    )

    payload = _read_json(RAW_REGISTRY_REPRODUCTION_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    observation = _observation_by_id(payload, "raw_registry_extracted_zip_reproduction_guard")
    assert observation.get("status") == "automated"


def test_pytest_release_smoke_hardening_observations_validate_and_record_automated_guards() -> None:
    assert PYTEST_RELEASE_SMOKE_HARDENING_OBSERVATIONS_PATH.exists(), (
        "pytest/release-smoke hardening observations are missing; restore the task observation artifact"
    )

    payload = _read_json(PYTEST_RELEASE_SMOKE_HARDENING_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    pytest_observation = _observation_by_id(payload, "pytest_entrypoint_contract_static_guard")
    release_smoke_observation = _observation_by_id(payload, "release_smoke_profile_tiering_and_command_hygiene")
    assert pytest_observation.get("status") == "automated"
    assert release_smoke_observation.get("status") == "automated"


def test_stable_artifact_debt_tranche_observations_validate_and_record_archive_backfill_guard() -> None:
    assert STABLE_ARTIFACT_DEBT_TRANCHE_OBSERVATIONS_PATH.exists(), (
        "stable artifact debt tranche observations are missing; restore the task observation artifact"
    )

    payload = _read_json(STABLE_ARTIFACT_DEBT_TRANCHE_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    observation = _observation_by_id(payload, "historical_bootstrap_archive_backfill_guard")
    assert observation.get("status") == "automated"


def test_archived_run_backfill_observations_validate_and_record_embedded_envelope_guard() -> None:
    assert ARCHIVED_RUN_BACKFILL_OBSERVATIONS_PATH.exists(), (
        "archived-run backfill observations are missing; restore the task observation artifact"
    )

    payload = _read_json(ARCHIVED_RUN_BACKFILL_OBSERVATIONS_PATH)
    schema = load_schema(IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH)

    assert validate_with_schema(payload, schema) == []
    observation = _observation_by_id(payload, "archived_run_embedded_envelope_backfill_guard")
    boundary = _observation_by_id(payload, "archived_mechanism_assessment_backfill_boundary")
    assert observation.get("status") == "automated"
    assert boundary.get("status") == "automated"
