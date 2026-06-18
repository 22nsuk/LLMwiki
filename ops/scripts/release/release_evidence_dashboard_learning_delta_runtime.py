from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.scripts.core.learning_claim_state_runtime import (
    confirmed_blocking_predicate_ids,
    confirmed_evidence_summary,
    confirmed_predicate_results,
    confirmed_wording_allowed,
    evidence_cohort_status,
    improvement_claim_status,
    learning_claim_bundle_status,
)
from ops.scripts.learning.learning_claim_model import (
    ImprovementClaimInputs,
    improvement_claim_model,
    learning_claim_blocker_status,
)
from ops.scripts.release.release_evidence_dashboard_render_runtime import (
    LEARNING_DELTA_SCOREBOARD_PATH,
)


@dataclass(frozen=True)
class LearningDeltaSections:
    summary: dict[str, Any]
    guard: dict[str, Any]
    unlock: dict[str, Any]
    placeholder_audit: dict[str, Any]


@dataclass(frozen=True)
class LearningDeltaCoverage:
    telemetry_ratio: float
    reason_ratio: float
    strict_secondary_ratio: float
    digest_ratio: float


@dataclass(frozen=True)
class LearningDeltaDecision:
    sections: LearningDeltaSections
    confirmed_predicate_results: list[dict[str, Any]]
    confirmed_blocking_predicate_ids: list[str]
    confirmed_summary: dict[str, Any]
    coverage: LearningDeltaCoverage
    confirmed_status: str
    evidence_cohort_status: str
    learning_claim_blocker_status: str
    claim_level: str
    bundle_status: str
    confirmed_wording_allowed: bool
    claim_model: dict[str, Any]
    claim_wording_policy_status: str


def _coverage_status(value: object) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    if value >= 1.0:
        return "full"
    if value > 0:
        return "partial"
    return "none"


def _summary_coverage_status(summary: dict[str, Any], key: str, ratio_key: str) -> str:
    status = str(summary.get(key, "")).strip()
    if status in {"full", "partial", "none", "no_evidence", "not_applicable"}:
        return status
    return _coverage_status(summary.get(ratio_key))


def _missing_learning_delta_claim_model() -> dict[str, Any]:
    return improvement_claim_model(
        ImprovementClaimInputs(
            guard_status="unknown",
            claims_learning_improved=False,
            learning_claim_evidence_complete=False,
            bounded_learning_claim_allowed=False,
            confirmed_learning_improvement_allowed=False,
            improvement_claim_status="not_ready",
            evidence_cohort_status="not_ready",
            claim_level="none",
            bundle_status="not_evaluated",
            blocking_predicate_ids=[],
            learning_claim_blocker_status="not_evaluated",
            same_eval_run_count=0,
            same_eval_reason_coverage_status="unknown",
            strict_secondary_improvement_coverage_status="unknown",
            behavior_delta_digest_coverage_status="unknown",
        )
    )


def _missing_learning_delta_guard_summary(load_status: str) -> dict[str, Any]:
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "status": "unknown",
        "claims_learning_improved": False,
        "learning_claim_allowed": False,
        "learning_likely": False,
        "bounded_learning_claim_allowed": False,
        "confirmed_learning_improvement_allowed": False,
        "improvement_claim_status": "not_ready",
        "confirmed_learning_improvement_status": "not_ready",
        "evidence_cohort_status": "not_ready",
        "learning_claim_blocker_status": "not_evaluated",
        "confirmed_blocking_predicate_ids": [],
        "confirmed_evidence_summary": confirmed_evidence_summary({}),
        "confirmed_predicate_results": [],
        "claim_level": "none",
        "claim_scope": "",
        "learning_claim_unlock_review_status": "unknown",
        "learning_claim_unlock_review_approved": False,
        "learning_claim_unlock_review_revocation_status": "not_evaluated",
        "learning_claim_evidence_bundle_status": "not_evaluated",
        "claim_wording_allowed": False,
        "claim_wording_policy_status": "blocked",
        "confirmed_wording_allowed": False,
        "confirmed_wording_policy_status": "blocked",
        "self_improvement_claim_model": _missing_learning_delta_claim_model(),
        "learning_claim_unlock_review_source": "",
        "same_eval_run_count": 0,
        "telemetry_coverage_ratio": 0.0,
        "telemetry_coverage_status": "unknown",
        "same_eval_reason_coverage_ratio": 0.0,
        "same_eval_reason_coverage_status": "unknown",
        "strict_secondary_improvement_coverage_ratio": 0.0,
        "strict_secondary_improvement_coverage_status": "unknown",
        "behavior_delta_digest_coverage_ratio": 0.0,
        "behavior_delta_digest_coverage_status": "unknown",
        "placeholder_audit_status": "unknown",
        "placeholder_count": 0,
        "reason": f"learning delta scoreboard load_status={load_status}",
    }


