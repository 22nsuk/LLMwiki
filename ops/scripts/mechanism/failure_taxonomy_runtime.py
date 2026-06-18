from __future__ import annotations

from typing import Any

from ops.scripts.core.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_record_from_payload,
    decision_record_from_report,
)

GENERATED_EVIDENCE_SETTLE_REQUIRED = "generated_evidence_settle_required"
RETRYABLE_FAILURE_TAXONOMIES = frozenset({"executor_usage_limited"})
SETTLE_FAILURE_TAXONOMIES = frozenset({GENERATED_EVIDENCE_SETTLE_REQUIRED})
ACTIONABLE_FAILURE_TAXONOMIES = frozenset(
    {
        "discarded",
        "hold",
        "mutation_failed",
        "repo_health_blocked",
        "review_blocked",
        "scope_blocked",
        "validation_blocked",
    }
)
ACTIONABLE_PROMOTION_CHECK_FAILURE_TAXONOMIES = frozenset(
    {
        "primary_target_scope",
        "primary_target_exists",
        "report_consistency",
        "run_ledger_target_coverage",
        "mechanism_report_primary_targets",
        "changed_files_manifest_declared_targets",
        "changed_files_manifest_scope",
        "changed_files_manifest_allowed_apply_roots",
        "changed_files_manifest_nonempty",
        "changed_files_manifest_primary_targets_touched",
        "behavior_delta_presence",
        "candidate_lint_pass",
        "candidate_eval_pass",
        "eval_score_improves",
        "lint_non_regression",
        "lint_improves",
        "structural_complexity_non_regression",
        "structural_complexity_improves",
        "tests_non_regression",
        "tests_increase",
        "complexity_profile_score",
        "risk_flags",
        "equal_score_secondary_eligibility",
    }
)
GENERIC_PROMOTION_FAILURE_TAXONOMIES = frozenset({"discarded"})
LEGACY_PROMOTION_REASON_CODES = frozenset(
    {"", "legacy_promotion_report", "unknown", "none"}
)
EQUAL_SCORE_SECONDARY_AXIS_BLOCKER_CHECK_IDS = frozenset(
    {
        "lint_non_regression",
        "structural_complexity_non_regression",
        "tests_non_regression",
        "lint_improves",
        "structural_complexity_improves",
        "tests_increase",
        "complexity_profile_score",
        "risk_flags",
    }
)


def is_retryable_failure_taxonomy(failure_taxonomy: str) -> bool:
    return failure_taxonomy in RETRYABLE_FAILURE_TAXONOMIES


def is_generated_evidence_settle_required(failure_taxonomy: str) -> bool:
    return failure_taxonomy == GENERATED_EVIDENCE_SETTLE_REQUIRED


def is_settle_failure_taxonomy(failure_taxonomy: str) -> bool:
    return failure_taxonomy in SETTLE_FAILURE_TAXONOMIES


def is_budget_consuming_failure_taxonomy(failure_taxonomy: str) -> bool:
    return not (
        is_retryable_failure_taxonomy(failure_taxonomy)
        or is_settle_failure_taxonomy(failure_taxonomy)
    )


def is_actionable_repair_failure_taxonomy(failure_taxonomy: str) -> bool:
    return (
        failure_taxonomy in ACTIONABLE_FAILURE_TAXONOMIES
        or failure_taxonomy in ACTIONABLE_PROMOTION_CHECK_FAILURE_TAXONOMIES
    )


def blocking_role_for_failure_taxonomy(failure_taxonomy: str, roles: list[str]) -> str:
    if failure_taxonomy == "review_blocked":
        return "reviewer"
    if failure_taxonomy == "validation_blocked":
        for role in roles:
            if role == "validator" or role.endswith("auditor"):
                return role
        return "validator"
    if failure_taxonomy == "mutation_failed":
        for role in roles:
            if role not in {"reviewer", "validator"} and not role.endswith("auditor"):
                return role
        return ""
    if failure_taxonomy == "repo_health_blocked":
        return "repo_health"
    if failure_taxonomy == GENERATED_EVIDENCE_SETTLE_REQUIRED:
        return "repo_health"
    if failure_taxonomy == "scope_blocked":
        return "scope"
    if failure_taxonomy in {"discarded", "hold"}:
        return "promotion_gate"
    if failure_taxonomy in ACTIONABLE_PROMOTION_CHECK_FAILURE_TAXONOMIES:
        return "promotion_gate"
    return ""


def decision_record_from_failure_result(result: object) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    for source in (result.get("promotion_report"), result):
        if not isinstance(source, dict):
            continue
        try:
            return decision_record_from_report(source, require_record=False)
        except PromotionDecisionRegistryError:
            pass
        try:
            return decision_record_from_payload(source, require_record=False)
        except PromotionDecisionRegistryError:
            pass
    return None


def promotion_check_failure_taxonomy(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    report = result.get("promotion_report")
    if not isinstance(report, dict):
        report = result
    checks = report.get("checks")
    if not isinstance(checks, list):
        return ""
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("id", "")).strip()
        check_status = str(check.get("status", "")).strip().upper()
        if check_id and check_status == "FAIL":
            return check_id
    return ""


def failure_taxonomy_from_outcome(
    outcome: object,
    override: str | None = None,
) -> str:
    override_text = str(override or "").strip()
    if override_text:
        return override_text
    failure_taxonomy = str(getattr(outcome, "outcome", "")).strip()
    if failure_taxonomy not in GENERIC_PROMOTION_FAILURE_TAXONOMIES:
        return failure_taxonomy
    result = getattr(outcome, "result", None)
    decision_record = decision_record_from_failure_result(result)
    if isinstance(decision_record, dict):
        reason_code = str(decision_record.get("reason_code", "")).strip()
        if reason_code and reason_code not in LEGACY_PROMOTION_REASON_CODES:
            return reason_code
    check_failure = promotion_check_failure_taxonomy(result)
    return check_failure or failure_taxonomy


def failure_taxonomy_from_iteration(
    outcome: str,
    *,
    decision_record: dict[str, Any] | None,
    discard_evidence: dict[str, Any] | None,
    result_failure_taxonomy: str = "",
) -> str:
    outcome_text = str(outcome).strip().lower()
    if outcome_text == "promoted":
        return ""
    if result_failure_taxonomy:
        return result_failure_taxonomy
    if outcome_text not in GENERIC_PROMOTION_FAILURE_TAXONOMIES:
        return outcome_text
    blocking_check_ids: list[str] = []
    if isinstance(discard_evidence, dict):
        blocking_check_ids = [
            str(item).strip()
            for item in discard_evidence.get("blocking_check_ids", [])
            if str(item).strip()
        ]
    if isinstance(decision_record, dict):
        reason_code = str(decision_record.get("reason_code", "")).strip()
        if (
            reason_code
            and reason_code not in LEGACY_PROMOTION_REASON_CODES
            and (
                not blocking_check_ids
                or reason_code in blocking_check_ids
                or (
                    reason_code == "equal_score_secondary_eligibility"
                    and all(
                        check_id in EQUAL_SCORE_SECONDARY_AXIS_BLOCKER_CHECK_IDS
                        for check_id in blocking_check_ids
                    )
                )
            )
        ):
            return reason_code
    if blocking_check_ids:
        return blocking_check_ids[0]
    return outcome_text
