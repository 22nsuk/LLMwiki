from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from typing import Any

from .gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_BLOCKS_PROMOTION,
    GATE_EFFECT_CLAIM_BLOCKER,
    GATE_EFFECT_NONE,
    strongest_gate_effect,
)

ROOT_EPHEMERAL_PATTERNS = [
    "pytest_*.log",
    "pytest_*.xml",
    "pytest_*_output.txt",
    "pytest_*_requested*.txt",
]
TOP_DEBT_LIMIT = 10
TOP_DEBT_FILE_LIMIT = 10
DEBT_QUEUE_PATH_LIMIT = 20
SOURCE_IDENTITY_ROUTE_SAMPLE_PATH_LIMIT = 8
OWNER_SURFACE_PREFIXES = (
    ("ops/reports/", "ops_reports"),
    ("ops/operator/", "operator_reports"),
    ("runs/", "runs"),
    ("external-reports/", "external_reports"),
)
STABLE_CONTRACT_ISSUES = (
    "missing_artifact_envelope",
    "unknown_currentness",
    "missing_schema",
    "schema_validation_failed",
    "schema_unavailable",
)
MTIME_SENSITIVE_ISSUES = (
    "generated_at_older_than_file_mtime",
)
TEST_TARGET_FINGERPRINT_ISSUES = (
    "test_target_fingerprint_mismatch",
    "test_target_missing",
)
SOURCE_TREE_FINGERPRINT_ISSUES = (
    "source_tree_fingerprint_mismatch",
    "source_tree_fingerprint_unknown",
)
SOURCE_REVISION_ISSUES = (
    "source_revision_mismatch",
    "source_revision_unknown",
)
SOURCE_IDENTITY_ISSUES = SOURCE_TREE_FINGERPRINT_ISSUES + SOURCE_REVISION_ISSUES
INPUT_FINGERPRINT_ISSUES = (
    "input_fingerprint_mismatch",
    "input_fingerprint_unknown",
)
OPERATIONAL_ATTENTION_ISSUES = (
    TEST_TARGET_FINGERPRINT_ISSUES + SOURCE_IDENTITY_ISSUES + INPUT_FINGERPRINT_ISSUES
)
EXECUTION_BLOCKING_ISSUES = (
    "root_ephemeral_artifact",
    "utf8_decode_failed",
    "read_failed",
    "json_decode_failed",
    "json_root_not_object",
    "schema_validation_failed",
)
ADVISORY_ONLY_MTIME_DRIFT_PATHS = {
    "ops/reports/generated-artifact-index.json",
}
LEARNING_READINESS_SIGNOFF_REPORT = "ops/reports/learning-readiness-signoff.json"
SUPPLY_CHAIN_SOURCE_IDENTITY_KINDS = {
    "cyclonedx_sbom",
    "in_toto_statement",
    "openvex_draft",
    "sbom_export_mapping_report",
    "sbom_readiness_gate_report",
    "security_advisories_report",
    "sigstore_bundle_verification",
    "spdx_sbom",
    "supply_chain_artifact_model",
    "supply_chain_gate_report",
    "supply_chain_provenance_report",
}
RELEASE_SOURCE_PACKAGE_SOURCE_IDENTITY_KINDS = {
    "source_package_clean_extract",
}
RELEASE_FINALITY_SOURCE_IDENTITY_KINDS = {
    "artifact_freshness_report",
    "auto_improve_readiness_report",
    "external_report_action_matrix",
    "generated_artifact_index_report",
    "release_clean_blocker_ledger",
    "release_closeout_fixed_point_report",
    "release_closeout_sealed_rehearsal_check",
    "release_closeout_summary",
    "release_evidence_cohort",
    "release_evidence_dashboard",
    "release_lane_summary",
    "release_risk_taxonomy_matrix",
}
GOAL_RUNTIME_SOURCE_IDENTITY_KINDS = {
    "codex_goal_contract",
    "codex_goal_prompt",
    "goal_run_status",
    "goal_runtime_certificate",
    "goal_worktree_guard",
    "remediation_backlog",
    "self_improvement_negative_lessons",
    "session_synopsis",
}
GOAL_RUNTIME_COMPLETED_RUN_LANE = "goal-runtime-completed-run-evidence"
GOAL_RUNTIME_COMPLETED_RUN_TARGETS = (
    "GOAL_RUN_ID=<completed-run-id> make goal-runtime-publish-snapshot",
    "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
)
LEARNING_SOURCE_IDENTITY_KINDS = {
    "learning_claim_activation_report",
    "learning_claim_evidence_bundle",
    "learning_claim_unlock_review",
    "learning_confirmed_evidence_cohort",
    "learning_confirmed_legacy_reconstruction",
    "learning_delta_scoreboard",
    "learning_readiness_signoff_revalidation",
}
MAINTAINABILITY_SOURCE_IDENTITY_KINDS = {
    "function_budget_refactor_proposals",
    "strict_lint_inventory",
    "strict_type_inventory",
    "structural_complexity_budget_report",
}
MECHANISM_SOURCE_IDENTITY_TARGETS = {
    "mechanism_review_candidates_report": (
        "mechanism-review",
        ("mechanism-review",),
        "mechanism_review_candidates_source_identity",
    ),
    "mutation_proposals_report": (
        "mutation-proposal",
        ("mutation-proposal",),
        "mutation_proposals_source_identity",
    ),
    "outcome_metrics_report": (
        "outcome-metrics",
        ("outcome-metrics",),
        "outcome_metrics_source_identity",
    ),
    "outcome_provenance_gate_policy": (
        "outcome-provenance-gate-policy",
        ("outcome-provenance-gate-policy",),
        "outcome_provenance_source_identity",
    ),
    "promotion_decision_trends": (
        "promotion-decision-trends",
        ("promotion-decision-trends",),
        "promotion_decision_trends_source_identity",
    ),
}