def _learning_delta_sections(payload: dict[str, Any]) -> LearningDeltaSections:
    summary = payload.get("summary")
    guard = payload.get("learning_claim_guard")
    unlock = payload.get("learning_claim_unlock_review")
    placeholder = payload.get("external_report_placeholder_audit")
    return LearningDeltaSections(
        summary=summary if isinstance(summary, dict) else {},
        guard=guard if isinstance(guard, dict) else {},
        unlock=unlock if isinstance(unlock, dict) else {},
        placeholder_audit=placeholder if isinstance(placeholder, dict) else {},
    )


def _confirmed_summary_payload(
    payload: dict[str, Any], unlock: dict[str, Any]
) -> object:
    value = payload.get("confirmed_evidence_summary")
    return value if isinstance(value, dict) else unlock.get("confirmed_evidence_summary")


def _learning_delta_coverage(summary: dict[str, Any]) -> LearningDeltaCoverage:
    return LearningDeltaCoverage(
        telemetry_ratio=float(summary.get("telemetry_coverage_ratio", 0.0) or 0.0),
        reason_ratio=float(
            summary.get("same_eval_reason_coverage_ratio", 0.0) or 0.0
        ),
        strict_secondary_ratio=float(
            summary.get("strict_secondary_improvement_coverage_ratio", 0.0) or 0.0
        ),
        digest_ratio=float(
            summary.get("behavior_delta_digest_coverage_ratio", 0.0) or 0.0
        ),
    )


def _learning_delta_claim_model(
    payload: dict[str, Any],
    sections: LearningDeltaSections,
    *,
    confirmed_status: str,
    evidence_cohort_status: str,
    claim_level: str,
    bundle_status: str,
    blocking_predicate_ids: list[str],
    learning_claim_blocker_status_value: str,
) -> dict[str, Any]:
    summary = sections.summary
    raw_claim_model = summary.get("self_improvement_claim_model")
    if not isinstance(raw_claim_model, dict):
        raw_claim_model = payload.get("self_improvement_claim_model")
    if isinstance(raw_claim_model, dict):
        return raw_claim_model
    return improvement_claim_model(
        ImprovementClaimInputs(
            guard_status=str(
                sections.guard.get("status", payload.get("status", "unknown"))
            ).strip()
            or "unknown",
            claims_learning_improved=bool(summary.get("claims_learning_improved")),
            learning_claim_evidence_complete=bool(
                summary.get("learning_claim_evidence_complete")
            ),
            bounded_learning_claim_allowed=bool(
                summary.get("bounded_learning_claim_allowed")
            ),
            confirmed_learning_improvement_allowed=bool(
                summary.get("confirmed_learning_improvement_allowed")
            ),
            improvement_claim_status=confirmed_status,
            evidence_cohort_status=evidence_cohort_status,
            claim_level=claim_level,
            bundle_status=bundle_status,
            blocking_predicate_ids=blocking_predicate_ids,
            learning_claim_blocker_status=learning_claim_blocker_status_value,
            same_eval_run_count=int(summary.get("same_eval_run_count", 0) or 0),
            same_eval_reason_coverage_status=_summary_coverage_status(
                summary,
                "same_eval_reason_coverage_status",
                "same_eval_reason_coverage_ratio",
            ),
            strict_secondary_improvement_coverage_status=_summary_coverage_status(
                summary,
                "strict_secondary_improvement_coverage_status",
                "strict_secondary_improvement_coverage_ratio",
            ),
            behavior_delta_digest_coverage_status=_summary_coverage_status(
                summary,
                "behavior_delta_digest_coverage_status",
                "behavior_delta_digest_coverage_ratio",
            ),
        )
    )


