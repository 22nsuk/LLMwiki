from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object

from .learning_claim_evidence_bundle import (
    DEFAULT_OUT as LEARNING_CLAIM_EVIDENCE_BUNDLE_PATH,
)
from .learning_claim_evidence_bundle import (
    validate_learning_claim_evidence_bundle,
)
from .learning_claim_model import (
    learning_claim_blocker_status,
    normalize_evidence_cohort_summary,
)
from .learning_delta_scoreboard_constants import (
    LEARNING_CLAIM_UNLOCK_REVIEW_PATH,
    REQUIRED_LEARNING_CLAIM_REVIEW_ITEMS,
)


def _confirmed_evidence_summary(
    value: object,
    *,
    confirmed_blocking_predicate_ids: list[str] | None = None,
) -> dict[str, Any]:
    return normalize_evidence_cohort_summary(
        value,
        blocking_predicate_ids=confirmed_blocking_predicate_ids,
    )


@dataclass(frozen=True)
class LearningClaimUnlockState:
    review: dict[str, Any]
    review_status: str
    machine_policy: dict[str, Any]
    confirmed_predicate_results: list[dict[str, Any]]
    confirmed_blocking_predicate_ids: list[str]
    confirmed_evidence_summary: dict[str, Any]
    evidence_cohort_status: str
    improvement_claim_status: str
    learning_claim_blocker_status: str
    bundle_validation: dict[str, Any]
    auto_approval_active: bool


def _review_items_pass(review: dict[str, Any]) -> bool:
    items = review.get("review_items", [])
    if not isinstance(items, list) or not items:
        return False
    return all(
        isinstance(item, dict) and str(item.get("status", "")).strip() == "pass"
        for item in items
    )


def _confirmed_predicate_results(machine_policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in machine_policy.get("confirmed_predicate_results", [])
        if isinstance(item, dict)
    ]


def _confirmed_blocking_predicate_ids(predicates: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("id", "")).strip()
        for item in predicates
        if str(item.get("id", "")).strip()
        and str(item.get("status", "")).strip() != "pass"
    ]


def _machine_policy_payload(review: dict[str, Any]) -> dict[str, Any]:
    machine_policy = review.get("machine_policy_decision")
    return machine_policy if isinstance(machine_policy, dict) else {}


def _learning_claim_bundle_validation(
    vault: Path,
    *,
    review_status: str,
    machine_policy: dict[str, Any],
) -> dict[str, Any]:
    bundle_path = str(machine_policy.get("bundle_path", LEARNING_CLAIM_EVIDENCE_BUNDLE_PATH)).strip()
    if review_status == "auto_approved":
        return validate_learning_claim_evidence_bundle(vault, bundle_path=bundle_path)
    return {
        "bundle_path": bundle_path,
        "bundle_status": "not_evaluated",
        "bundle_sha256": str(machine_policy.get("bundle_sha256", "")).strip(),
        "current_bundle_sha256": "",
        "bundle_fingerprint_match_status": "not_evaluated",
        "revocation_status": "not_evaluated",
        "reasons": [],
    }


def _auto_approval_active(
    *,
    review_status: str,
    machine_policy: dict[str, Any],
    bundle_validation: dict[str, Any],
) -> bool:
    return review_status != "auto_approved" or (
        bundle_validation["revocation_status"] == "active"
        and str(machine_policy.get("bundle_sha256", "")).strip() == bundle_validation["bundle_sha256"]
    )


