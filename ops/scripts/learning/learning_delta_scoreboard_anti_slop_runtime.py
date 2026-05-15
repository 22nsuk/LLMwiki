from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AntiSlopScore:
    status: str
    score: int
    max_score: int
    placeholder_penalty: int
    evidence_coverage_penalty: int
    unsupported_claim_penalty: int
    claim_wording_penalty: int
    deduction_count: int
    deductions: list[dict[str, Any]]
    inputs: dict[str, Any]


def _deduction(deduction_id: str, points: int, reason: str) -> dict[str, Any]:
    return {"id": deduction_id, "points": points, "reason": reason}


def _coverage_status_penalty(status: str) -> int:
    if status in {"full", "not_applicable"}:
        return 0
    if status == "partial":
        return 5
    return 10


def _anti_slop_score(
    *,
    decision: Any,
    coverage: Any,
    placeholder_audit: dict[str, Any],
) -> AntiSlopScore:
    claims_learning_improved = decision.claims_learning_improved
    placeholder_status = str(placeholder_audit.get("status", "unknown")).strip() or "unknown"
    placeholder_count = int(placeholder_audit.get("placeholder_count", 0) or 0)
    deductions: list[dict[str, Any]] = []

    placeholder_penalty = min(40, placeholder_count * 20)
    if placeholder_penalty:
        deductions.append(
            _deduction(
                "external_report_placeholders",
                placeholder_penalty,
                "external reports still contain placeholder-shaped wording",
            )
        )
    elif placeholder_status != "pass":
        placeholder_penalty = 20
        deductions.append(
            _deduction(
                "external_report_placeholder_audit_not_clean",
                placeholder_penalty,
                f"external report placeholder audit status is {placeholder_status}",
            )
        )

    coverage_inputs = {
        "telemetry_coverage_status": coverage.telemetry["status"],
        "same_eval_reason_coverage_status": coverage.reason["status"],
        "strict_secondary_improvement_coverage_status": coverage.strict_secondary["status"],
        "behavior_delta_digest_coverage_status": coverage.digest["status"],
    }
    evidence_coverage_penalty = 0
    if claims_learning_improved:
        evidence_coverage_penalty = sum(
            _coverage_status_penalty(str(status)) for status in coverage_inputs.values()
        )
        if evidence_coverage_penalty:
            deductions.append(
                _deduction(
                    "learning_claim_evidence_coverage_not_full",
                    evidence_coverage_penalty,
                    "learning-improvement wording requires full same-eval coverage",
                )
            )

    unsupported_claim_penalty = (
        20
        if claims_learning_improved and not decision.learning_claim_evidence_complete
        else 0
    )
    if unsupported_claim_penalty:
        deductions.append(
            _deduction(
                "unsupported_learning_claim",
                unsupported_claim_penalty,
                "runtime learning claim is present before evidence is complete",
            )
        )

    claim_wording_penalty = (
        20 if claims_learning_improved and not decision.claim_wording_allowed else 0
    )
    if claim_wording_penalty:
        deductions.append(
            _deduction(
                "claim_wording_not_allowed",
                claim_wording_penalty,
                "claim wording is blocked by the learning claim model",
            )
        )

    max_score = 100
    score = max(
        0,
        max_score
        - placeholder_penalty
        - evidence_coverage_penalty
        - unsupported_claim_penalty
        - claim_wording_penalty,
    )
    if score == max_score:
        status = "clean"
    elif score >= 80:
        status = "attention"
    else:
        status = "blocked"

    inputs = {
        "claims_learning_improved": claims_learning_improved,
        "learning_claim_evidence_complete": decision.learning_claim_evidence_complete,
        "claim_wording_allowed": decision.claim_wording_allowed,
        "placeholder_audit_status": placeholder_status,
        "placeholder_count": placeholder_count,
        **coverage_inputs,
    }
    return AntiSlopScore(
        status=status,
        score=score,
        max_score=max_score,
        placeholder_penalty=placeholder_penalty,
        evidence_coverage_penalty=evidence_coverage_penalty,
        unsupported_claim_penalty=unsupported_claim_penalty,
        claim_wording_penalty=claim_wording_penalty,
        deduction_count=len(deductions),
        deductions=deductions,
        inputs=inputs,
    )


def _anti_slop_score_payload(score: AntiSlopScore) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": score.status,
        "score": score.score,
        "max_score": score.max_score,
        "placeholder_penalty": score.placeholder_penalty,
        "evidence_coverage_penalty": score.evidence_coverage_penalty,
        "unsupported_claim_penalty": score.unsupported_claim_penalty,
        "claim_wording_penalty": score.claim_wording_penalty,
        "deduction_count": score.deduction_count,
        "deductions": score.deductions,
        "inputs": score.inputs,
        "summary": (
            f"anti_slop_score={score.score}/{score.max_score}; "
            f"status={score.status}; deduction_count={score.deduction_count}"
        ),
    }

