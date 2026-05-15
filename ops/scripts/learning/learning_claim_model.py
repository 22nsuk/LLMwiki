from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLAIM_MODEL_VERSION = 2
CLAIM_STAGES = [
    "regression_safe",
    "same_eval_gain",
    "cross_eval_gain",
    "persistence",
    "production_learning",
]


@dataclass(frozen=True)
class ImprovementClaimInputs:
    guard_status: str
    claims_learning_improved: bool
    learning_claim_evidence_complete: bool
    bounded_learning_claim_allowed: bool
    confirmed_learning_improvement_allowed: bool
    improvement_claim_status: str
    evidence_cohort_status: str
    claim_level: str
    bundle_status: str
    blocking_predicate_ids: list[str]
    same_eval_run_count: int
    same_eval_reason_coverage_status: str
    strict_secondary_improvement_coverage_status: str
    behavior_delta_digest_coverage_status: str
    learning_claim_blocker_status: str = ""


def _stage(stage: str, status: str, *, evidence: list[str], summary: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "evidence": evidence,
        "summary": summary,
    }


def learning_claim_blocker_status(blocking_predicate_ids: list[str]) -> str:
    return "blocked" if blocking_predicate_ids else "clear"


def normalize_evidence_cohort_summary(
    value: object,
    *,
    blocking_predicate_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    status = (
        str(
            payload.get(
                "evidence_cohort_status",
                payload.get("confirmed_evidence_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )
    legacy_summary = payload.get("legacy_reconstruction_summary")
    return {
        "evidence_cohort_status": status,
        "confirmed_evidence_status": status,
        "valid_run_count": int(payload.get("valid_run_count", 0) or 0),
        "min_required_run_count": int(payload.get("min_required_run_count", 0) or 0),
        "eligible_family_count": int(payload.get("eligible_family_count", 0) or 0),
        "selected_valid_run_ids": [
            str(item).strip()
            for item in payload.get("selected_valid_run_ids", [])
            if str(item).strip()
        ],
        "blocking_predicate_ids": [
            str(item).strip()
            for item in payload.get(
                "blocking_predicate_ids", blocking_predicate_ids or []
            )
            if str(item).strip()
        ],
        "rejected_run_count": int(payload.get("rejected_run_count", 0) or 0),
        "rejected_run_diagnostics": [
            item
            for item in payload.get("rejected_run_diagnostics", [])
            if isinstance(item, dict)
        ],
        "legacy_reconstruction_summary": legacy_summary
        if isinstance(legacy_summary, dict)
        else {
            "status": "not_used",
            "reconstruction_needed_count": 0,
            "reconstructed_run_count": 0,
            "blocked_run_count": 0,
            "run_diagnostics": [],
        },
    }


def improvement_claim_model(inputs: ImprovementClaimInputs) -> dict[str, Any]:
    blocker_status = inputs.learning_claim_blocker_status.strip() or learning_claim_blocker_status(
        inputs.blocking_predicate_ids
    )
    if blocker_status not in {"clear", "blocked", "not_evaluated"}:
        blocker_status = learning_claim_blocker_status(inputs.blocking_predicate_ids)
    regression_safe_status = "pass" if inputs.guard_status == "pass" else "blocked"
    same_eval_status = (
        "pass"
        if inputs.bounded_learning_claim_allowed
        else ("blocked" if inputs.claims_learning_improved else "not_claimed")
    )
    cross_eval_status = "not_evaluated"
    persistence_status = (
        "pass"
        if inputs.evidence_cohort_status == "auto_confirmed"
        and not inputs.blocking_predicate_ids
        else "blocked"
        if inputs.blocking_predicate_ids
        else "not_ready"
    )
    production_status = (
        "pass"
        if (
            inputs.confirmed_learning_improvement_allowed
            and inputs.improvement_claim_status == "auto_confirmed"
            and inputs.evidence_cohort_status == "auto_confirmed"
            and inputs.bundle_status == "active"
            and not inputs.blocking_predicate_ids
        )
        else "blocked"
    )
    stages = [
        _stage(
            "regression_safe",
            regression_safe_status,
            evidence=[f"learning_claim_guard.status={inputs.guard_status}"],
            summary="Release may say no learning claim regression blockers are active; this is not a learning-improvement claim.",
        ),
        _stage(
            "same_eval_gain",
            same_eval_status,
            evidence=[
                f"same_eval_run_count={inputs.same_eval_run_count}",
                f"same_eval_reason_coverage_status={inputs.same_eval_reason_coverage_status}",
                f"strict_secondary_improvement_coverage_status={inputs.strict_secondary_improvement_coverage_status}",
                f"behavior_delta_digest_coverage_status={inputs.behavior_delta_digest_coverage_status}",
                f"learning_claim_evidence_complete={str(inputs.learning_claim_evidence_complete).lower()}",
            ],
            summary="Same-eval gain requires full typed reason, strict-secondary, and behavior-delta evidence.",
        ),
        _stage(
            "cross_eval_gain",
            cross_eval_status,
            evidence=[],
            summary="No cross-eval evidence lane is registered for automatic wording yet.",
        ),
        _stage(
            "persistence",
            persistence_status,
            evidence=[
                f"evidence_cohort_status={inputs.evidence_cohort_status}",
                f"learning_claim_blocker_status={blocker_status}",
                "blocking_predicate_ids="
                + (",".join(inputs.blocking_predicate_ids) or "[]"),
            ],
            summary="Persistence requires the confirmed evidence cohort to auto-confirm without blocking predicates.",
        ),
        _stage(
            "production_learning",
            production_status,
            evidence=[
                f"improvement_claim_status={inputs.improvement_claim_status}",
                f"evidence_cohort_status={inputs.evidence_cohort_status}",
                f"bundle_status={inputs.bundle_status}",
                f"claim_level={inputs.claim_level}",
            ],
            summary="Production learning wording opens only after confirmed claim, confirmed cohort, and active bundle evidence align.",
        ),
    ]
    highest_supported_stage = "none"
    for item in stages:
        if item["status"] == "pass":
            highest_supported_stage = str(item["stage"])
    claim_wording_allowed = production_status == "pass"
    return {
        "schema_version": CLAIM_MODEL_VERSION,
        "stage_order": CLAIM_STAGES,
        "stages": stages,
        "highest_supported_stage": highest_supported_stage,
        "improvement_claim_status": inputs.improvement_claim_status,
        "evidence_cohort_status": inputs.evidence_cohort_status,
        "learning_claim_blocker_status": blocker_status,
        "claim_wording_allowed": claim_wording_allowed,
        "claim_wording_policy_status": "pre_seal_ready"
        if claim_wording_allowed
        else "blocked",
        "summary": (
            f"highest_supported_stage={highest_supported_stage}; "
            f"improvement_claim_status={inputs.improvement_claim_status}; "
            f"evidence_cohort_status={inputs.evidence_cohort_status}; "
            f"learning_claim_blocker_status={blocker_status}; "
            f"claim_wording_allowed={str(claim_wording_allowed).lower()}"
        ),
    }