def _learning_claim_unlock_state(vault: Path) -> LearningClaimUnlockState:
    review = load_optional_json_object(vault / LEARNING_CLAIM_UNLOCK_REVIEW_PATH)
    review_status = str(review.get("review_status", "")).strip()
    machine_policy = _machine_policy_payload(review)
    confirmed_predicates = _confirmed_predicate_results(machine_policy)
    blocking_predicate_ids = _confirmed_blocking_predicate_ids(confirmed_predicates)
    confirmed_summary = _confirmed_evidence_summary(
        machine_policy.get("confirmed_evidence_summary"),
        confirmed_blocking_predicate_ids=blocking_predicate_ids,
    )
    evidence_cohort_status = str(
        confirmed_summary.get("evidence_cohort_status", "not_ready")
    ).strip() or "not_ready"
    improvement_claim_status = (
        str(
            machine_policy.get(
                "improvement_claim_status",
                machine_policy.get("confirmed_learning_improvement_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )
    bundle_validation = _learning_claim_bundle_validation(
        vault,
        review_status=review_status,
        machine_policy=machine_policy,
    )
    return LearningClaimUnlockState(
        review=review,
        review_status=review_status,
        machine_policy=machine_policy,
        confirmed_predicate_results=confirmed_predicates,
        confirmed_blocking_predicate_ids=blocking_predicate_ids,
        confirmed_evidence_summary=confirmed_summary,
        evidence_cohort_status=evidence_cohort_status,
        improvement_claim_status=improvement_claim_status,
        learning_claim_blocker_status=str(
            machine_policy.get(
                "learning_claim_blocker_status",
                learning_claim_blocker_status(blocking_predicate_ids)
                if confirmed_predicates
                else "not_evaluated",
            )
        ).strip()
        or "not_evaluated",
        bundle_validation=bundle_validation,
        auto_approval_active=_auto_approval_active(
            review_status=review_status,
            machine_policy=machine_policy,
            bundle_validation=bundle_validation,
        ),
    )


def _learning_claim_review_approved(
    *,
    state: LearningClaimUnlockState,
    evidence_complete: bool,
    readiness_signal_ids: list[str],
    readiness_blocker_ids: list[str],
) -> bool:
    return (
        evidence_complete
        and bool(state.review.get("approved"))
        and state.review_status in {"approved", "auto_approved"}
        and _review_items_pass(state.review)
        and not readiness_signal_ids
        and not readiness_blocker_ids
        and state.auto_approval_active
    )


def _learning_claim_review_common_payload(state: LearningClaimUnlockState) -> dict[str, Any]:
    machine_policy = state.machine_policy
    bundle_validation = state.bundle_validation
    return {
        "claim_scope": str(machine_policy.get("claim_scope", "")).strip(),
        "confirmed_learning_improvement_status": str(
            machine_policy.get("confirmed_learning_improvement_status", "not_ready")
        ).strip()
        or "not_ready",
        "improvement_claim_status": state.improvement_claim_status,
        "evidence_cohort_status": state.evidence_cohort_status,
        "learning_claim_blocker_status": state.learning_claim_blocker_status,
        "claim_wording_allowed": bool(machine_policy.get("claim_wording_allowed", False)),
        "claim_wording_policy_status": str(
            machine_policy.get("claim_wording_policy_status", "blocked")
        ).strip()
        or "blocked",
        "confirmed_blocking_predicate_ids": state.confirmed_blocking_predicate_ids,
        "confirmed_evidence_summary": state.confirmed_evidence_summary,
        "confirmed_predicate_results": state.confirmed_predicate_results,
        "bundle_status": str(bundle_validation["bundle_status"]),
        "bundle_sha256": str(bundle_validation["bundle_sha256"]),
        "current_bundle_sha256": str(bundle_validation["current_bundle_sha256"]),
        "revocation_status": str(bundle_validation["revocation_status"]),
        "confirmed_evidence_cohort_path": str(
            machine_policy.get("confirmed_evidence_cohort_path", "")
        ).strip(),
        "confirmed_evidence_cohort_sha256": str(
            machine_policy.get("confirmed_evidence_cohort_sha256", "")
        ).strip(),
        "current_confirmed_evidence_cohort_sha256": str(
            machine_policy.get("current_confirmed_evidence_cohort_sha256", "")
        ).strip(),
        "confirmed_evidence_cohort_status": str(
            machine_policy.get("confirmed_evidence_cohort_status", "not_evaluated")
        ).strip()
        or "not_evaluated",
        "confirmed_evidence_cohort_fingerprint_match_status": str(
            machine_policy.get(
                "confirmed_evidence_cohort_fingerprint_match_status",
                "not_evaluated",
            )
        ).strip()
        or "not_evaluated",
    }


def _approved_learning_claim_unlock_payload(
    *,
    state: LearningClaimUnlockState,
    status: str,
) -> dict[str, Any]:
    machine_policy = state.machine_policy
    return {
        "status": status,
        "approved": True,
        "claim_level": (
            "confirmed_learning_improvement"
            if bool(machine_policy.get("confirmed_learning_improvement_allowed"))
            else ("bounded_learning_likely" if status == "auto_approved" else "human_reviewed_learning_claim")
        ),
        "bounded_learning_claim_allowed": status == "auto_approved" or status == "approved",
        "confirmed_learning_improvement_allowed": bool(
            machine_policy.get("confirmed_learning_improvement_allowed")
        ),
        **_learning_claim_review_common_payload(state),
        "source_path": LEARNING_CLAIM_UNLOCK_REVIEW_PATH,
        "reason": (
            "learning claim unlock review artifact machine-approved all required evidence surfaces"
            if status == "auto_approved"
            else "learning claim unlock review artifact approved all required evidence surfaces"
        ),
        "required_review_items": REQUIRED_LEARNING_CLAIM_REVIEW_ITEMS,
    }


def _blocked_learning_claim_unlock_status_reason(
    *,
    state: LearningClaimUnlockState,
    evidence_complete: bool,
    readiness_signal_ids: list[str],
    readiness_blocker_ids: list[str],
) -> tuple[str, str]:
    bundle_validation = state.bundle_validation
    if state.review_status == "auto_approved" and bundle_validation["revocation_status"] in {"stale", "revoked"}:
        status = str(bundle_validation["revocation_status"])
        reason = (
            "learning claim auto approval is no longer active for the current evidence bundle: "
            + "; ".join(str(reason) for reason in bundle_validation.get("reasons", []) if str(reason).strip())
        )
    elif evidence_complete and (readiness_signal_ids or readiness_blocker_ids):
        status = "required"
        reason = (
            "typed same-eval coverage is complete, but auto_improve_readiness still reports "
            "learning claim blockers requiring operator review: "
            + ", ".join([*readiness_signal_ids, *readiness_blocker_ids])
        )
    elif evidence_complete and state.review:
        status = "required"
        reason = "learning claim unlock review artifact is present but not approved"
    elif evidence_complete:
        status = "required"
        reason = (
            "typed same-eval coverage is complete; explicit release-dashboard/readiness/provenance "
            "review is still required before learning claims can open"
        )
    else:
        status = "not_ready"
        reason = "typed same-eval coverage and placeholder/provenance evidence are not complete"
    return status, reason


def _blocked_learning_claim_unlock_payload(
    *,
    state: LearningClaimUnlockState,
    evidence_complete: bool,
    reason: str,
    status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "approved": False,
        "claim_level": "learning_likely" if evidence_complete else "none",
        "bounded_learning_claim_allowed": False,
        "confirmed_learning_improvement_allowed": False,
        **_learning_claim_review_common_payload(state),
        "source_path": LEARNING_CLAIM_UNLOCK_REVIEW_PATH if state.review else "",
        "reason": reason,
        "required_review_items": REQUIRED_LEARNING_CLAIM_REVIEW_ITEMS,
    }


def _learning_claim_unlock_review(
    vault: Path,
    evidence_complete: bool,
    *,
    readiness_signal_ids: list[str],
    readiness_blocker_ids: list[str],
) -> dict[str, Any]:
    state = _learning_claim_unlock_state(vault)
    if _learning_claim_review_approved(
        state=state,
        evidence_complete=evidence_complete,
        readiness_signal_ids=readiness_signal_ids,
        readiness_blocker_ids=readiness_blocker_ids,
    ):
        status = "auto_approved" if state.review_status == "auto_approved" else "approved"
        return _approved_learning_claim_unlock_payload(state=state, status=status)

    status, reason = _blocked_learning_claim_unlock_status_reason(
        state=state,
        evidence_complete=evidence_complete,
        readiness_signal_ids=readiness_signal_ids,
        readiness_blocker_ids=readiness_blocker_ids,
    )
    return _blocked_learning_claim_unlock_payload(
        state=state,
        evidence_complete=evidence_complete,
        reason=reason,
        status=status,
    )


