from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.core.learning_claim_state_runtime import confirmed_evidence_summary
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext

from .learning_claim_model import (
    ImprovementClaimInputs,
    improvement_claim_model,
    learning_claim_blocker_status,
)
from .learning_delta_scoreboard_anti_slop_runtime import (
    _anti_slop_score,
    _anti_slop_score_payload,
)
from .learning_delta_scoreboard_constants import (
    DEFAULT_OUT,
    EVIDENCE_SCOPE_SPECS,
    LEARNING_CLAIM_UNLOCK_REVIEW_PATH,
    PRODUCER,
    SAME_EVAL_PROPOSAL_FAILURE_MODES,
    SAME_EVAL_REASON_CODES,
    SCHEMA_PATH,
    SCOREBOARD_SOURCE_PATHS,
    SOURCE_COMMAND,
)
from .learning_delta_scoreboard_unlock_runtime import (
    _learning_claim_unlock_review,
)
from .learning_readiness_vocabulary import learning_release_blocker_ids_from_report

PLACEHOLDER_RE = re.compile(r"\{(?:[A-Za-z_][A-Za-z0-9_]*\.get\([^{}\n]*\)|(?:ref|zip)_[^{}\n]*)\}")


@dataclass(frozen=True)
class ScoreboardCoverageSet:
    telemetry: dict[str, Any]
    reason: dict[str, Any]
    strict_secondary: dict[str, Any]
    digest: dict[str, Any]


@dataclass(frozen=True)
class LearningClaimDecision:
    claims_learning_improved: bool
    learning_claim_evidence_complete: bool
    unlock_review: dict[str, Any]
    learning_claim_allowed: bool
    bounded_learning_claim_allowed: bool
    confirmed_learning_improvement_allowed: bool
    confirmed_learning_improvement_status: str
    confirmed_blocking_predicate_ids: list[str]
    confirmed_evidence_summary: dict[str, Any]
    evidence_cohort_status: str
    improvement_claim_status: str
    learning_claim_blocker_status: str
    claim_level: str
    claim_scope: str
    guard_status: str
    status: str
    self_improvement_claim_model: dict[str, Any]
    claim_wording_allowed: bool
    claim_wording_policy_status: str


@dataclass(frozen=True)
class ScoreboardDecisionInputs:
    readiness: dict[str, Any]
    same_eval: dict[str, Any]
    placeholder_audit: dict[str, Any]
    coverage: ScoreboardCoverageSet
    claims_learning_improved: bool


@dataclass(frozen=True)
class ScoreboardRenderInputs:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    decision: LearningClaimDecision
    same_eval: dict[str, Any]
    placeholder_audit: dict[str, Any]
    coverage: ScoreboardCoverageSet
    aggregate_selector: dict[str, Any]
    evidence_scopes: list[dict[str, str]]
    input_paths: list[str]


def _latest_json(vault: Path, rel_dir: str) -> tuple[str, dict[str, Any]]:
    root = vault / rel_dir
    reports = []
    if root.is_dir():
        for path in root.glob("*.json"):
            payload = load_optional_json_object(path)
            if payload:
                reports.append((str(payload.get("generated_at", "")), report_path(vault, path), payload))
    if not reports:
        return "", {}
    _generated_at, rel_path, payload = sorted(reports)[-1]
    return rel_path, payload


