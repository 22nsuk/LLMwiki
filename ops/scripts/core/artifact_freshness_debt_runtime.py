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
OPERATIONAL_ATTENTION_ISSUES = (
    TEST_TARGET_FINGERPRINT_ISSUES + SOURCE_TREE_FINGERPRINT_ISSUES + SOURCE_REVISION_ISSUES
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


def is_ops_report_source_identity_issue(issue: str, *, rel_path: str) -> bool:
    return owner_surface(rel_path) == "ops_reports" and issue.startswith(
        SOURCE_TREE_FINGERPRINT_ISSUES + SOURCE_REVISION_ISSUES
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
    if is_ops_report_source_identity_issue(issue, rel_path=rel_path):
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