def _learning_delta_decision(payload: dict[str, Any]) -> LearningDeltaDecision:
    sections = _learning_delta_sections(payload)
    predicate_results = confirmed_predicate_results(sections.unlock)
    blocking_ids = confirmed_blocking_predicate_ids(
        predicate_results,
        summary=sections.summary,
    )
    confirmed_summary = confirmed_evidence_summary(
        _confirmed_summary_payload(payload, sections.unlock),
        blocking_predicate_ids=blocking_ids,
    )
    confirmed_status = improvement_claim_status(sections.summary)
    evidence_status = evidence_cohort_status(sections.summary, confirmed_summary)
    has_confirmed_predicates = bool(predicate_results)
    blocker_status = (
        str(
            sections.summary.get(
                "learning_claim_blocker_status",
                learning_claim_blocker_status(blocking_ids)
                if has_confirmed_predicates
                else "not_evaluated",
            )
        ).strip()
        or ("clear" if has_confirmed_predicates else "not_evaluated")
    )
    claim_level = str(sections.summary.get("claim_level", "none")).strip() or "none"
    bundle_status = learning_claim_bundle_status(sections.summary)
    wording_allowed = confirmed_wording_allowed(
        summary=sections.summary,
        claim_level=claim_level,
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        bundle_status=bundle_status,
        blocking_predicate_ids=blocking_ids,
    )
    claim_model = _learning_delta_claim_model(
        payload,
        sections,
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        claim_level=claim_level,
        bundle_status=bundle_status,
        blocking_predicate_ids=blocking_ids,
        learning_claim_blocker_status_value=blocker_status,
    )
    return LearningDeltaDecision(
        sections=sections,
        confirmed_predicate_results=predicate_results,
        confirmed_blocking_predicate_ids=blocking_ids,
        confirmed_summary=confirmed_summary,
        coverage=_learning_delta_coverage(sections.summary),
        confirmed_status=confirmed_status,
        evidence_cohort_status=evidence_status,
        learning_claim_blocker_status=blocker_status,
        claim_level=claim_level,
        bundle_status=bundle_status,
        confirmed_wording_allowed=wording_allowed,
        claim_model=claim_model,
        claim_wording_policy_status=str(
            sections.summary.get("claim_wording_policy_status", "")
        ).strip()
        or ("pre_seal_ready" if wording_allowed else "blocked"),
    )