def _telemetry_path_for_run(vault: Path, run_id: str) -> Path | None:
    candidates = [
        vault / "runs" / run_id / "run-telemetry.json",
        vault / "runs" / "archive" / run_id / "run-telemetry.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted((vault / "runs").glob(f"**/{run_id}/run-telemetry.json"))
    return matches[0] if matches else None


def _proposal_family(proposal: dict[str, Any]) -> str:
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    if failure_mode:
        return failure_mode
    expected_change = str(proposal.get("expected_change", "")).strip()
    if expected_change:
        return expected_change
    return "unknown"


def _same_eval_proposals(mutation_proposals: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        proposal
        for proposal in mutation_proposals.get("proposals", [])
        if isinstance(proposal, dict)
        and str(proposal.get("failure_mode", "")).strip() in SAME_EVAL_PROPOSAL_FAILURE_MODES
    ]


def _proposal_run_ids(mutation_proposals: dict[str, Any]) -> list[str]:
    run_ids: list[str] = []
    for proposal in _same_eval_proposals(mutation_proposals):
        for run_id in proposal.get("run_ids", []):
            value = str(run_id).strip()
            if value and value not in run_ids:
                run_ids.append(value)
    return run_ids


def _proposal_families(mutation_proposals: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for proposal in _same_eval_proposals(mutation_proposals):
        family = _proposal_family(proposal)
        if family not in families:
            families.append(family)
    return families


def _same_eval_evidence(vault: Path, mutation_proposals: dict[str, Any]) -> dict[str, Any]:
    proposal_count = sum(
        1
        for proposal in mutation_proposals.get("proposals", [])
        if isinstance(proposal, dict)
        and str(proposal.get("failure_mode", "")).strip() in SAME_EVAL_PROPOSAL_FAILURE_MODES
    )
    runs = []
    for run_id in _proposal_run_ids(mutation_proposals):
        telemetry_path = _telemetry_path_for_run(vault, run_id)
        telemetry = load_optional_json_object(telemetry_path) if telemetry_path else {}
        runs.append(
            {
                "run_id": run_id,
                "telemetry_path": report_path(vault, telemetry_path) if telemetry_path else "",
                "telemetry_present": bool(telemetry),
                "decision": str(telemetry.get("decision", "")),
                "same_eval_reason_present": bool(str(telemetry.get("same_eval_reason", "")).strip()),
                "same_eval_reason_code": _same_eval_reason_code(telemetry),
                "same_eval_reason_code_present": _same_eval_reason_code(telemetry) != "unknown",
                "strict_secondary_improvement_present": bool(
                    telemetry.get("strict_secondary_improvement_present", False)
                ),
                "secondary_improvement_axes": _string_list(telemetry.get("secondary_improvement_axes")),
                "behavior_delta_digest_present": bool(str(telemetry.get("behavior_delta_digest", "")).strip()),
            }
        )
    return {
        "proposal_count": proposal_count,
        "run_count": len(runs),
        "runs_with_telemetry": sum(1 for item in runs if item["telemetry_present"]),
        "runs": runs,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _same_eval_reason_code(telemetry: dict[str, Any]) -> str:
    value = str(telemetry.get("same_eval_reason_code", "")).strip()
    return value if value in SAME_EVAL_REASON_CODES else "unknown"


def _coverage(numerator: int, denominator: int, *, empty_status: str = "no_evidence") -> dict[str, Any]:
    if denominator <= 0:
        return {
            "numerator": 0,
            "denominator": 0,
            "ratio": 0.0,
            "status": empty_status,
        }
    ratio = round(numerator / denominator, 4)
    if numerator == denominator:
        status = "full"
    elif numerator > 0:
        status = "partial"
    else:
        status = "none"
    return {
        "numerator": numerator,
        "denominator": denominator,
        "ratio": ratio,
        "status": status,
    }


def _coverage_pass(coverage: dict[str, Any]) -> bool:
    return coverage.get("status") == "full"


def _learning_readiness_signal_ids(readiness: dict[str, Any]) -> list[str]:
    signals = readiness.get("learning_readiness", {}).get("signals", [])
    if not isinstance(signals, list):
        return []
    return [
        str(signal.get("id", "")).strip()
        for signal in signals
        if isinstance(signal, dict) and str(signal.get("id", "")).strip()
    ]


def _learning_readiness_blocker_ids(readiness: dict[str, Any]) -> list[str]:
    return learning_release_blocker_ids_from_report(readiness)


def _latest_session_coverage(vault: Path, routing_path: str, routing_aggregate: dict[str, Any]) -> dict[str, Any]:
    if not routing_path or not routing_aggregate:
        return {
            "status": "no_evidence",
            "source_path": "",
            "telemetry_coverage_ratio": 0.0,
            "session_id": "",
            "summary": "no routing provenance aggregate is available",
        }
    audit_rollup = routing_aggregate.get("audit_rollup")
    loop_health = audit_rollup.get("loop_health") if isinstance(audit_rollup, dict) else {}
    coverage_ratios = loop_health.get("coverage_ratios") if isinstance(loop_health, dict) else {}
    telemetry = coverage_ratios.get("telemetry", 0.0) if isinstance(coverage_ratios, dict) else 0.0
    try:
        ratio = round(float(telemetry), 4)
    except (TypeError, ValueError):
        ratio = 0.0
    return {
        "status": "available",
        "source_path": routing_path,
        "telemetry_coverage_ratio": ratio,
        "session_id": str(routing_aggregate.get("session_id", "")).strip(),
        "summary": "latest routing provenance aggregate selected by generated_at",
    }


def _aggregate_selector(
    vault: Path,
    *,
    routing_path: str,
    routing_aggregate: dict[str, Any],
    same_eval: dict[str, Any],
    telemetry_coverage: dict[str, Any],
    mutation_proposals: dict[str, Any],
) -> dict[str, Any]:
    families = _proposal_families(mutation_proposals)
    latest = _latest_session_coverage(vault, routing_path, routing_aggregate)
    proposal_family = {
        "status": telemetry_coverage["status"],
        "source_path": "ops/reports/mutation-proposals.json",
        "proposal_families": families,
        "proposal_count": same_eval["proposal_count"],
        "run_count": same_eval["run_count"],
        "telemetry_coverage_ratio": telemetry_coverage["ratio"],
        "summary": "coverage is computed only from repeated same-eval/discard proposal run_ids",
    }
    historical = {
        "status": telemetry_coverage["status"],
        "source_path": "runs/**/run-telemetry.json",
        "run_count": same_eval["run_count"],
        "runs_with_telemetry": same_eval["runs_with_telemetry"],
        "telemetry_coverage_ratio": telemetry_coverage["ratio"],
        "summary": "telemetry was resolved from active and archived run directories for the proposal run_ids",
    }
    effective = {
        "status": telemetry_coverage["status"],
        "selected_source": "proposal_family_coverage",
        "telemetry_coverage_ratio": telemetry_coverage["ratio"],
        "summary": "release learning claims use proposal-family coverage, not the latest aggregate alone",
    }
    return {
        "latest_session_coverage": latest,
        "proposal_family_coverage": proposal_family,
        "historical_recoverable_coverage": historical,
        "effective_learning_coverage": effective,
    }


def _external_report_placeholder_audit(vault: Path) -> dict[str, Any]:
    placeholders = []
    root = vault / "external-reports"
    if root.is_dir():
        for path in sorted(root.glob("*.md")):
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if PLACEHOLDER_RE.search(line):
                    placeholders.append(
                        {
                            "path": report_path(vault, path),
                            "line": index,
                            "text": line.strip(),
                        }
                    )
    return {
        "status": "pass" if not placeholders else "fail",
        "placeholder_count": len(placeholders),
        "placeholders": placeholders,
    }


def _claims_learning_improved(readiness: dict[str, Any]) -> bool:
    return (
        readiness.get("can_promote_result") is True
        and readiness.get("learning_readiness", {}).get("likely_to_learn") is True
    )


def _scoreboard_coverage_set(
    same_eval: dict[str, Any],
    *,
    claims_learning_improved: bool,
) -> ScoreboardCoverageSet:
    run_count = same_eval["run_count"]
    empty_status = "no_evidence" if claims_learning_improved else "not_applicable"
    return ScoreboardCoverageSet(
        telemetry=_coverage(
            same_eval["runs_with_telemetry"],
            run_count,
            empty_status=empty_status,
        ),
        reason=_coverage(
            sum(1 for item in same_eval["runs"] if item["same_eval_reason_code_present"]),
            run_count,
            empty_status=empty_status,
        ),
        strict_secondary=_coverage(
            sum(1 for item in same_eval["runs"] if item["strict_secondary_improvement_present"]),
            run_count,
            empty_status=empty_status,
        ),
        digest=_coverage(
            sum(1 for item in same_eval["runs"] if item["behavior_delta_digest_present"]),
            run_count,
            empty_status=empty_status,
        ),
    )


def _learning_claim_evidence_complete(
    *,
    coverage: ScoreboardCoverageSet,
    placeholder_audit: dict[str, Any],
) -> bool:
    return (
        _coverage_pass(coverage.telemetry)
        and _coverage_pass(coverage.reason)
        and _coverage_pass(coverage.strict_secondary)
        and _coverage_pass(coverage.digest)
        and placeholder_audit["status"] == "pass"
    )


def _claim_level_for_scoreboard(
    *,
    claims_learning_improved: bool,
    bounded_learning_claim_allowed: bool,
    confirmed_learning_improvement_allowed: bool,
) -> str:
    if confirmed_learning_improvement_allowed:
        return "confirmed_learning_improvement"
    if bounded_learning_claim_allowed:
        return "bounded_learning_likely"
    if claims_learning_improved:
        return "learning_likely"
    return "none"


def _learning_claim_decision(
    vault: Path,
    *,
    readiness: dict[str, Any],
    same_eval: dict[str, Any],
    placeholder_audit: dict[str, Any],
    coverage: ScoreboardCoverageSet,
    claims_learning_improved: bool,
) -> LearningClaimDecision:
    evidence_complete = _learning_claim_evidence_complete(
        coverage=coverage,
        placeholder_audit=placeholder_audit,
    )
    unlock_review = _learning_claim_unlock_review(
        vault,
        evidence_complete,
        readiness_signal_ids=_learning_readiness_signal_ids(readiness),
        readiness_blocker_ids=_learning_readiness_blocker_ids(readiness),
    )
    learning_claim_allowed = (
        claims_learning_improved
        and evidence_complete
        and unlock_review["approved"]
        and unlock_review["status"] in {"approved", "auto_approved"}
    )
    bounded_allowed = learning_claim_allowed and bool(
        unlock_review.get("bounded_learning_claim_allowed", learning_claim_allowed)
    )
    confirmed_allowed = learning_claim_allowed and bool(
        unlock_review.get("confirmed_learning_improvement_allowed")
    )
    confirmed_status = str(
        unlock_review.get("confirmed_learning_improvement_status", "not_ready")
    ).strip() or "not_ready"
    blocking_predicate_ids = [
        str(item).strip()
        for item in unlock_review.get("confirmed_blocking_predicate_ids", [])
        if str(item).strip()
    ]
    confirmed_summary = confirmed_evidence_summary(
        unlock_review.get("confirmed_evidence_summary"),
        blocking_predicate_ids=blocking_predicate_ids,
    )
    evidence_cohort_status = str(
        confirmed_summary.get("evidence_cohort_status", "not_ready")
    ).strip() or "not_ready"
    blocker_status = (
        str(
            unlock_review.get(
                "learning_claim_blocker_status",
                learning_claim_blocker_status(blocking_predicate_ids)
                if unlock_review.get("confirmed_predicate_results")
                else "not_evaluated",
            )
        ).strip()
        or "not_evaluated"
    )
    claim_level = _claim_level_for_scoreboard(
        claims_learning_improved=claims_learning_improved,
        bounded_learning_claim_allowed=bounded_allowed,
        confirmed_learning_improvement_allowed=confirmed_allowed,
    )
    claim_scope = str(unlock_review.get("claim_scope", "")).strip()
    if bounded_allowed and not claim_scope:
        claim_scope = "sealed_evidence_bundle"
    guard_status = "pass" if (not claims_learning_improved or learning_claim_allowed) else "blocked"
    status = "pass" if guard_status == "pass" and placeholder_audit["status"] == "pass" else "attention"
    claim_model = improvement_claim_model(
        ImprovementClaimInputs(
            guard_status=guard_status,
            claims_learning_improved=claims_learning_improved,
            learning_claim_evidence_complete=evidence_complete,
            bounded_learning_claim_allowed=bounded_allowed,
            confirmed_learning_improvement_allowed=confirmed_allowed,
            improvement_claim_status=confirmed_status,
            evidence_cohort_status=evidence_cohort_status,
            claim_level=claim_level,
            bundle_status=str(unlock_review["bundle_status"]),
            blocking_predicate_ids=blocking_predicate_ids,
            learning_claim_blocker_status=blocker_status,
            same_eval_run_count=same_eval["run_count"],
            same_eval_reason_coverage_status=coverage.reason["status"],
            strict_secondary_improvement_coverage_status=coverage.strict_secondary["status"],
            behavior_delta_digest_coverage_status=coverage.digest["status"],
        )
    )
    return LearningClaimDecision(
        claims_learning_improved=claims_learning_improved,
        learning_claim_evidence_complete=evidence_complete,
        unlock_review=unlock_review,
        learning_claim_allowed=learning_claim_allowed,
        bounded_learning_claim_allowed=bounded_allowed,
        confirmed_learning_improvement_allowed=confirmed_allowed,
        confirmed_learning_improvement_status=confirmed_status,
        confirmed_blocking_predicate_ids=blocking_predicate_ids,
        confirmed_evidence_summary=confirmed_summary,
        evidence_cohort_status=evidence_cohort_status,
        improvement_claim_status=confirmed_status,
        learning_claim_blocker_status=blocker_status,
        claim_level=claim_level,
        claim_scope=claim_scope,
        guard_status=guard_status,
        status=status,
        self_improvement_claim_model=claim_model,
        claim_wording_allowed=bool(claim_model["claim_wording_allowed"]),
        claim_wording_policy_status=str(claim_model["claim_wording_policy_status"]),
    )


def _learning_delta_summary(
    *,
    decision: LearningClaimDecision,
    same_eval: dict[str, Any],
    coverage: ScoreboardCoverageSet,
    placeholder_audit: dict[str, Any],
    anti_slop_score: dict[str, Any],
    evidence_scopes: list[dict[str, str]],
) -> dict[str, Any]:
    unlock_review = decision.unlock_review
    return {
        "claims_learning_improved": decision.claims_learning_improved,
        "learning_claim_allowed": decision.learning_claim_allowed,
        "learning_likely": decision.claims_learning_improved,
        "bounded_learning_claim_allowed": decision.bounded_learning_claim_allowed,
        "confirmed_learning_improvement_allowed": decision.confirmed_learning_improvement_allowed,
        "improvement_claim_status": decision.improvement_claim_status,
        "confirmed_learning_improvement_status": decision.confirmed_learning_improvement_status,
        "evidence_cohort_status": decision.evidence_cohort_status,
        "learning_claim_blocker_status": decision.learning_claim_blocker_status,
        "confirmed_blocking_predicate_ids": decision.confirmed_blocking_predicate_ids,
        "confirmed_evidence_summary": decision.confirmed_evidence_summary,
        "claim_wording_allowed": decision.claim_wording_allowed,
        "claim_wording_policy_status": decision.claim_wording_policy_status,
        "self_improvement_claim_model": decision.self_improvement_claim_model,
        "claim_vocabulary_version": 1,
        "claim_level": decision.claim_level,
        "claim_scope": decision.claim_scope,
        "learning_claim_evidence_complete": decision.learning_claim_evidence_complete,
        "learning_claim_unlock_review_status": unlock_review["status"],
        "learning_claim_unlock_review_approved": unlock_review["approved"],
        "learning_claim_unlock_review_revocation_status": unlock_review["revocation_status"],
        "learning_claim_evidence_bundle_status": unlock_review["bundle_status"],
        "learning_claim_evidence_bundle_sha256": unlock_review["bundle_sha256"],
        "learning_confirmed_evidence_cohort_sha256": unlock_review["confirmed_evidence_cohort_sha256"],
        "learning_confirmed_evidence_cohort_status": unlock_review["confirmed_evidence_cohort_status"],
        "telemetry_coverage_ratio": coverage.telemetry["ratio"],
        "telemetry_coverage_status": coverage.telemetry["status"],
        "same_eval_run_count": same_eval["run_count"],
        "same_eval_reason_coverage_ratio": coverage.reason["ratio"],
        "same_eval_reason_coverage_status": coverage.reason["status"],
        "strict_secondary_improvement_coverage_ratio": coverage.strict_secondary["ratio"],
        "strict_secondary_improvement_coverage_status": coverage.strict_secondary["status"],
        "behavior_delta_digest_coverage_ratio": coverage.digest["ratio"],
        "behavior_delta_digest_coverage_status": coverage.digest["status"],
        "placeholder_count": placeholder_audit["placeholder_count"],
        "anti_slop_status": anti_slop_score["status"],
        "anti_slop_score": anti_slop_score["score"],
        "anti_slop_deduction_count": anti_slop_score["deduction_count"],
        "evidence_scope_count": len(evidence_scopes),
    }


def _learning_claim_guard(decision: LearningClaimDecision) -> dict[str, Any]:
    return {
        "status": decision.guard_status,
        "improvement_claim_status": decision.improvement_claim_status,
        "evidence_cohort_status": decision.evidence_cohort_status,
        "learning_claim_blocker_status": decision.learning_claim_blocker_status,
        "claim_wording_allowed": decision.claim_wording_allowed,
        "claim_wording_policy_status": decision.claim_wording_policy_status,
        "reason": (
            "bounded learning-likely claims require full same-eval reason/digest coverage, "
            "placeholder-free external reports, an active evidence bundle, and explicit unlock review; "
            "confirmed learning-improvement claims require the stricter confirmed-improvement lane"
        ),
        "required_conditions": [
            "telemetry_coverage_ratio == 1.0",
            "same_eval_reason_coverage_status == full",
            "strict_secondary_improvement_coverage_status == full",
            "behavior_delta_digest_coverage_ratio == 1.0",
            "external_report_placeholder_audit.status == pass",
            "learning_claim_unlock_review.status in [approved, auto_approved]",
            "learning_claim_unlock_review.revocation_status in [active, not_evaluated]",
        ],
    }


def _scoreboard_evidence_scopes(routing_path: str) -> list[dict[str, str]]:
    evidence_scopes = [
        {"scope": scope, "path": path, "authority": authority}
        for scope, path, authority in EVIDENCE_SCOPE_SPECS
    ]
    if routing_path:
        evidence_scopes.append(
            {"scope": "learning_loop", "path": routing_path, "authority": "diagnostic"}
        )
    return evidence_scopes


def _scoreboard_input_paths(routing_path: str) -> list[str]:
    return [
        "ops/reports/auto-improve-readiness.json",
        "ops/reports/outcome-metrics.json",
        "ops/reports/mutation-proposals.json",
        LEARNING_CLAIM_UNLOCK_REVIEW_PATH,
        *([routing_path] if routing_path else []),
        *[scope[1] for scope in EVIDENCE_SCOPE_SPECS],
    ]


def _scoreboard_decision_inputs(vault: Path) -> tuple[ScoreboardDecisionInputs, dict[str, Any], str]:
    readiness = load_optional_json_object(vault / "ops/reports/auto-improve-readiness.json")
    mutation_proposals = load_optional_json_object(vault / "ops/reports/mutation-proposals.json")
    routing_path, routing_aggregate = _latest_json(vault, "ops/reports/routing-provenance-aggregates")
    same_eval = _same_eval_evidence(vault, mutation_proposals)
    placeholder_audit = _external_report_placeholder_audit(vault)
    claims_learning_improved = _claims_learning_improved(readiness)
    coverage = _scoreboard_coverage_set(
        same_eval,
        claims_learning_improved=claims_learning_improved,
    )
    aggregate_selector = _aggregate_selector(
        vault,
        routing_path=routing_path,
        routing_aggregate=routing_aggregate,
        same_eval=same_eval,
        telemetry_coverage=coverage.telemetry,
        mutation_proposals=mutation_proposals,
    )
    return (
        ScoreboardDecisionInputs(
            readiness=readiness,
            same_eval=same_eval,
            placeholder_audit=placeholder_audit,
            coverage=coverage,
            claims_learning_improved=claims_learning_improved,
        ),
        aggregate_selector,
        routing_path,
    )


def _render_scoreboard_report(inputs: ScoreboardRenderInputs) -> dict[str, Any]:
    anti_slop_score = _anti_slop_score_payload(
        _anti_slop_score(
            decision=inputs.decision,
            coverage=inputs.coverage,
            placeholder_audit=inputs.placeholder_audit,
        )
    )
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.runtime_context.isoformat_z(),
            artifact_kind="learning_delta_scoreboard",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=SCOREBOARD_SOURCE_PATHS,
            path_group_inputs={"learning_delta_inputs": inputs.input_paths},
        ),
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": inputs.decision.status,
        "summary": _learning_delta_summary(
            decision=inputs.decision,
            same_eval=inputs.same_eval,
            coverage=inputs.coverage,
            placeholder_audit=inputs.placeholder_audit,
            anti_slop_score=anti_slop_score,
            evidence_scopes=inputs.evidence_scopes,
        ),
        "learning_claim_guard": _learning_claim_guard(inputs.decision),
        "learning_claim_unlock_review": inputs.decision.unlock_review,
        "self_improvement_claim_model": inputs.decision.self_improvement_claim_model,
        "confirmed_evidence_summary": inputs.decision.confirmed_evidence_summary,
        "same_eval_evidence": inputs.same_eval,
        "coverage": {
            "telemetry": inputs.coverage.telemetry,
            "same_eval_reason_code": inputs.coverage.reason,
            "strict_secondary_improvement": inputs.coverage.strict_secondary,
            "behavior_delta_digest": inputs.coverage.digest,
        },
        "aggregate_selector": inputs.aggregate_selector,
        "evidence_scopes": inputs.evidence_scopes,
        "external_report_placeholder_audit": inputs.placeholder_audit,
        "anti_slop_score": anti_slop_score,
    }


def build_report(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    decision_inputs, aggregate_selector, routing_path = _scoreboard_decision_inputs(vault)
    decision = _learning_claim_decision(
        vault,
        readiness=decision_inputs.readiness,
        same_eval=decision_inputs.same_eval,
        placeholder_audit=decision_inputs.placeholder_audit,
        coverage=decision_inputs.coverage,
        claims_learning_improved=decision_inputs.claims_learning_improved,
    )
    input_paths = _scoreboard_input_paths(routing_path)
    evidence_scopes = _scoreboard_evidence_scopes(routing_path)
    return _render_scoreboard_report(
        ScoreboardRenderInputs(
            vault=vault,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            runtime_context=runtime_context,
            decision=decision,
            same_eval=decision_inputs.same_eval,
            placeholder_audit=decision_inputs.placeholder_audit,
            coverage=decision_inputs.coverage,
            aggregate_selector=aggregate_selector,
            evidence_scopes=evidence_scopes,
            input_paths=input_paths,
        )
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning delta scoreboard schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning delta scoreboard")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, out_path=args.out)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
