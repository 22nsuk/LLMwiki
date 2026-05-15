from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from .learning_claim_evidence_bundle import (
    DEFAULT_OUT as DEFAULT_EVIDENCE_BUNDLE_PATH,
    validate_learning_claim_evidence_bundle,
)
from .learning_confirmed_evidence_cohort import (
    DEFAULT_OUT as DEFAULT_CONFIRMED_EVIDENCE_COHORT_PATH,
    validate_learning_confirmed_evidence_cohort,
)
from .learning_claim_model import (
    learning_claim_blocker_status,
    normalize_evidence_cohort_summary,
)
from .learning_readiness_vocabulary import learning_release_blocker_ids_from_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "ops/reports/learning-claim-unlock-review.json"
DEFAULT_AUTO_POLICY_PATH = "ops/policies/learning-claim-auto-unlock.json"
DEFAULT_CONFIRMED_POLICY_PATH = "ops/policies/learning-claim-confirmed-improvement.json"
PRODUCER = "ops.scripts.learning_claim_unlock_review"
SCHEMA_PATH = "ops/schemas/learning-claim-unlock-review.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_claim_unlock_review --vault ."


@dataclass(frozen=True)
class AutoPolicyThresholds:
    min_same_eval_runs: int
    min_coverage: float
    max_rework_count: int
    max_defect_escape_pair_count: int
    min_runnable_proposal_count: int


@dataclass(frozen=True)
class UnlockReviewDecision:
    approved_by: str
    reviewed_at: str
    operator_review_present: bool
    operator_approved: bool
    machine_approved: bool
    approved: bool
    review_status: str
    approval_mode: str
    reviewed_surface_status: str
    readiness_status: str
    operator_review_value: str
    readiness_observed_value: str
    decision_reason: str


def _empty_confirmed_evidence_summary(status: str = "not_ready") -> dict[str, Any]:
    return {
        "evidence_cohort_status": status,
        "confirmed_evidence_status": status,
        "valid_run_count": 0,
        "min_required_run_count": 0,
        "eligible_family_count": 0,
        "selected_valid_run_ids": [],
        "blocking_predicate_ids": [],
        "rejected_run_count": 0,
        "rejected_run_diagnostics": [],
        "legacy_reconstruction_summary": {
            "status": "not_used",
            "reconstruction_needed_count": 0,
            "reconstructed_run_count": 0,
            "blocked_run_count": 0,
            "run_diagnostics": [],
        },
    }


def _learning_signal_ids(readiness: dict[str, Any]) -> list[str]:
    signals = readiness.get("learning_readiness", {}).get("signals", [])
    if not isinstance(signals, list):
        return []
    return [
        str(signal.get("id", "")).strip()
        for signal in signals
        if isinstance(signal, dict) and str(signal.get("id", "")).strip()
    ]


def _learning_blocker_ids(readiness: dict[str, Any]) -> list[str]:
    return learning_release_blocker_ids_from_report(readiness)


def _bool_at(payload: dict[str, Any], path: tuple[str, ...]) -> bool:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return False
        value = value.get(key)
    return bool(value)


def _string_at(payload: dict[str, Any], path: tuple[str, ...]) -> str:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "").strip()


def _float_at(payload: dict[str, Any], path: tuple[str, ...]) -> float:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return 0.0
        value = value.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_at(payload: dict[str, Any], path: tuple[str, ...]) -> int:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return 0
        value = value.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(policy.get(key, default))
    except (TypeError, ValueError):
        return default