def _loaded_learning_delta_guard_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    decision = _learning_delta_decision(payload)
    summary = decision.sections.summary
    guard = decision.sections.guard
    placeholder = decision.sections.placeholder_audit
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "status": str(guard.get("status", payload.get("status", "unknown"))).strip()
        or "unknown",
        "claims_learning_improved": bool(summary.get("claims_learning_improved")),
        "learning_claim_allowed": bool(summary.get("learning_claim_allowed")),
        "learning_likely": bool(
            summary.get("learning_likely", summary.get("claims_learning_improved"))
        ),
        "bounded_learning_claim_allowed": bool(
            summary.get("bounded_learning_claim_allowed")
        ),
        "confirmed_learning_improvement_allowed": bool(
            summary.get("confirmed_learning_improvement_allowed")
        ),
        "improvement_claim_status": decision.confirmed_status,
        "confirmed_learning_improvement_status": decision.confirmed_status,
        "evidence_cohort_status": decision.evidence_cohort_status,
        "learning_claim_blocker_status": decision.learning_claim_blocker_status,
        "confirmed_blocking_predicate_ids": decision.confirmed_blocking_predicate_ids,
        "confirmed_evidence_summary": decision.confirmed_summary,
        "confirmed_predicate_results": decision.confirmed_predicate_results,
        "claim_level": decision.claim_level,
        "claim_scope": str(summary.get("claim_scope", "")).strip(),
        "learning_claim_unlock_review_status": str(
            summary.get("learning_claim_unlock_review_status", "unknown")
        ).strip()
        or "unknown",
        "learning_claim_unlock_review_approved": bool(
            summary.get("learning_claim_unlock_review_approved")
        ),
        "learning_claim_unlock_review_revocation_status": str(
            summary.get(
                "learning_claim_unlock_review_revocation_status", "not_evaluated"
            )
        ).strip()
        or "not_evaluated",
        "learning_claim_evidence_bundle_status": decision.bundle_status,
        "claim_wording_allowed": decision.confirmed_wording_allowed,
        "claim_wording_policy_status": decision.claim_wording_policy_status,
        "confirmed_wording_allowed": decision.confirmed_wording_allowed,
        "confirmed_wording_policy_status": decision.claim_wording_policy_status,
        "self_improvement_claim_model": decision.claim_model,
        "learning_claim_unlock_review_source": str(
            decision.sections.unlock.get("source_path", "")
        ).strip(),
        "same_eval_run_count": int(summary.get("same_eval_run_count", 0) or 0),
        "telemetry_coverage_ratio": decision.coverage.telemetry_ratio,
        "telemetry_coverage_status": _summary_coverage_status(
            summary, "telemetry_coverage_status", "telemetry_coverage_ratio"
        ),
        "same_eval_reason_coverage_ratio": decision.coverage.reason_ratio,
        "same_eval_reason_coverage_status": _summary_coverage_status(
            summary,
            "same_eval_reason_coverage_status",
            "same_eval_reason_coverage_ratio",
        ),
        "strict_secondary_improvement_coverage_ratio": (
            decision.coverage.strict_secondary_ratio
        ),
        "strict_secondary_improvement_coverage_status": _summary_coverage_status(
            summary,
            "strict_secondary_improvement_coverage_status",
            "strict_secondary_improvement_coverage_ratio",
        ),
        "behavior_delta_digest_coverage_ratio": decision.coverage.digest_ratio,
        "behavior_delta_digest_coverage_status": _summary_coverage_status(
            summary,
            "behavior_delta_digest_coverage_status",
            "behavior_delta_digest_coverage_ratio",
        ),
        "placeholder_audit_status": str(
            placeholder.get("status", "unknown")
        ).strip()
        or "unknown",
        "placeholder_count": int(
            placeholder.get("placeholder_count", summary.get("placeholder_count", 0))
            or 0
        ),
        "reason": str(guard.get("reason", "")).strip()
        or "learning delta scoreboard guard status loaded",
    }


def learning_delta_guard_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    if load_status != "ok":
        return _missing_learning_delta_guard_summary(load_status)
    return _loaded_learning_delta_guard_summary(payload, load_status)


def _learning_claim_blocked_only_by_unlock_review(
    guard_summary: dict[str, Any],
) -> bool:
    if str(guard_summary.get("status", "")).strip() != "blocked":
        return False
    if not bool(guard_summary.get("claims_learning_improved")):
        return False
    if bool(guard_summary.get("learning_claim_allowed")):
        return False
    if (
        str(guard_summary.get("learning_claim_unlock_review_status", "")).strip()
        != "required"
    ):
        return False
    if bool(guard_summary.get("learning_claim_unlock_review_approved")):
        return False
    coverage_keys = (
        "telemetry_coverage_status",
        "same_eval_reason_coverage_status",
        "strict_secondary_improvement_coverage_status",
        "behavior_delta_digest_coverage_status",
    )
    if any(str(guard_summary.get(key, "")).strip() != "full" for key in coverage_keys):
        return False
    return str(guard_summary.get("placeholder_audit_status", "")).strip() == "pass"