def owner_surface(rel_path: str) -> str:
    for prefix, surface in OWNER_SURFACE_PREFIXES:
        if rel_path.startswith(prefix):
            return surface
    if any(fnmatch.fnmatch(rel_path, pattern) for pattern in ROOT_EPHEMERAL_PATTERNS):
        return "root_ephemeral"
    return "repo_root"


def is_run_local_artifact(rel_path: str) -> bool:
    return rel_path.startswith("runs/")


def is_historical_schema_drift(
    *,
    rel_path: str,
    schema_validation_status: str,
) -> bool:
    return is_run_local_artifact(rel_path) and schema_validation_status == "historical_schema_drift"


def matching_issues(issues: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(issue for issue in issues if issue.startswith(prefixes))


def mtime_drift_is_advisory_only(rel_path: str) -> bool:
    return rel_path in ADVISORY_ONLY_MTIME_DRIFT_PATHS


def is_learning_readiness_signoff_source_identity_issue(
    issues: list[str],
    *,
    rel_path: str,
) -> bool:
    if rel_path != LEARNING_READINESS_SIGNOFF_REPORT:
        return False
    return bool(matching_issues(issues, SOURCE_TREE_FINGERPRINT_ISSUES + SOURCE_REVISION_ISSUES))


def is_ops_report_claim_blocker_issue(issue: str, *, rel_path: str) -> bool:
    return owner_surface(rel_path) == "ops_reports" and issue.startswith(
        SOURCE_IDENTITY_ISSUES + INPUT_FINGERPRINT_ISSUES
    )


def recommended_next_action(
    issues: list[str],
    schema_validation_status: str,
    *,
    rel_path: str = "",
) -> str:
    if any(issue.startswith(("read_failed", "utf8_decode_failed", "json_decode_failed")) for issue in issues):
        return "repair_or_remove_unreadable_artifact"
    if schema_validation_status == "fail":
        return "regenerate_artifact_from_current_schema"
    if schema_validation_status == "historical_schema_drift":
        return "archive_or_classify_historical_run_artifact"
    if "missing_artifact_envelope" in issues:
        return "backfill_artifact_envelope"
    if "missing_schema" in issues or schema_validation_status == "schema_unavailable":
        return "add_schema_or_exclude_noncanonical_json"
    if matching_issues(issues, TEST_TARGET_FINGERPRINT_ISSUES):
        return "regenerate_test_execution_summary"
    if is_learning_readiness_signoff_source_identity_issue(issues, rel_path=rel_path):
        return "refresh_learning_readiness_signoff"
    if "source_tree_fingerprint_mismatch" in issues:
        return "regenerate_canonical_report"
    if "source_tree_fingerprint_unknown" in issues:
        return "regenerate_canonical_report_with_source_tree_fingerprint"
    if "source_revision_mismatch" in issues:
        return "regenerate_canonical_report"
    if "source_revision_unknown" in issues:
        return "regenerate_canonical_report_with_source_revision"
    if matching_issues(issues, INPUT_FINGERPRINT_ISSUES):
        return "regenerate_canonical_report"
    if "generated_at_older_than_file_mtime" in issues:
        return "regenerate_artifact_or_refresh_timestamp"
    if "missing_generated_at" in issues:
        return "backfill_generated_at_or_mark_legacy_noncanonical"
    if "unknown_currentness" in issues:
        return "backfill_currentness_metadata"
    return "none"


def contract_issue_class(
    *,
    rel_path: str,
    issues: list[str],
    stable_contract_issues: list[str],
    mtime_sensitive_issues: list[str],
    schema_validation_status: str,
) -> str:
    if any(issue.startswith(("read_failed", "utf8_decode_failed", "json_decode_failed")) for issue in issues):
        return "artifact_unreadable"
    if schema_validation_status == "fail":
        return "stable_contract_failure"
    if is_historical_schema_drift(
        rel_path=rel_path,
        schema_validation_status=schema_validation_status,
    ):
        return "stable_contract_debt"
    if stable_contract_issues:
        return "stable_contract_debt"
    if mtime_sensitive_issues:
        return "mtime_sensitive_attention"
    if issues:
        return "operational_attention"
    return "clean"


def issue_gate_effect(issue: str) -> str:
    if issue.startswith(EXECUTION_BLOCKING_ISSUES):
        return GATE_EFFECT_BLOCKS_EXECUTION
    if issue == "generated_at_older_than_file_mtime" or issue.startswith(
        OPERATIONAL_ATTENTION_ISSUES
    ):
        return GATE_EFFECT_BLOCKS_PROMOTION
    if issue:
        return GATE_EFFECT_ADVISORY
    return GATE_EFFECT_NONE


def issue_gate_effect_for_record(issue: str, *, rel_path: str) -> str:
    if issue == "schema_validation_failed" and is_run_local_artifact(rel_path):
        return GATE_EFFECT_ADVISORY
    if is_ops_report_claim_blocker_issue(issue, rel_path=rel_path):
        return GATE_EFFECT_CLAIM_BLOCKER
    return issue_gate_effect(issue)


def issues_gate_effect_for_record(issues: Sequence[str], *, rel_path: str) -> str:
    return strongest_gate_effect(
        issue_gate_effect_for_record(issue, rel_path=rel_path) for issue in issues
    )


def artifact_record_gate_effect(
    *,
    rel_path: str,
    issues: list[str],
    stable_contract_issues: list[str],
    mtime_sensitive_issues: list[str],
) -> str:
    issue_effect = issues_gate_effect_for_record(issues, rel_path=rel_path)
    if issue_effect != GATE_EFFECT_NONE:
        return issue_effect
    if stable_contract_issues or mtime_sensitive_issues:
        return GATE_EFFECT_ADVISORY
    return GATE_EFFECT_NONE


def artifact_freshness_status(
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
    missing_envelope_count: int,
    missing_schema_count: int,
    stale_count: int,
    unknown_currentness_count: int,
    schema_invalid_count: int,
    schema_unavailable_count: int,
) -> str:
    if root_ephemeral_count or non_utf8_count or schema_invalid_count:
        return "fail"
    if missing_envelope_count or missing_schema_count or stale_count or unknown_currentness_count or schema_unavailable_count:
        return "attention"
    return "pass"


def _recommended_next_action_for_issue(issue: str, *, rel_path: str = "") -> str:
    if issue == "root_ephemeral_artifact":
        return "remove_root_ephemeral_artifact"
    if issue == "schema_validation_failed" and is_run_local_artifact(rel_path):
        return "archive_or_classify_historical_run_artifact"
    schema_validation_status = "fail" if issue == "schema_validation_failed" else "pass"
    return recommended_next_action([issue], schema_validation_status, rel_path=rel_path)


def _issue_priority(issue: str) -> int:
    ordered = {
        "root_ephemeral_artifact": 0,
        "utf8_decode_failed": 1,
        "read_failed": 1,
        "json_decode_failed": 2,
        "json_root_not_object": 2,
        "schema_validation_failed": 3,
        "missing_artifact_envelope": 4,
        "missing_schema": 5,
        "schema_unavailable": 6,
        "source_tree_fingerprint_mismatch": 7,
        "source_tree_fingerprint_unknown": 7,
        "source_revision_mismatch": 7,
        "source_revision_unknown": 7,
        "generated_at_older_than_file_mtime": 7,
        "test_target_fingerprint_mismatch": 7,
        "test_target_missing": 7,
        "unknown_currentness": 8,
        "missing_generated_at": 9,
    }
    for prefix, priority in ordered.items():
        if issue.startswith(prefix):
            return priority
    return 100


def _primary_issue(issues: list[str]) -> str:
    return min(issues, key=lambda issue: (_issue_priority(issue), issue)) if issues else "none"


def top_debt(
    artifact_records: list[dict[str, Any]],
    root_ephemeral: list[dict[str, str]],
    non_utf8: list[dict[str, str]],
) -> list[dict[str, Any]]:
    by_issue: dict[str, dict[str, Any]] = {}

    def add(
        issue: str,
        surface: str,
        *,
        safe_to_backfill: bool,
        mtime_sensitive: bool,
        gate_effect: str,
        action: str,
    ) -> None:
        item = by_issue.setdefault(
            issue,
            {
                "issue": issue,
                "count": 0,
                "owner_surface_counts": {},
                "safe_to_backfill_count": 0,
                "mtime_sensitive_count": 0,
                "recommended_next_action": action,
                "gate_effect": GATE_EFFECT_NONE,
            },
        )
        item["count"] += 1
        item["owner_surface_counts"][surface] = item["owner_surface_counts"].get(surface, 0) + 1
        if safe_to_backfill:
            item["safe_to_backfill_count"] += 1
        if mtime_sensitive:
            item["mtime_sensitive_count"] += 1
        item["gate_effect"] = strongest_gate_effect([str(item["gate_effect"]), gate_effect])
        if item["recommended_next_action"] == "none" and action != "none":
            item["recommended_next_action"] = action

    for record in artifact_records:
        for issue in record["issues"]:
            rel_path = str(record["path"])
            add(
                issue,
                str(record["owner_surface"]),
                safe_to_backfill=bool(record["safe_to_backfill"]),
                mtime_sensitive=bool(record["mtime_sensitive"]),
                gate_effect=issue_gate_effect_for_record(issue, rel_path=rel_path),
                action=_recommended_next_action_for_issue(issue, rel_path=rel_path),
            )
    for item in root_ephemeral:
        add(
            "root_ephemeral_artifact",
            owner_surface(item["path"]),
            safe_to_backfill=False,
            mtime_sensitive=False,
            gate_effect=issue_gate_effect("root_ephemeral_artifact"),
            action=_recommended_next_action_for_issue("root_ephemeral_artifact"),
        )
    for item in non_utf8:
        issue = item["issue"]
        add(
            issue,
            owner_surface(item["path"]),
            safe_to_backfill=False,
            mtime_sensitive=False,
            gate_effect=issue_gate_effect(issue),
            action=_recommended_next_action_for_issue(issue),
        )

    return sorted(
        by_issue.values(),
        key=lambda item: (-item["count"], item["issue"]),
    )[:TOP_DEBT_LIMIT]


def top_debt_files(
    artifact_records: list[dict[str, Any]],
    root_ephemeral: list[dict[str, str]],
    non_utf8: list[dict[str, str]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in artifact_records:
        issues = list(record["issues"])
        if not issues:
            continue
        primary_issue = _primary_issue(issues)
        rel_path = str(record["path"])
        items.append(
            {
                "path": record["path"],
                "owner_surface": record["owner_surface"],
                "primary_issue": primary_issue,
                "issues": issues,
                "recommended_next_action": record["recommended_next_action"],
                "gate_effect": issues_gate_effect_for_record(issues, rel_path=rel_path),
                "expected_debt_reduction": len(issues),
                "safe_to_backfill": bool(record["safe_to_backfill"]),
                "mtime_sensitive": bool(record["mtime_sensitive"]),
            }
        )
    for item in root_ephemeral:
        items.append(
            {
                "path": item["path"],
                "owner_surface": owner_surface(item["path"]),
                "primary_issue": "root_ephemeral_artifact",
                "issues": ["root_ephemeral_artifact"],
                "recommended_next_action": "remove_root_ephemeral_artifact",
                "gate_effect": issue_gate_effect("root_ephemeral_artifact"),
                "expected_debt_reduction": 1,
                "safe_to_backfill": False,
                "mtime_sensitive": False,
            }
        )
    for item in non_utf8:
        items.append(
            {
                "path": item["path"],
                "owner_surface": owner_surface(item["path"]),
                "primary_issue": item["issue"],
                "issues": [item["issue"]],
                "recommended_next_action": "repair_non_utf8_artifact",
                "gate_effect": issue_gate_effect(item["issue"]),
                "expected_debt_reduction": 1,
                "safe_to_backfill": False,
                "mtime_sensitive": False,
            }
        )
    return sorted(
        items,
        key=lambda item: (
            _issue_priority(str(item["primary_issue"])),
            not bool(item["safe_to_backfill"]),
            bool(item["mtime_sensitive"]),
            -int(item["expected_debt_reduction"]),
            str(item["owner_surface"]),
            str(item["path"]),
        ),
    )[:TOP_DEBT_FILE_LIMIT]


def owner_surface_rollup(artifact_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surfaces: dict[str, dict[str, Any]] = {}
    for record in artifact_records:
        surface = record["owner_surface"]
        item = surfaces.setdefault(
            surface,
            {
                "surface": surface,
                "artifact_count": 0,
                "issue_count": 0,
                "safe_to_backfill_count": 0,
                "mtime_sensitive_count": 0,
                "recommended_next_action": "none",
            },
        )
        item["artifact_count"] += 1
        item["issue_count"] += len(record["issues"])
        if record["safe_to_backfill"]:
            item["safe_to_backfill_count"] += 1
        if record["mtime_sensitive"]:
            item["mtime_sensitive_count"] += 1
        if item["recommended_next_action"] == "none" and record["recommended_next_action"] != "none":
            item["recommended_next_action"] = record["recommended_next_action"]
    return sorted(surfaces.values(), key=lambda item: (-item["issue_count"], item["surface"]))


def _debt_queue_path(record: dict[str, Any], issues: list[str]) -> dict[str, Any]:
    return {
        "path": record["path"],
        "owner_surface": record["owner_surface"],
        "primary_issue": _primary_issue(issues),
        "issues": issues,
        "gate_effect": issues_gate_effect_for_record(issues, rel_path=str(record["path"])),
        "safe_to_backfill": bool(record["safe_to_backfill"]),
        "mtime_sensitive": bool(record["mtime_sensitive"]),
    }


def _debt_queue(
    *,
    queue_id: str,
    records: list[dict[str, Any]],
    issue_selector: str,
    exit_condition: str,
    action: str,
) -> dict[str, Any]:
    paths: list[dict[str, Any]] = []
    for record in records:
        if issue_selector == "stable":
            issues = list(record["stable_contract_issues"])
        elif issue_selector == "mtime":
            issues = list(record["mtime_sensitive_issues"])
        else:
            issues = list(record["issues"])
        if not issues:
            continue
        paths.append(_debt_queue_path(record, issues))
    paths = sorted(paths, key=lambda item: (str(item["owner_surface"]), str(item["path"])))
    issue_count = sum(len(item["issues"]) for item in paths)
    return {
        "queue": queue_id,
        "status": "open" if paths else "complete",
        "gate_effect": strongest_gate_effect(
            str(item.get("gate_effect", GATE_EFFECT_NONE)) for item in paths
        ),
        "item_count": len(paths),
        "issue_count": issue_count,
        "safe_to_backfill_count": sum(1 for item in paths if item["safe_to_backfill"]),
        "mtime_sensitive_count": sum(1 for item in paths if item["mtime_sensitive"]),
        "exit_condition": exit_condition,
        "recommended_next_action": action if paths else "none",
        "paths": paths[:DEBT_QUEUE_PATH_LIMIT],
    }


def debt_queues(artifact_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs_historical = [
        record
        for record in artifact_records
        if record["owner_surface"] == "runs" and record["stable_contract_issues"]
    ]
    ops_reports = [
        record
        for record in artifact_records
        if record["owner_surface"] == "ops_reports" and record["stable_contract_issues"]
    ]
    operator_reports = [
        record
        for record in artifact_records
        if record["owner_surface"] == "operator_reports" and record["stable_contract_issues"]
    ]
    mtime_sensitive = [
        record
        for record in artifact_records
        if record["mtime_sensitive_issues"]
    ]
    return [
        _debt_queue(
            queue_id="runs_historical_archive",
            records=runs_historical,
            issue_selector="stable",
            exit_condition=(
                "Run-local historical JSON artifacts are archived, classified as noncanonical, "
                "or gain schema-backed artifact envelope/currentness metadata."
            ),
            action="archive_or_classify_historical_run_artifacts",
        ),
        _debt_queue(
            queue_id="ops_reports_producer_refresh",
            records=ops_reports,
            issue_selector="stable",
            exit_condition=(
                "Ops report producers emit schema-backed current artifacts, or legacy reports move "
                "to an archive namespace with explicit retention metadata."
            ),
            action="refresh_ops_report_producers",
        ),
        _debt_queue(
            queue_id="operator_reports_producer_refresh",
            records=operator_reports,
            issue_selector="stable",
            exit_condition=(
                "Operator reports emit schema-backed current artifacts, or move to an archive namespace "
                "with explicit retention metadata."
            ),
            action="refresh_operator_report_producers",
        ),
        _debt_queue(
            queue_id="mtime_sensitive_regeneration",
            records=mtime_sensitive,
            issue_selector="mtime",
            exit_condition=(
                "Mtime-sensitive artifacts are regenerated so generated_at and test target fingerprints "
                "match the current source tree, or are marked archived with archive retention."
            ),
            action="regenerate_mtime_sensitive_artifacts",
        ),
    ]


def report_next_action(
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
    schema_invalid_count: int,
    missing_envelope_count: int,
    missing_schema_count: int,
    stale_count: int,
    unknown_currentness_count: int,
) -> str:
    if root_ephemeral_count:
        return "remove_root_ephemeral_artifacts"
    if non_utf8_count:
        return "repair_non_utf8_artifacts"
    if schema_invalid_count:
        return "regenerate_schema_invalid_artifacts"
    if stale_count:
        return "regenerate_stale_artifacts"
    if missing_envelope_count:
        return "backfill_artifact_envelopes"
    if missing_schema_count:
        return "add_missing_artifact_schemas"
    if unknown_currentness_count:
        return "backfill_currentness_metadata"
    return "none"


def artifact_freshness_gate_effect(
    *,
    root_ephemeral: list[dict[str, str]],
    non_utf8: list[dict[str, Any]],
    artifact_records: list[dict[str, Any]],
) -> str:
    return strongest_gate_effect(
        [
            *(
                issue_gate_effect("root_ephemeral_artifact")
                for _item in root_ephemeral
            ),
            *(issue_gate_effect(str(item.get("issue", ""))) for item in non_utf8),
            *(str(record.get("gate_effect", GATE_EFFECT_NONE)) for record in artifact_records),
        ]
    )


def _record_source_identity_issues(record: dict[str, Any]) -> list[str]:
    return matching_issues(
        [str(issue) for issue in record.get("issues", [])],
        SOURCE_IDENTITY_ISSUES,
    )


def _record_test_target_issues(record: dict[str, Any]) -> list[str]:
    return matching_issues(
        [str(issue) for issue in record.get("issues", [])],
        TEST_TARGET_FINGERPRINT_ISSUES,
    )


def _is_source_identity_only_record(record: dict[str, Any]) -> bool:
    issues = [str(issue) for issue in record.get("issues", [])]
    if not issues:
        return False
    if str(record.get("schema_validation_status", "")) != "pass":
        return False
    if record.get("stable_contract_issues") or record.get("mtime_sensitive_issues"):
        return False
    return all(issue.startswith(SOURCE_IDENTITY_ISSUES) for issue in issues)


def _source_identity_test_summary_lane(rel_path: str) -> tuple[str, tuple[str, ...], str]:
    if rel_path.endswith("/test-execution-summary-full.json"):
        return (
            "test-execution-summary-full-current-or-refresh",
            ("test-execution-summary-full-current-or-refresh",),
            "full_suite_test_summary_source_identity",
        )
    if rel_path.endswith("/test-execution-summary-public.json"):
        return (
            "public-check-summary-current-or-refresh",
            ("public-check-summary-current-or-refresh",),
            "public_test_summary_source_identity",
        )
    return (
        "test-execution-summary-current-or-refresh",
        ("test-execution-summary-current-or-refresh",),
        "report_contract_test_summary_source_identity",
    )


def _source_identity_release_smoke_lane(rel_path: str) -> tuple[str, tuple[str, ...], str]:
    if rel_path.endswith("/release-smoke-report-fast.json"):
        return (
            "release-smoke-fast-refresh-check",
            ("release-smoke-fast-refresh-check",),
            "release_smoke_fast_source_identity",
        )
    return (
        "release-smoke-full-reuse",
        ("release-smoke-full-reuse",),
        "release_smoke_full_source_identity",
    )


def _source_identity_route_descriptor(record: dict[str, Any]) -> dict[str, Any]:
    rel_path = str(record.get("path", ""))
    surface = str(record.get("owner_surface") or owner_surface(rel_path))
    artifact_kind = str(record.get("artifact_kind", ""))
    next_action = str(record.get("recommended_next_action", ""))
    route_id: str
    lane: str
    targets: tuple[str, ...]
    reason_id: str

    if surface == "external_reports":
        route_id = "external_reports_reference_manifest"
        lane = "external-report-reference-manifest-settle"
        targets = (
            "external-report-reference-manifest-settle",
            "external-report-lifecycle-refresh",
        )
        reason_id = "external_report_reference_manifest_source_identity"
    elif artifact_kind == "test_execution_summary":
        lane, targets, reason_id = _source_identity_test_summary_lane(rel_path)
        route_id = f"ops_reports_{lane.replace('-', '_')}"
    elif artifact_kind == "public_check_summary":
        route_id = "ops_reports_public_check_summary"
        lane = "public-check-summary-current-or-refresh"
        targets = ("public-check-summary-current-or-refresh",)
        reason_id = "public_check_summary_source_identity"
    elif (
        rel_path == LEARNING_READINESS_SIGNOFF_REPORT
        or next_action == "refresh_learning_readiness_signoff"
    ):
        route_id = "ops_reports_learning_readiness_signoff"
        lane = "learning-readiness-signoff-refresh"
        targets = ("learning-readiness-signoff-refresh", "learning-readiness-signoff-revalidation")
        reason_id = "learning_readiness_signoff_source_identity"
    elif artifact_kind in LEARNING_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_learning_evidence"
        lane = "learning-claim-activation-report"
        targets = (
            "learning-claim-activation-report",
            "learning-readiness-signoff-revalidation",
        )
        reason_id = "learning_evidence_source_identity"
    elif artifact_kind in GOAL_RUNTIME_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_goal_runtime"
        lane = GOAL_RUNTIME_COMPLETED_RUN_LANE
        targets = GOAL_RUNTIME_COMPLETED_RUN_TARGETS
        reason_id = "goal_runtime_completed_run_evidence_required"
    elif artifact_kind in SUPPLY_CHAIN_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_supply_chain"
        lane = "supply-chain-artifacts-cached"
        targets = ("supply-chain-artifacts-cached",)
        reason_id = "supply_chain_source_identity"
    elif artifact_kind == "release_smoke_report":
        lane, targets, reason_id = _source_identity_release_smoke_lane(rel_path)
        route_id = f"ops_reports_{lane.replace('-', '_')}"
    elif artifact_kind in RELEASE_SOURCE_PACKAGE_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_release_source_package"
        lane = "release-source-package-check"
        targets = ("release-source-package-check",)
        reason_id = "release_source_package_source_identity"
    elif artifact_kind in MAINTAINABILITY_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_maintainability"
        lane = "function-budget-refactor-proposals"
        targets = (
            "function-budget-refactor-proposals",
            "lint-uplift-plan",
            "type-uplift-plan",
            "complexity-budget",
        )
        reason_id = "maintainability_evidence_source_identity"
    elif artifact_kind in MECHANISM_SOURCE_IDENTITY_TARGETS:
        lane, targets, reason_id = MECHANISM_SOURCE_IDENTITY_TARGETS[artifact_kind]
        route_id = f"ops_reports_{lane.replace('-', '_')}"
    elif artifact_kind in RELEASE_FINALITY_SOURCE_IDENTITY_KINDS:
        route_id = "ops_reports_release_finality"
        lane = "release-finality-resettle-current-or-refresh"
        targets = ("release-finality-resettle-current-or-refresh",)
        reason_id = "release_finality_source_identity"
    elif artifact_kind.startswith("raw_registry_"):
        route_id = "ops_reports_registry_preflight"
        lane = "registry-preflight"
        targets = ("registry-preflight",)
        reason_id = "registry_preflight_source_identity"
    elif artifact_kind == "github_governance_live_drift_verification":
        route_id = "ops_reports_github_governance"
        lane = "github-governance-live-drift"
        targets = ("github-governance-live-drift",)
        reason_id = "github_governance_source_identity"
    elif artifact_kind == "bootstrap_preflight_report":
        route_id = "ops_reports_bootstrap_preflight"
        lane = "bootstrap-preflight"
        targets = ("bootstrap-preflight",)
        reason_id = "bootstrap_preflight_source_identity"
    else:
        route_id = f"{surface}_source_identity_resettle"
        lane = "freshness-source-identity-converge"
        targets = ("freshness-source-identity-converge",)
        reason_id = "source_identity_resettle_fallback"

    return {
        "route_id": route_id,
        "owner_surface": surface,
        "recommended_lane": lane,
        "recommended_targets": list(targets),
        "reason_id": reason_id,
    }


def _source_identity_route_summary(route: dict[str, Any]) -> str:
    artifact_count = route["artifact_count"]
    owner_surface_value = route["owner_surface"]
    recommended_lane = route["recommended_lane"]
    reason_ids = set(route["reason_ids"])
    if "goal_runtime_completed_run_evidence_required" in reason_ids:
        return (
            f"{artifact_count} {owner_surface_value} source-identity artifact(s) require "
            "completed goal-run evidence; set GOAL_RUN_ID=<completed-run-id> before "
            "publishing or certifying canonical goal runtime evidence."
        )
    if "release_finality_source_identity" in reason_ids:
        return (
            f"{artifact_count} {owner_surface_value} source-identity artifact(s) require "
            "release finality readback/resettle; start with "
            f"{recommended_lane}."
        )
    return (
        f"{artifact_count} {owner_surface_value} source-identity artifact(s) route to "
        f"{recommended_lane}."
    )


def _source_identity_owner_routes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routes: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        descriptor = _source_identity_route_descriptor(record)
        key = (str(descriptor["owner_surface"]), str(descriptor["route_id"]))
        route = routes.setdefault(
            key,
            {
                "route_id": descriptor["route_id"],
                "owner_surface": descriptor["owner_surface"],
                "artifact_count": 0,
                "issue_count": 0,
                "artifact_kinds": set(),
                "recommended_lane": descriptor["recommended_lane"],
                "recommended_targets": descriptor["recommended_targets"],
                "reason_ids": set(),
                "sample_paths": [],
            },
        )
        route["artifact_count"] += 1
        route["issue_count"] += len(_record_source_identity_issues(record))
        artifact_kind = str(record.get("artifact_kind", ""))
        if artifact_kind:
            route["artifact_kinds"].add(artifact_kind)
        route["reason_ids"].add(descriptor["reason_id"])
        sample_paths = route["sample_paths"]
        if len(sample_paths) < SOURCE_IDENTITY_ROUTE_SAMPLE_PATH_LIMIT:
            sample_paths.append(str(record.get("path", "")))

    result: list[dict[str, Any]] = []
    for route in routes.values():
        artifact_kinds = sorted(route["artifact_kinds"])
        reason_ids = sorted(route["reason_ids"])
        result.append(
            {
                "route_id": route["route_id"],
                "owner_surface": route["owner_surface"],
                "artifact_count": route["artifact_count"],
                "issue_count": route["issue_count"],
                "artifact_kinds": artifact_kinds,
                "recommended_lane": route["recommended_lane"],
                "recommended_targets": route["recommended_targets"],
                "reason_ids": reason_ids,
                "sample_paths": sorted(route["sample_paths"]),
                "summary": _source_identity_route_summary(route),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            str(item["owner_surface"]),
            str(item["recommended_lane"]),
            str(item["route_id"]),
        ),
    )


def _artifact_problem_records(artifact_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in artifact_records
        if record.get("issues")
        or record.get("stable_contract_issues")
        or record.get("mtime_sensitive_issues")
        or str(record.get("schema_validation_status", "")) in {"fail", "schema_unavailable", "historical_schema_drift"}
    ]


def _schema_or_contract_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("stable_contract_issues")
        or str(record.get("schema_validation_status", "")) in {"fail", "schema_unavailable", "historical_schema_drift"}
    ]


def _mtime_or_test_target_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("mtime_sensitive_issues") or _record_test_target_issues(record)
    ]


def _execution_blocking_artifact_count(
    records: list[dict[str, Any]],
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
) -> int:
    return root_ephemeral_count + non_utf8_count + sum(
        1
        for record in records
        if str(record.get("gate_effect", "")) == GATE_EFFECT_BLOCKS_EXECUTION
    )


def _other_operational_attention_count(
    problem_records: list[dict[str, Any]],
    *categorized_groups: list[dict[str, Any]],
) -> int:
    categorized_record_ids = {
        id(record) for records in categorized_groups for record in records
    }
    categorized_record_ids.update(
        id(record)
        for record in problem_records
        if str(record.get("gate_effect", "")) == GATE_EFFECT_BLOCKS_EXECUTION
    )
    return sum(1 for record in problem_records if id(record) not in categorized_record_ids)


def _stale_routing_decision(
    *,
    problem_count: int,
    source_identity_count: int,
    schema_or_contract_count: int,
    mtime_or_test_target_count: int,
    execution_blocking_count: int,
    source_identity_owner_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    source_identity_only = (
        problem_count > 0
        and source_identity_count == problem_count
        and execution_blocking_count == 0
    )
    if problem_count == 0 and execution_blocking_count == 0:
        return {
            "classification": "clean",
            "recommended_lane": "none",
            "recommended_targets": [],
            "reason_ids": ["artifact_freshness_clean"],
            "summary": "No artifact freshness debt needs routing.",
        }
    if source_identity_only:
        goal_runtime_only = source_identity_owner_routes and all(
            str(route.get("recommended_lane", "")) == GOAL_RUNTIME_COMPLETED_RUN_LANE
            for route in source_identity_owner_routes
        )
        if goal_runtime_only:
            return {
                "classification": "source_identity_only",
                "recommended_lane": GOAL_RUNTIME_COMPLETED_RUN_LANE,
                "recommended_targets": list(GOAL_RUNTIME_COMPLETED_RUN_TARGETS),
                "reason_ids": [
                    "source_identity_only_stale",
                    "goal_runtime_completed_run_evidence_required",
                ],
                "summary": (
                    f"{source_identity_count} stale goal runtime artifact(s) require "
                    "completed run evidence. Set GOAL_RUN_ID=<completed-run-id> and "
                    "publish/certify that run instead of using a generic freshness refresh."
                ),
            }
        return {
            "classification": "source_identity_only",
            "recommended_lane": "freshness-source-identity-converge",
            "recommended_targets": ["freshness-source-identity-converge"],
            "reason_ids": ["source_identity_only_stale"],
            "summary": (
                f"{source_identity_count} stale artifact(s) only differ by source "
                "revision or source-tree fingerprint. Use the source-identity convergence "
                "lane before broad release convergence; use owner routes for artifacts that "
                "need explicit release finality or completed goal-run evidence."
            ),
        }
    if execution_blocking_count:
        return {
            "classification": "execution_blocking_debt",
            "recommended_lane": "artifact-freshness-refresh-check",
            "recommended_targets": ["artifact-freshness-refresh-check"],
            "reason_ids": ["execution_blocking_artifact_debt"],
            "summary": (
                f"{execution_blocking_count} execution-blocking artifact freshness "
                "issue(s) need direct repair before release evidence routing."
            ),
        }
    if schema_or_contract_count:
        return {
            "classification": "schema_or_contract_debt",
            "recommended_lane": "release-evidence-converge",
            "recommended_targets": [
                "release-evidence-converge",
                "artifact-freshness-refresh-check",
            ],
            "reason_ids": ["schema_or_contract_artifact_debt"],
            "summary": (
                f"{schema_or_contract_count} artifact(s) have schema or contract debt; "
                "use the broader evidence convergence lane after fixing the producer or schema."
            ),
        }
    if mtime_or_test_target_count:
        return {
            "classification": "mtime_or_test_target_debt",
            "recommended_lane": "release-evidence-converge",
            "recommended_targets": [
                "release-evidence-converge",
                "artifact-freshness-refresh-check",
            ],
            "reason_ids": ["mtime_or_test_target_artifact_debt"],
            "summary": (
                f"{mtime_or_test_target_count} artifact(s) have mtime or test target "
                "freshness debt; regenerate the owning evidence before final release checks."
            ),
        }
    return {
        "classification": "mixed",
        "recommended_lane": "release-evidence-converge",
        "recommended_targets": [
            "release-evidence-converge",
            "artifact-freshness-refresh-check",
        ],
        "reason_ids": ["mixed_artifact_freshness_debt"],
        "summary": (
            f"{problem_count} artifact freshness issue(s) need owner-specific repair "
            "before broad release evidence can be trusted."
        ),
    }


def stale_routing(
    artifact_records: list[dict[str, Any]],
    *,
    root_ephemeral_count: int,
    non_utf8_count: int,
) -> dict[str, Any]:
    problem_records = _artifact_problem_records(artifact_records)
    source_identity_records = [
        record for record in problem_records if _is_source_identity_only_record(record)
    ]
    source_identity_issue_count = sum(
        len(_record_source_identity_issues(record)) for record in source_identity_records
    )
    source_identity_owner_routes = _source_identity_owner_routes(source_identity_records)
    schema_or_contract_records = _schema_or_contract_records(problem_records)
    mtime_or_test_target_records = _mtime_or_test_target_records(problem_records)
    execution_blocking_artifact_count = _execution_blocking_artifact_count(
        problem_records,
        root_ephemeral_count=root_ephemeral_count,
        non_utf8_count=non_utf8_count,
    )
    other_operational_attention_artifact_count = _other_operational_attention_count(
        problem_records,
        source_identity_records,
        schema_or_contract_records,
        mtime_or_test_target_records,
    )
    decision = _stale_routing_decision(
        problem_count=len(problem_records),
        source_identity_count=len(source_identity_records),
        schema_or_contract_count=len(schema_or_contract_records),
        mtime_or_test_target_count=len(mtime_or_test_target_records),
        execution_blocking_count=execution_blocking_artifact_count,
        source_identity_owner_routes=source_identity_owner_routes,
    )

    return {
        "classification": decision["classification"],
        "recommended_lane": decision["recommended_lane"],
        "recommended_targets": decision["recommended_targets"],
        "post_commit_lane": "release-post-commit-finalize",
        "reason_ids": decision["reason_ids"],
        "problem_artifact_count": len(problem_records) + root_ephemeral_count + non_utf8_count,
        "source_identity_only_artifact_count": len(source_identity_records),
        "source_identity_only_issue_count": source_identity_issue_count,
        "source_identity_owner_routes": source_identity_owner_routes,
        "schema_or_contract_debt_artifact_count": len(schema_or_contract_records),
        "mtime_or_test_target_debt_artifact_count": len(mtime_or_test_target_records),
        "execution_blocking_artifact_count": execution_blocking_artifact_count,
        "other_operational_attention_artifact_count": other_operational_attention_artifact_count,
        "summary": decision["summary"],
    }
