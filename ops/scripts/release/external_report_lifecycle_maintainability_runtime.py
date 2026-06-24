from __future__ import annotations

from pathlib import Path

from ops.scripts.release.external_report_inventory_runtime import (
    as_dict,
    as_int,
    load_json_object,
)
from ops.scripts.release.external_report_release_verification_runtime import (
    _dedupe_reason_ids,
)


def maintainability_hotspot_refactor_backlog_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return (
        "implemented"
        if not maintainability_hotspot_refactor_backlog_reason_ids(vault)
        else "partially_automated"
    )


def maintainability_hotspot_refactor_backlog_reason_ids(vault: Path) -> list[str]:
    report = load_json_object(vault / "ops/reports/function-budget-refactor-proposals.json")
    if not report:
        return ["maintainability_hotspot_report_missing"]
    summary = as_dict(report.get("summary"))
    proposal_count = as_int(summary.get("proposal_count"))
    candidate_count = as_int(summary.get("function_budget_candidate_count"))
    owner_backlog_count = as_int(summary.get("owner_backlog_count"))
    large_main_count = as_int(summary.get("large_main_without_tests_or_docs_count"))
    reasons: list[str] = []
    if report.get("artifact_kind") != "function_budget_refactor_proposals":
        reasons.append("maintainability_hotspot_report_kind_mismatch")
    if report.get("producer") != "ops.scripts.function_budget_refactor_proposals":
        reasons.append("maintainability_hotspot_report_producer_mismatch")
    if report.get("status") != "pass":
        reasons.append("maintainability_hotspot_report_not_pass")
    if candidate_count > 0:
        reasons.append("maintainability_hotspot_candidates_remain")
    if proposal_count > 0:
        reasons.append("maintainability_hotspot_proposals_not_absorbed")
    if owner_backlog_count > 0:
        reasons.append("maintainability_hotspot_owner_backlog_not_absorbed")
    if large_main_count > 0:
        reasons.append("maintainability_hotspot_large_main_remains")
    return _dedupe_reason_ids(reasons)