def learning_delta_guard_gate(guard_summary: dict[str, Any]) -> dict[str, Any]:
    load_status = str(guard_summary.get("load_status", "unknown")).strip() or "unknown"
    guard_status = str(guard_summary.get("status", "unknown")).strip() or "unknown"
    claims_learning_improved = bool(guard_summary.get("claims_learning_improved"))
    learning_claim_allowed = bool(guard_summary.get("learning_claim_allowed"))
    reason = str(guard_summary.get("reason", "")).strip()
    if load_status != "ok":
        checked_in_state = "fail"
        next_action = (
            "Regenerate learning-delta-scoreboard before release dashboard signoff."
        )
        reason = reason or f"learning delta scoreboard load_status={load_status}"
    elif guard_status == "pass":
        checked_in_state = "pass"
        next_action = "none"
    elif _learning_claim_blocked_only_by_unlock_review(guard_summary):
        checked_in_state = "attention"
        next_action = (
            "Obtain learning-claim-unlock-review approval before claiming runtime learning improvement; "
            "source release evidence may proceed without the learning claim."
        )
    else:
        checked_in_state = "fail"
        next_action = "Resolve learning claim guard blockers before claiming runtime learning improvement."

    return {
        "gate_id": "learning_delta_scoreboard_guard",
        "source_path": LEARNING_DELTA_SCOREBOARD_PATH,
        "checked_in_state": checked_in_state,
        "live_rerun_state": {
            "status": checked_in_state,
            "reason": reason
            or f"learning_delta_scoreboard_guard status={guard_status}",
        },
        "authoritative_for_release": checked_in_state == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": (
                    "learning delta scoreboard guard is "
                    f"{guard_status}; claims_learning_improved={claims_learning_improved}; "
                    f"bounded_learning_claim_allowed={guard_summary.get('bounded_learning_claim_allowed')}; "
                    f"confirmed_learning_improvement_allowed="
                    f"{guard_summary.get('confirmed_learning_improvement_allowed')}; "
                    f"learning_claim_allowed={learning_claim_allowed}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "learning claim unlock review is "
                    f"{guard_summary.get('learning_claim_unlock_review_status')}; "
                    f"approved={guard_summary.get('learning_claim_unlock_review_approved')}; "
                    f"revocation={guard_summary.get('learning_claim_unlock_review_revocation_status')}; "
                    f"bundle={guard_summary.get('learning_claim_evidence_bundle_status')}; "
                    f"source={guard_summary.get('learning_claim_unlock_review_source') or 'none'}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "confirmed learning predicates are "
                    + (
                        ", ".join(
                            f"{item.get('id')}={item.get('status')}"
                            for item in guard_summary.get(
                                "confirmed_predicate_results", []
                            )
                            if isinstance(item, dict)
                        )
                        or "not_available"
                    )
                    + "; blocking="
                    + (
                        ",".join(
                            str(item)
                            for item in guard_summary.get(
                                "confirmed_blocking_predicate_ids", []
                            )
                            if str(item).strip()
                        )
                        or "none"
                    )
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
            {
                "claim": (
                    "same-eval evidence coverage is "
                    f"telemetry={guard_summary.get('telemetry_coverage_status')}, "
                    f"reason={guard_summary.get('same_eval_reason_coverage_status')}, "
                    f"strict_secondary={guard_summary.get('strict_secondary_improvement_coverage_status')}, "
                    f"digest={guard_summary.get('behavior_delta_digest_coverage_status')}"
                ),
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            },
        ],
    }