def _policy_float(policy: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(policy.get(key, default))
    except (TypeError, ValueError):
        return default


def _auto_policy_thresholds(policy: dict[str, Any]) -> AutoPolicyThresholds:
    return AutoPolicyThresholds(
        min_same_eval_runs=_policy_int(policy, "min_same_eval_run_count", 1),
        min_coverage=_policy_float(policy, "min_coverage_ratio", 1.0),
        max_rework_count=_policy_int(policy, "max_rework_count", 0),
        max_defect_escape_pair_count=_policy_int(policy, "max_defect_escape_pair_count", 0),
        min_runnable_proposal_count=_policy_int(policy, "min_runnable_proposal_count", 1),
    )


def _predicate_result(
    predicate_id: str,
    status: str,
    source_path: str,
    required_condition: str,
    observed_value: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "id": predicate_id,
        "status": status,
        "source_path": source_path,
        "required_condition": required_condition,
        "observed_value": observed_value,
        "summary": summary,
    }


def _disabled_machine_policy_decision(
    vault: Path,
    *,
    auto_policy_path: str,
    policy_version: int | str | None = None,
    evidence_bundle_path: str = DEFAULT_EVIDENCE_BUNDLE_PATH,
    confirmed_policy_path: str = "",
) -> dict[str, Any]:
    return {
        "enabled": False,
        "policy_path": report_path(vault, vault / auto_policy_path) if auto_policy_path else "",
        "policy_version": policy_version,
        "decision": "disabled",
        "evidence_bundle_digest": "",
        "bundle_path": evidence_bundle_path,
        "bundle_sha256": "",
        "current_bundle_sha256": "",
        "bundle_status": "not_evaluated",
        "bundle_fingerprint_match_status": "not_evaluated",
        "revocation_status": "not_evaluated",
        "claim_level": "none",
        "claim_scope": "",
        "bounded_learning_claim_allowed": False,
        "confirmed_learning_improvement_allowed": False,
        "confirmed_learning_improvement_status": "not_ready",
        "confirmed_policy_path": confirmed_policy_path,
        "confirmed_policy_version": None,
        "confirmed_evidence_cohort_path": DEFAULT_CONFIRMED_EVIDENCE_COHORT_PATH,
        "confirmed_evidence_cohort_sha256": "",
        "current_confirmed_evidence_cohort_sha256": "",
        "confirmed_evidence_cohort_status": "not_evaluated",
        "confirmed_evidence_cohort_fingerprint_match_status": "not_evaluated",
        "improvement_claim_status": "not_ready",
        "evidence_cohort_status": "not_ready",
        "learning_claim_blocker_status": "not_evaluated",
        "claim_wording_allowed": False,
        "claim_wording_policy_status": "blocked",
        "confirmed_evidence_summary": _empty_confirmed_evidence_summary(),
        "confirmed_predicate_results": [],
        "predicate_results": [],
    }


def _simple_report_status(vault: Path, rel_path: str) -> str:
    payload = load_optional_json_object(vault / rel_path)
    return str(payload.get("status", "")).strip() if payload else "missing"


def _learning_claim_blocker_count(vault: Path, rel_path: str) -> int:
    payload = load_optional_json_object(vault / rel_path)
    blockers = payload.get("learning_claim_blockers")
    if isinstance(blockers, list):
        return len(blockers)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        try:
            return int(summary.get("learning_claim_blocking_family_count", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _confirmed_policy_evidence_paths(policy: dict[str, Any]) -> dict[str, str]:
    required_paths = policy.get("required_evidence_paths")
    path_map: dict[str, Any] = required_paths if isinstance(required_paths, dict) else {}
    return {
        "confirmed_evidence_cohort": str(
            path_map.get("confirmed_evidence_cohort", DEFAULT_CONFIRMED_EVIDENCE_COHORT_PATH)
        ),
        "full_suite_summary": str(
            path_map.get("full_suite_summary", "ops/reports/test-execution-summary-full.json")
        ),
        "public_check_summary": str(
            path_map.get("public_check_summary", "ops/reports/public-check-summary.json")
        ),
        "rollback_revalidation": str(
            path_map.get(
                "rollback_revalidation",
                "ops/reports/learning-readiness-signoff-revalidation.json",
            )
        ),
        "release_clean_blocker_ledger": str(
            path_map.get("release_clean_blocker_ledger", "ops/reports/release-clean-blocker-ledger.json")
        ),
    }


def _confirmed_policy_predicate_results(
    vault: Path,
    *,
    bundle_validation: dict[str, Any],
    cohort_predicates: list[dict[str, Any]],
    evidence_paths: dict[str, str],
    ledger_blocker_count: int,
) -> list[dict[str, Any]]:
    full_suite_path = evidence_paths["full_suite_summary"]
    public_check_path = evidence_paths["public_check_summary"]
    rollback_path = evidence_paths["rollback_revalidation"]
    ledger_path = evidence_paths["release_clean_blocker_ledger"]
    return [
        _predicate_result(
            "evidence_bundle_active",
            "pass" if bundle_validation.get("revocation_status") == "active" else "fail",
            str(bundle_validation.get("bundle_path", DEFAULT_EVIDENCE_BUNDLE_PATH)),
            "learning_claim_evidence_bundle.revocation_status == active",
            f"revocation_status={bundle_validation.get('revocation_status')}",
            "Confirmed claims require a non-stale, non-revoked evidence bundle.",
        ),
        *cohort_predicates,
        _predicate_result(
            "full_suite_pass",
            "pass" if _simple_report_status(vault, full_suite_path) == "pass" else "fail",
            full_suite_path,
            "test_execution_summary_full.status == pass",
            f"status={_simple_report_status(vault, full_suite_path)}",
            "Full test suite must pass before confirmed improvement opens.",
        ),
        _predicate_result(
            "public_check_pass",
            "pass" if _simple_report_status(vault, public_check_path) == "pass" else "fail",
            public_check_path,
            "public_check_summary.status == pass",
            f"status={_simple_report_status(vault, public_check_path)}",
            "Public mirror check must pass before confirmed improvement opens.",
        ),
        _predicate_result(
            "rollback_revalidation_clean",
            "pass" if _simple_report_status(vault, rollback_path) == "pass" else "fail",
            rollback_path,
            "learning_readiness_signoff_revalidation.status == pass",
            f"status={_simple_report_status(vault, rollback_path)}",
            "Rollback/revalidation evidence must be clean.",
        ),
        _predicate_result(
            "learning_claim_blocker_absence",
            "pass" if ledger_blocker_count == 0 else "fail",
            ledger_path,
            "release_clean_blocker_ledger.learning_claim_blockers == []",
            f"learning_claim_blocker_count={ledger_blocker_count}",
            "No accepted learning risk or learning-claim blocker may remain.",
        ),
    ]


def _confirmed_policy_status(
    *,
    bundle_validation: dict[str, Any],
    cohort_validation: dict[str, Any],
    predicates: list[dict[str, Any]],
) -> str:
    if bundle_validation.get("revocation_status") == "revoked" or cohort_validation.get("revocation_status") == "revoked":
        return "revoked"
    if all(item["status"] == "pass" for item in predicates):
        return "auto_confirmed"
    return "not_ready"


def _failed_predicate_ids(predicates: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("id", "")).strip()
        for item in predicates
        if str(item.get("id", "")).strip()
        and str(item.get("status", "")).strip() != "pass"
    ]


def _confirmed_claim_wording_allowed(
    *,
    status: str,
    evidence_cohort_status: str,
    bundle_validation: dict[str, Any],
) -> bool:
    return (
        status == "auto_confirmed"
        and evidence_cohort_status == "auto_confirmed"
        and bundle_validation.get("revocation_status") == "active"
    )


def _confirmed_policy_decision(
    vault: Path,
    *,
    confirmed_policy_path: str,
    bundle_validation: dict[str, Any],
) -> dict[str, Any]:
    resolved_policy = vault / confirmed_policy_path if confirmed_policy_path else Path()
    policy = load_optional_json_object(resolved_policy) if confirmed_policy_path else {}
    if not confirmed_policy_path or not policy or not bool(policy.get("enabled")):
        return {
            "confirmed_policy_path": report_path(vault, resolved_policy) if confirmed_policy_path else "",
            "confirmed_policy_version": policy.get("version") if policy else None,
            "confirmed_learning_improvement_status": "not_ready",
            "confirmed_learning_improvement_allowed": False,
            "confirmed_evidence_cohort_path": DEFAULT_CONFIRMED_EVIDENCE_COHORT_PATH,
            "confirmed_evidence_cohort_sha256": "",
            "current_confirmed_evidence_cohort_sha256": "",
            "confirmed_evidence_cohort_status": "not_evaluated",
            "confirmed_evidence_cohort_fingerprint_match_status": "not_evaluated",
            "improvement_claim_status": "not_ready",
            "evidence_cohort_status": "not_ready",
            "learning_claim_blocker_status": "not_evaluated",
            "claim_wording_allowed": False,
            "claim_wording_policy_status": "blocked",
            "confirmed_evidence_summary": _empty_confirmed_evidence_summary(),
            "confirmed_predicate_results": [],
        }

    evidence_paths = _confirmed_policy_evidence_paths(policy)
    cohort_path = evidence_paths["confirmed_evidence_cohort"]
    cohort_validation = validate_learning_confirmed_evidence_cohort(
        vault,
        cohort_path=cohort_path,
        evidence_bundle_path=str(bundle_validation.get("bundle_path", DEFAULT_EVIDENCE_BUNDLE_PATH)),
        confirmed_policy_path=confirmed_policy_path,
    )
    ledger_blocker_count = _learning_claim_blocker_count(vault, evidence_paths["release_clean_blocker_ledger"])
    cohort_predicates = [
        item
        for item in cohort_validation.get("predicate_results", [])
        if isinstance(item, dict)
    ]
    predicates = _confirmed_policy_predicate_results(
        vault,
        bundle_validation=bundle_validation,
        cohort_predicates=cohort_predicates,
        evidence_paths=evidence_paths,
        ledger_blocker_count=ledger_blocker_count,
    )
    status = _confirmed_policy_status(
        bundle_validation=bundle_validation,
        cohort_validation=cohort_validation,
        predicates=predicates,
    )
    failed_predicate_ids = _failed_predicate_ids(predicates)
    confirmed_evidence_summary = normalize_evidence_cohort_summary(
        cohort_validation.get(
            "confirmed_evidence_summary",
            _empty_confirmed_evidence_summary(
                str(cohort_validation.get("confirmed_evidence_status", "not_ready"))
            ),
        ),
        blocking_predicate_ids=failed_predicate_ids,
    )
    evidence_cohort_status = str(
        confirmed_evidence_summary.get("evidence_cohort_status", "not_ready")
    )
    claim_wording_allowed = _confirmed_claim_wording_allowed(
        status=status,
        evidence_cohort_status=evidence_cohort_status,
        bundle_validation=bundle_validation,
    )
    return {
        "confirmed_policy_path": report_path(vault, resolved_policy),
        "confirmed_policy_version": policy.get("version"),
        "improvement_claim_status": status,
        "confirmed_learning_improvement_status": status,
        "confirmed_learning_improvement_allowed": status == "auto_confirmed",
        "evidence_cohort_status": evidence_cohort_status,
        "learning_claim_blocker_status": learning_claim_blocker_status(failed_predicate_ids),
        "claim_wording_allowed": claim_wording_allowed,
        "claim_wording_policy_status": "pre_seal_ready"
        if claim_wording_allowed
        else "blocked",
        "confirmed_evidence_cohort_path": cohort_path,
        "confirmed_evidence_cohort_sha256": str(cohort_validation.get("cohort_sha256", "")),
        "current_confirmed_evidence_cohort_sha256": str(cohort_validation.get("current_cohort_sha256", "")),
        "confirmed_evidence_cohort_status": str(cohort_validation.get("cohort_status", "missing")),
        "confirmed_evidence_cohort_fingerprint_match_status": str(
            cohort_validation.get("cohort_fingerprint_match_status", "missing")
        ),
        "confirmed_evidence_summary": confirmed_evidence_summary,
        "confirmed_predicate_results": predicates,
    }


def _auto_policy_readiness_predicates(
    *,
    readiness: dict[str, Any],
    bundle_validation: dict[str, Any],
    evidence_bundle_path: str,
    blocking_signal_ids: list[str],
    blocking_blocker_ids: list[str],
    thresholds: AutoPolicyThresholds,
) -> list[dict[str, Any]]:
    return [
        _predicate_result(
            "learning_claim_evidence_bundle_active",
            "pass" if bundle_validation["revocation_status"] == "active" else "fail",
            evidence_bundle_path,
            "learning_claim_evidence_bundle.revocation_status == active",
            (
                f"bundle_status={bundle_validation['bundle_status']}; "
                f"fingerprint_match={bundle_validation['bundle_fingerprint_match_status']}; "
                f"revocation_status={bundle_validation['revocation_status']}"
            ),
            "Automatic approval is valid only for the current evidence bundle digest.",
        ),
        _predicate_result(
            "auto_improve_can_execute_trial",
            "pass" if _bool_at(readiness, ("can_execute_trial",)) else "fail",
            "ops/reports/auto-improve-readiness.json",
            "auto_improve_readiness.can_execute_trial == true",
            f"can_execute_trial={_bool_at(readiness, ('can_execute_trial',))}",
            "Auto-improve execution trial is runnable.",
        ),
        _predicate_result(
            "auto_improve_can_promote_result",
            "pass" if _bool_at(readiness, ("can_promote_result",)) else "fail",
            "ops/reports/auto-improve-readiness.json",
            "auto_improve_readiness.can_promote_result == true",
            f"can_promote_result={_bool_at(readiness, ('can_promote_result',))}",
            "Auto-improve result promotion gate is clean.",
        ),
        _predicate_result(
            "learning_readiness_likely",
            "pass"
            if _string_at(readiness, ("learning_readiness", "status")) == "learning_likely"
            and _bool_at(readiness, ("learning_readiness", "likely_to_learn"))
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            "learning_readiness.status == learning_likely and likely_to_learn == true",
            (
                f"status={_string_at(readiness, ('learning_readiness', 'status'))}; "
                f"likely_to_learn={_bool_at(readiness, ('learning_readiness', 'likely_to_learn'))}"
            ),
            "Learning readiness is in the narrow machine-claimable state.",
        ),
        _predicate_result(
            "learning_readiness_no_blockers",
            "pass" if not blocking_signal_ids and not blocking_blocker_ids else "fail",
            "ops/reports/auto-improve-readiness.json",
            "learning_readiness.signals == [] and release_blockers == []",
            (
                "learning_readiness.signals="
                + (",".join(blocking_signal_ids) or "[]")
                + "; release_blockers="
                + (",".join(blocking_blocker_ids) or "[]")
            ),
            "Learning readiness exposes no blocking learning claim signals.",
        ),
        _predicate_result(
            "runnable_proposal_queue_present",
            "pass"
            if _bool_at(readiness, ("queue", "ready"))
            and _int_at(readiness, ("queue", "runnable_proposal_count"))
            >= thresholds.min_runnable_proposal_count
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            (
                "queue.ready == true and runnable_proposal_count >= "
                f"{thresholds.min_runnable_proposal_count}"
            ),
            (
                f"queue.ready={_bool_at(readiness, ('queue', 'ready'))}; "
                f"runnable_proposal_count={_int_at(readiness, ('queue', 'runnable_proposal_count'))}"
            ),
            "Runnable proposal queue has at least one candidate.",
        ),
    ]


def _auto_policy_metric_predicates(
    *,
    readiness: dict[str, Any],
    thresholds: AutoPolicyThresholds,
) -> list[dict[str, Any]]:
    metrics_path = ("learning_readiness", "metrics")
    return [
        _predicate_result(
            "same_eval_run_count_minimum",
            "pass"
            if _int_at(readiness, (*metrics_path, "same_eval_run_count")) >= thresholds.min_same_eval_runs
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            f"learning_readiness.metrics.same_eval_run_count >= {thresholds.min_same_eval_runs}",
            f"same_eval_run_count={_int_at(readiness, (*metrics_path, 'same_eval_run_count'))}",
            "Same-eval evidence has enough repeated comparable runs.",
        ),
        _predicate_result(
            "same_eval_reason_coverage_full",
            "pass"
            if _float_at(readiness, (*metrics_path, "same_eval_reason_code_coverage_ratio"))
            >= thresholds.min_coverage
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            f"same_eval_reason_code_coverage_ratio >= {thresholds.min_coverage}",
            (
                "same_eval_reason_code_coverage_ratio="
                f"{_float_at(readiness, (*metrics_path, 'same_eval_reason_code_coverage_ratio'))}"
            ),
            "Same-eval reason codes are complete.",
        ),
        _predicate_result(
            "strict_secondary_coverage_full",
            "pass"
            if _float_at(readiness, (*metrics_path, "strict_secondary_improvement_coverage_ratio"))
            >= thresholds.min_coverage
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            f"strict_secondary_improvement_coverage_ratio >= {thresholds.min_coverage}",
            (
                "strict_secondary_improvement_coverage_ratio="
                f"{_float_at(readiness, (*metrics_path, 'strict_secondary_improvement_coverage_ratio'))}"
            ),
            "Strict-secondary improvement coverage is complete.",
        ),
        _predicate_result(
            "behavior_delta_digest_coverage_full",
            "pass"
            if _float_at(readiness, (*metrics_path, "behavior_delta_digest_coverage_ratio"))
            >= thresholds.min_coverage
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            f"behavior_delta_digest_coverage_ratio >= {thresholds.min_coverage}",
            (
                "behavior_delta_digest_coverage_ratio="
                f"{_float_at(readiness, (*metrics_path, 'behavior_delta_digest_coverage_ratio'))}"
            ),
            "Behavior-delta digest coverage is complete.",
        ),
        _predicate_result(
            "rework_and_escape_budget_clean",
            "pass"
            if _int_at(readiness, (*metrics_path, "rework_count")) <= thresholds.max_rework_count
            and _int_at(readiness, (*metrics_path, "defect_escape_pair_count"))
            <= thresholds.max_defect_escape_pair_count
            else "fail",
            "ops/reports/auto-improve-readiness.json",
            (
                f"rework_count <= {thresholds.max_rework_count} and "
                f"defect_escape_pair_count <= {thresholds.max_defect_escape_pair_count}"
            ),
            (
                f"rework_count={_int_at(readiness, (*metrics_path, 'rework_count'))}; "
                f"defect_escape_pair_count={_int_at(readiness, (*metrics_path, 'defect_escape_pair_count'))}"
            ),
            "Shadow learning risk budget is clean for automatic narrow claim unlock.",
        ),
    ]


def _auto_policy_predicate_results(
    *,
    readiness: dict[str, Any],
    bundle_validation: dict[str, Any],
    evidence_bundle_path: str,
    blocking_signal_ids: list[str],
    blocking_blocker_ids: list[str],
    thresholds: AutoPolicyThresholds,
) -> list[dict[str, Any]]:
    return [
        *_auto_policy_readiness_predicates(
            readiness=readiness,
            bundle_validation=bundle_validation,
            evidence_bundle_path=evidence_bundle_path,
            blocking_signal_ids=blocking_signal_ids,
            blocking_blocker_ids=blocking_blocker_ids,
            thresholds=thresholds,
        ),
        *_auto_policy_metric_predicates(
            readiness=readiness,
            thresholds=thresholds,
        ),
    ]


def _claim_level_for_decision(decision: str, confirmed: dict[str, Any]) -> str:
    if confirmed["confirmed_learning_improvement_allowed"]:
        return "confirmed_learning_improvement"
    if decision == "auto_approved":
        return "bounded_learning_likely"
    return "none"


def _machine_policy_decision(
    vault: Path,
    *,
    auto_policy_path: str,
    evidence_bundle_path: str,
    confirmed_policy_path: str,
    readiness: dict[str, Any],
    blocking_signal_ids: list[str],
    blocking_blocker_ids: list[str],
) -> dict[str, Any]:
    if not auto_policy_path:
        return _disabled_machine_policy_decision(
            vault,
            auto_policy_path="",
            evidence_bundle_path=evidence_bundle_path,
            confirmed_policy_path=confirmed_policy_path,
        )
    resolved_policy = vault / auto_policy_path
    policy = load_optional_json_object(resolved_policy)
    if not policy or not bool(policy.get("enabled")):
        return _disabled_machine_policy_decision(
            vault,
            auto_policy_path=auto_policy_path,
            policy_version=policy.get("version") if policy else None,
            evidence_bundle_path=evidence_bundle_path,
            confirmed_policy_path=confirmed_policy_path,
        )

    thresholds = _auto_policy_thresholds(policy)
    bundle_validation = validate_learning_claim_evidence_bundle(vault, bundle_path=evidence_bundle_path)
    predicates = _auto_policy_predicate_results(
        readiness=readiness,
        bundle_validation=bundle_validation,
        evidence_bundle_path=evidence_bundle_path,
        blocking_signal_ids=blocking_signal_ids,
        blocking_blocker_ids=blocking_blocker_ids,
        thresholds=thresholds,
    )
    approved = all(item["status"] == "pass" for item in predicates)
    confirmed = _confirmed_policy_decision(
        vault,
        confirmed_policy_path=confirmed_policy_path,
        bundle_validation=bundle_validation,
    )
    decision = "auto_approved" if approved else "requires_human"
    if bundle_validation["revocation_status"] == "revoked":
        decision = "rejected"
    return {
        "enabled": True,
        "policy_path": report_path(vault, resolved_policy),
        "policy_version": policy.get("version"),
        "decision": decision,
        "evidence_bundle_digest": bundle_validation["bundle_sha256"],
        "bundle_path": evidence_bundle_path,
        "bundle_sha256": bundle_validation["bundle_sha256"],
        "current_bundle_sha256": bundle_validation["current_bundle_sha256"],
        "bundle_status": bundle_validation["bundle_status"],
        "bundle_fingerprint_match_status": bundle_validation["bundle_fingerprint_match_status"],
        "revocation_status": bundle_validation["revocation_status"],
        "claim_level": _claim_level_for_decision(decision, confirmed),
        "claim_scope": str(policy.get("claim_scope", "")).strip(),
        "bounded_learning_claim_allowed": decision == "auto_approved",
        "confirmed_learning_improvement_allowed": bool(confirmed["confirmed_learning_improvement_allowed"]),
        "improvement_claim_status": confirmed["improvement_claim_status"],
        "confirmed_learning_improvement_status": confirmed["confirmed_learning_improvement_status"],
        "evidence_cohort_status": confirmed["evidence_cohort_status"],
        "learning_claim_blocker_status": confirmed["learning_claim_blocker_status"],
        "claim_wording_allowed": confirmed["claim_wording_allowed"],
        "claim_wording_policy_status": confirmed["claim_wording_policy_status"],
        "confirmed_policy_path": confirmed["confirmed_policy_path"],
        "confirmed_policy_version": confirmed["confirmed_policy_version"],
        "confirmed_evidence_cohort_path": confirmed["confirmed_evidence_cohort_path"],
        "confirmed_evidence_cohort_sha256": confirmed["confirmed_evidence_cohort_sha256"],
        "current_confirmed_evidence_cohort_sha256": confirmed["current_confirmed_evidence_cohort_sha256"],
        "confirmed_evidence_cohort_status": confirmed["confirmed_evidence_cohort_status"],
        "confirmed_evidence_cohort_fingerprint_match_status": confirmed[
            "confirmed_evidence_cohort_fingerprint_match_status"
        ],
        "confirmed_evidence_summary": confirmed["confirmed_evidence_summary"],
        "confirmed_predicate_results": confirmed["confirmed_predicate_results"],
        "predicate_results": predicates,
    }


def _review_item(
    item_id: str,
    status: str,
    source_path: str,
    summary: str,
    *,
    required_condition: str,
    observed_value: str,
    requires_human_review: bool,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "status": status,
        "source_path": source_path,
        "required_condition": required_condition,
        "observed_value": observed_value,
        "requires_human_review": requires_human_review,
        "summary": summary,
    }


def _unlock_review_decision(
    *,
    machine_policy: dict[str, Any],
    approved_by: str,
    reviewed_at: str,
    blocking_signal_ids: list[str],
    blocking_blocker_ids: list[str],
) -> UnlockReviewDecision:
    normalized_approved_by = approved_by.strip()
    normalized_reviewed_at = reviewed_at.strip()
    operator_review_present = bool(normalized_approved_by) and bool(normalized_reviewed_at)
    operator_approved = operator_review_present and not blocking_signal_ids and not blocking_blocker_ids
    machine_approved = machine_policy["decision"] == "auto_approved"
    approved = operator_approved or machine_approved
    review_status = (
        "auto_approved"
        if machine_approved and not operator_approved
        else ("approved" if approved else "required")
    )
    approval_mode = (
        "machine_policy"
        if machine_approved and not operator_approved
        else ("human_operator" if operator_approved else "none")
    )
    operator_review_value = (
        f"reviewed=true; reviewed_by={normalized_approved_by}; reviewed_at={normalized_reviewed_at}"
        if operator_review_present
        else "reviewed=false"
    )
    readiness_observed_value = (
        "learning_readiness.signals=[]; release_blockers=[]"
        if not blocking_signal_ids and not blocking_blocker_ids
        else (
            "learning_readiness.signals="
            + (",".join(blocking_signal_ids) or "<none>")
            + "; release_blockers="
            + (",".join(blocking_blocker_ids) or "<none>")
        )
    )
    return UnlockReviewDecision(
        approved_by=normalized_approved_by,
        reviewed_at=normalized_reviewed_at,
        operator_review_present=operator_review_present,
        operator_approved=operator_approved,
        machine_approved=machine_approved,
        approved=approved,
        review_status=review_status,
        approval_mode=approval_mode,
        reviewed_surface_status="pass" if operator_review_present or machine_approved else "pending",
        readiness_status="pass" if not blocking_signal_ids and not blocking_blocker_ids else "fail",
        operator_review_value=operator_review_value,
        readiness_observed_value=readiness_observed_value,
        decision_reason=_unlock_decision_reason(
            machine_approved=machine_approved,
            operator_approved=operator_approved,
        ),
    )


def _unlock_decision_reason(*, machine_approved: bool, operator_approved: bool) -> str:
    if machine_approved and not operator_approved:
        return "Machine policy auto-approved the bounded learning-likely claim for the active evidence bundle."
    if operator_approved:
        return "Operator approved all learning claim unlock evidence surfaces."
    return (
        "Typed same-eval coverage may be full, but learning claim unlock remains inappropriate "
        "until an operator approves release dashboard, readiness, strict-secondary axes, and "
        "behavior-delta provenance after remaining readiness signals close."
    )


def _unlock_review_items(
    *,
    machine_policy: dict[str, Any],
    decision: UnlockReviewDecision,
    blocking_signal_ids: list[str],
    blocking_blocker_ids: list[str],
) -> list[dict[str, Any]]:
    machine_approved = decision.machine_approved
    return [
        _review_item(
            "release_evidence_dashboard",
            decision.reviewed_surface_status,
            "ops/reports/release-evidence-dashboard.json",
            (
                "Machine policy accepted dashboard review as covered by zero readiness blockers."
                if machine_approved
                else "Operator must review the release evidence dashboard learning-claim guard and placeholder audit."
            ),
            required_condition=(
                "machine_policy_decision.decision == auto_approved"
                if machine_approved
                else "release_evidence_dashboard.reviewed_by_operator == true"
            ),
            observed_value=(
                f"machine_policy_decision={machine_policy['decision']}"
                if machine_approved
                else decision.operator_review_value
            ),
            requires_human_review=not machine_approved,
        ),
        _review_item(
            "auto_improve_readiness",
            decision.readiness_status,
            "ops/reports/auto-improve-readiness.json",
            (
                "Current readiness has no blocking learning signals or learning release blockers."
                if not blocking_signal_ids and not blocking_blocker_ids
                else (
                    "Current readiness still reports learning claim blockers: "
                    + ", ".join([*blocking_signal_ids, *blocking_blocker_ids])
                )
            ),
            required_condition=(
                "auto_improve_readiness.learning_readiness.signals == [] "
                "and auto_improve_readiness.release_blockers == []"
            ),
            observed_value=decision.readiness_observed_value,
            requires_human_review=False,
        ),
        _review_item(
            "strict_secondary_axes",
            decision.reviewed_surface_status,
            "runs/**/run-telemetry.json",
            (
                "Machine policy accepted strict-secondary coverage from auto-improve readiness metrics."
                if machine_approved
                else "Operator must review strict-secondary improvement axes against promotion artifacts."
            ),
            required_condition=(
                "machine_policy_decision.strict_secondary_coverage_full == pass"
                if machine_approved
                else "strict_secondary_axes.reviewed_by_operator == true"
            ),
            observed_value=(
                f"machine_policy_decision={machine_policy['decision']}"
                if machine_approved
                else decision.operator_review_value
            ),
            requires_human_review=not machine_approved,
        ),
        _review_item(
            "behavior_delta_provenance",
            decision.reviewed_surface_status,
            "runs/**/run-telemetry.json",
            (
                "Machine policy accepted behavior-delta digest coverage from auto-improve readiness metrics."
                if machine_approved
                else "Operator must review behavior_delta_digest provenance before unlock."
            ),
            required_condition=(
                "machine_policy_decision.behavior_delta_digest_coverage_full == pass"
                if machine_approved
                else "behavior_delta_digest_provenance.reviewed_by_operator == true"
            ),
            observed_value=(
                f"machine_policy_decision={machine_policy['decision']}"
                if machine_approved
                else decision.operator_review_value
            ),
            requires_human_review=not machine_approved,
        ),
    ]


def _required_followup_for_unlock(approved: bool) -> list[str]:
    if approved:
        return []
    return [
        "Close or explicitly review remaining auto_improve_readiness learning signals.",
        "Close any open auto_improve_readiness learning release blockers.",
        "Rebuild release evidence dashboard and auto-improve readiness after readiness signals change.",
        "Approve all learning claim unlock review items only after the refreshed evidence is reviewed.",
    ]


def build_report(
    vault: Path,
    *,
    approved_by: str = "",
    reviewed_at: str = "",
    auto_policy_path: str = "",
    evidence_bundle_path: str = DEFAULT_EVIDENCE_BUNDLE_PATH,
    confirmed_policy_path: str = DEFAULT_CONFIRMED_POLICY_PATH,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    readiness = load_optional_json_object(vault / "ops/reports/auto-improve-readiness.json")
    blocking_signal_ids = _learning_signal_ids(readiness)
    blocking_blocker_ids = _learning_blocker_ids(readiness)
    machine_policy = _machine_policy_decision(
        vault,
        auto_policy_path=auto_policy_path,
        evidence_bundle_path=evidence_bundle_path,
        confirmed_policy_path=confirmed_policy_path,
        readiness=readiness,
        blocking_signal_ids=blocking_signal_ids,
        blocking_blocker_ids=blocking_blocker_ids,
    )
    unlock_decision = _unlock_review_decision(
        machine_policy=machine_policy,
        approved_by=approved_by,
        reviewed_at=reviewed_at,
        blocking_signal_ids=blocking_signal_ids,
        blocking_blocker_ids=blocking_blocker_ids,
    )

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="learning_claim_unlock_review",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/learning/learning_claim_unlock_review.py",
                "ops/scripts/learning/learning_claim_evidence_bundle.py",
                "ops/scripts/learning/learning_readiness_vocabulary.py",
            ],
            file_inputs={
                "auto_improve_readiness": "ops/reports/auto-improve-readiness.json",
                "learning_claim_evidence_bundle": evidence_bundle_path,
            },
            text_inputs={
                "approved_by": unlock_decision.approved_by,
                "reviewed_at": unlock_decision.reviewed_at,
                "blocking_signal_ids": ",".join(blocking_signal_ids),
                "blocking_blocker_ids": ",".join(blocking_blocker_ids),
                "auto_policy_path": auto_policy_path,
                "evidence_bundle_path": evidence_bundle_path,
                "confirmed_policy_path": confirmed_policy_path,
                "machine_policy_decision": machine_policy["decision"],
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "review_status": unlock_decision.review_status,
        "approved": unlock_decision.approved,
        "approval_mode": unlock_decision.approval_mode,
        "reviewed_by": unlock_decision.approved_by,
        "reviewed_at": unlock_decision.reviewed_at,
        "decision_reason": unlock_decision.decision_reason,
        "source_paths": [
            "ops/reports/release-evidence-dashboard.json",
            "ops/reports/auto-improve-readiness.json",
            evidence_bundle_path,
            "runs/**/run-telemetry.json",
            "external-reports/report-reference-manifest.json",
        ],
        "blocking_signal_ids": blocking_signal_ids,
        "blocking_blocker_ids": blocking_blocker_ids,
        "improvement_claim_status": machine_policy["improvement_claim_status"],
        "evidence_cohort_status": machine_policy["evidence_cohort_status"],
        "learning_claim_blocker_status": machine_policy["learning_claim_blocker_status"],
        "claim_wording_allowed": machine_policy["claim_wording_allowed"],
        "claim_wording_policy_status": machine_policy["claim_wording_policy_status"],
        "machine_policy_decision": machine_policy,
        "review_items": _unlock_review_items(
            machine_policy=machine_policy,
            decision=unlock_decision,
            blocking_signal_ids=blocking_signal_ids,
            blocking_blocker_ids=blocking_blocker_ids,
        ),
        "required_followup": _required_followup_for_unlock(unlock_decision.approved),
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning claim unlock review schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the learning claim unlock review artifact")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--approved-by", default="")
    parser.add_argument("--reviewed-at", default="")
    parser.add_argument("--auto-policy", default="")
    parser.add_argument("--evidence-bundle", default=DEFAULT_EVIDENCE_BUNDLE_PATH)
    parser.add_argument("--confirmed-policy", default=DEFAULT_CONFIRMED_POLICY_PATH)
    parser.add_argument("--policy-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        approved_by=args.approved_by,
        reviewed_at=args.reviewed_at,
        auto_policy_path=args.auto_policy,
        evidence_bundle_path=args.evidence_bundle,
        confirmed_policy_path=args.confirmed_policy,
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
