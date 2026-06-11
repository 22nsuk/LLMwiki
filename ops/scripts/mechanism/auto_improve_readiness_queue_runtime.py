from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object
from ops.scripts.core.payload_field_runtime import dict_field
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_NONE,
)
from ops.scripts.policy_runtime import report_path

from .auto_improve_queue_runtime import build_proposal_queue
from .auto_improve_readiness_constants_runtime import (
    AUTO_IMPROVE_GOAL_RUN_COMMAND,
    FALLBACK_PRIMARY_TARGETS,
    FALLBACK_SUPPORTING_TARGETS,
    FALLBACK_TEST_FILES,
    LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH,
    READINESS_TARGET,
    RECENT_LOG_OVERLAP_REMEDIATION,
    RECENT_OUTCOME_REWORK_REMEDIATION,
    SAME_EVAL_PROPOSAL_FAILURE_MODES,
)
from .auto_improve_readiness_learning_runtime import _build_loop_health_summary


@dataclass(frozen=True)
class ReadinessRemediation:
    blocker: str
    remediation_code: str
    blocker_kind: str
    unblock_action_type: str
    minimum_evidence: list[str]
    retry_condition: str
    affected_proposal_count: int
    proposal_ids: list[str]

    def to_wire(self) -> dict[str, Any]:
        return {
            "blocker": self.blocker,
            "remediation_code": self.remediation_code,
            "blocker_kind": self.blocker_kind,
            "unblock_action_type": self.unblock_action_type,
            "minimum_evidence": self.minimum_evidence,
            "retry_condition": self.retry_condition,
            "affected_proposal_count": self.affected_proposal_count,
            "proposal_ids": self.proposal_ids,
        }


@dataclass(frozen=True)
class ReadinessQueue:
    ready: bool
    proposals_emitted: int
    runnable_proposal_count: int
    runnable_proposal_ids: list[str]
    blocked_proposal_count: int
    blocked_reason_counts: list[dict[str, Any]]
    source_candidates_read: int
    candidates_emitted: int
    attempts_considered: int
    session_reports_considered: int
    queue_pressure_summary: str
    review_bootstrap_summary: str
    evidence_gaps: list[str]

    def to_wire(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "proposals_emitted": self.proposals_emitted,
            "runnable_proposal_count": self.runnable_proposal_count,
            "runnable_proposal_ids": self.runnable_proposal_ids,
            "blocked_proposal_count": self.blocked_proposal_count,
            "blocked_reason_counts": self.blocked_reason_counts,
            "source_candidates_read": self.source_candidates_read,
            "candidates_emitted": self.candidates_emitted,
            "attempts_considered": self.attempts_considered,
            "session_reports_considered": self.session_reports_considered,
            "queue_pressure_summary": self.queue_pressure_summary,
            "review_bootstrap_summary": self.review_bootstrap_summary,
            "evidence_gaps": self.evidence_gaps,
        }


@dataclass(frozen=True)
class ReadinessQueueState:
    outcome_summary: dict[str, Any]
    review_summary: dict[str, Any]
    proposal_summary: dict[str, Any]
    proposal_diagnostics: dict[str, Any]
    loop_health_summary: dict[str, Any]
    same_eval_telemetry_summary: dict[str, Any]
    queue_evidence_gaps: list[str]
    proposals_emitted: int
    runnable_proposal_ids: list[str]
    blocked_proposal_count: int
    blocked_reason_counts: dict[str, int]
    blocked_proposal_ids: dict[str, list[str]]
    blocked_reasons: list[str]
    queue_ready: bool
    seed_runs: list[str]
    history_requirement: int
    additional_runs_needed: int


@dataclass(frozen=True)
class ReadinessExecutionFields:
    status: str
    gate_effect: str
    can_run: bool
    reasons: list[str]
    runnable_proposal_count: int
    blocked_proposal_count: int
    recommended_next_step: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gate_effect": self.gate_effect,
            "can_run": self.can_run,
            "reasons": self.reasons,
            "runnable_proposal_count": self.runnable_proposal_count,
            "blocked_proposal_count": self.blocked_proposal_count,
            "recommended_next_step": self.recommended_next_step,
        }


@dataclass(frozen=True)
class ReadinessQueuePayloads:
    queue: ReadinessQueue
    fallback: dict[str, Any]
    checks: list[dict[str, Any]]
    remediations: list[dict[str, Any]]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _upstream_attention_summaries(
    *,
    review_report: dict[str, Any],
    proposal_report: dict[str, Any],
    review_summary: dict[str, Any],
    proposal_summary: dict[str, Any],
) -> list[str]:
    summaries: list[str] = []

    review_status = str(review_report.get("status", "")).strip()
    review_bootstrap = review_report.get("diagnostics", {}).get("bootstrap", {})
    if review_status == "attention":
        bootstrap_status = str(review_bootstrap.get("status", "")).strip()
        candidates_emitted = int(review_summary.get("candidates_emitted", 0) or 0)
        detail = bootstrap_status or "attention"
        summaries.append(
            f"mechanism_review.status=attention ({detail}; candidates_emitted={candidates_emitted})"
        )

    proposal_status = str(proposal_report.get("status", "")).strip()
    if proposal_status == "attention":
        proposals_emitted = int(proposal_summary.get("proposals_emitted", 0) or 0)
        queue_pressure_summary = str(
            proposal_summary.get("queue_pressure_summary", "")
        ).strip()
        detail = queue_pressure_summary or "attention"
        summaries.append(
            f"mutation_proposal.status=attention ({detail}; proposals_emitted={proposals_emitted})"
        )

    return summaries


def _runnable_proposal_ids(mutation_proposal_report: dict[str, Any]) -> list[str]:
    proposals = mutation_proposal_report.get("proposals")
    if not isinstance(proposals, list):
        return []
    try:
        runnable = build_proposal_queue(
            mutation_proposal_report,
            attempted=set(),
            quarantined=set(),
        )
    except (KeyError, TypeError):
        return []
    return [
        str(proposal.get("proposal_id", "")).strip()
        for proposal in runnable
        if proposal
    ]


def _blocked_reason_counts(mutation_proposal_report: dict[str, Any]) -> dict[str, int]:
    proposals = mutation_proposal_report.get("proposals")
    counts: dict[str, int] = {}
    proposal_counts: dict[str, int] = {}
    diagnostics = mutation_proposal_report.get("diagnostics")
    queue_selection = (
        diagnostics.get("queue_selection") if isinstance(diagnostics, dict) else {}
    )
    if isinstance(queue_selection, dict):
        for item in queue_selection.get("blocked_reason_counts", []):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason", "")).strip()
            if reason:
                counts[reason] = max(
                    counts.get(reason, 0), int(item.get("count", 0) or 0)
                )
    if isinstance(proposals, list):
        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            for reason in _string_list(proposal.get("blocked_by")):
                proposal_counts[reason] = proposal_counts.get(reason, 0) + 1
    empty_queue_blockers = (
        diagnostics.get("empty_queue_blockers") if isinstance(diagnostics, dict) else []
    )
    if isinstance(empty_queue_blockers, list):
        for blocker in empty_queue_blockers:
            if not isinstance(blocker, dict):
                continue
            reason = str(blocker.get("reason", "")).strip()
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
    for reason, proposal_count in proposal_counts.items():
        counts[reason] = max(counts.get(reason, 0), proposal_count)
    return counts


def _blocked_proposal_ids_by_reason(
    mutation_proposal_report: dict[str, Any],
) -> dict[str, list[str]]:
    proposals = mutation_proposal_report.get("proposals")
    proposal_ids_by_reason: dict[str, list[str]] = {}
    if not isinstance(proposals, list):
        return proposal_ids_by_reason
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        proposal_id = str(proposal.get("proposal_id", "")).strip()
        for reason in _string_list(proposal.get("blocked_by")):
            proposal_ids_by_reason.setdefault(reason, [])
            if proposal_id:
                proposal_ids_by_reason[reason].append(proposal_id)
    return proposal_ids_by_reason


def _blocked_reasons(mutation_proposal_report: dict[str, Any]) -> list[str]:
    return list(_blocked_reason_counts(mutation_proposal_report))


def _blocked_reason_count_items(
    blocked_reason_counts: dict[str, int],
) -> list[dict[str, Any]]:
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(blocked_reason_counts.items())
    ]


def _blocked_proposal_count(
    proposal_summary: dict[str, Any],
    proposal_diagnostics: dict[str, Any],
) -> int:
    queue_selection = proposal_diagnostics.get("queue_selection")
    if isinstance(queue_selection, dict):
        blocked_available = queue_selection.get("blocked_available_count")
        if isinstance(blocked_available, int) and blocked_available > 0:
            return blocked_available
    empty_queue_blockers = proposal_diagnostics.get("empty_queue_blockers")
    if isinstance(empty_queue_blockers, list) and empty_queue_blockers:
        return max(
            int(proposal_summary.get("blocked_proposals", 0) or 0),
            len(empty_queue_blockers),
        )
    return int(
        proposal_summary.get("blocked_proposals", 0)
        or proposal_summary.get("blocked_proposal_count", 0)
        or 0
    )


def _queue_evidence_gaps(
    *,
    review_report: dict[str, Any],
    proposal_report: dict[str, Any],
    review_summary: dict[str, Any],
    proposal_summary: dict[str, Any],
    proposal_diagnostics: dict[str, Any],
    proposals_emitted: int,
    queue_ready: bool,
    blocked_reasons: list[str],
) -> list[str]:
    evidence_gaps = [
        *_upstream_attention_summaries(
            review_report=review_report,
            proposal_report=proposal_report,
            review_summary=review_summary,
            proposal_summary=proposal_summary,
        ),
        *_string_list(proposal_diagnostics.get("evidence_gaps", [])),
    ]
    if proposals_emitted <= 0 or queue_ready:
        return evidence_gaps
    blocked_detail = (
        f"proposal blockers active: {', '.join(blocked_reasons)}"
        if blocked_reasons
        else "all emitted proposals are currently blocked"
    )
    return [*evidence_gaps, blocked_detail]


def _proposal_blocker_remediation(
    reason: str,
    *,
    blocked_count: int,
    proposal_ids: list[str],
) -> dict[str, Any]:
    if reason == "recent_log_overlap":
        payload = dict(RECENT_LOG_OVERLAP_REMEDIATION)
    elif reason == "recent_outcome_rework":
        payload = dict(RECENT_OUTCOME_REWORK_REMEDIATION)
    else:
        blocker_source = (
            "blocked_by for every emitted proposal"
            if proposal_ids
            else "diagnostics.empty_queue_blockers"
        )
        payload = {
            "remediation_code": "clear_mutation_proposal_blocker",
            "blocker_kind": "hard",
            "unblock_action_type": "manual_blocker_triage",
            "minimum_evidence": [
                f"A refreshed mutation proposal report no longer lists {reason} in {blocker_source}.",
                "auto-improve readiness reports queue.runnable_proposal_count greater than 0.",
            ],
            "retry_condition": (
                "Rerun make auto-improve-readiness after the blocking condition clears and "
                "make refresh-generated-core updates mutation-proposals.json."
            ),
        }
    return ReadinessRemediation(
        blocker=reason,
        affected_proposal_count=blocked_count,
        proposal_ids=proposal_ids,
        remediation_code=str(payload["remediation_code"]),
        blocker_kind=str(payload["blocker_kind"]),
        unblock_action_type=str(payload["unblock_action_type"]),
        minimum_evidence=list(payload["minimum_evidence"]),
        retry_condition=str(payload["retry_condition"]),
    ).to_wire()


def _fallback_remediation(
    *,
    blocker: str,
    remediation_code: str,
    unblock_action_type: str,
    minimum_evidence: list[str],
    retry_condition: str,
) -> dict[str, Any]:
    return ReadinessRemediation(
        blocker=blocker,
        remediation_code=remediation_code,
        blocker_kind="history_gap",
        unblock_action_type=unblock_action_type,
        minimum_evidence=minimum_evidence,
        retry_condition=retry_condition,
        affected_proposal_count=0,
        proposal_ids=[],
    ).to_wire()


def _readiness_remediations(
    *,
    reports_present: bool,
    proposals_emitted: int,
    runnable_proposal_count: int,
    blocked_reason_counts: dict[str, int],
    blocked_proposal_ids: dict[str, list[str]],
    seed_runs: list[str],
    history_requirement: int,
) -> list[dict[str, Any]]:
    remediations: list[dict[str, Any]] = []
    if not reports_present:
        remediations.append(
            ReadinessRemediation(
                blocker="generated_reports_missing",
                remediation_code="refresh_generated_reports",
                blocker_kind="input_gap",
                unblock_action_type="refresh_generated_reports",
                minimum_evidence=[
                    "ops/reports/outcome-metrics.json exists and has a summary object.",
                    "ops/reports/mechanism-review-candidates.json exists and has a summary object.",
                    "ops/reports/mutation-proposals.json exists and has a summary object.",
                ],
                retry_condition="Run make refresh-generated-core, then rerun make auto-improve-readiness.",
                affected_proposal_count=0,
                proposal_ids=[],
            ).to_wire()
        )
    if proposals_emitted > 0 and runnable_proposal_count == 0:
        if blocked_reason_counts:
            for reason, count in blocked_reason_counts.items():
                remediations.append(
                    _proposal_blocker_remediation(
                        reason,
                        blocked_count=count,
                        proposal_ids=blocked_proposal_ids.get(reason, []),
                    )
                )
        else:
            remediations.append(
                _proposal_blocker_remediation(
                    "all_emitted_proposals_blocked",
                    blocked_count=proposals_emitted,
                    proposal_ids=[],
                )
            )
    elif proposals_emitted == 0:
        if blocked_reason_counts:
            for reason, count in blocked_reason_counts.items():
                remediations.append(
                    _proposal_blocker_remediation(
                        reason,
                        blocked_count=count,
                        proposal_ids=blocked_proposal_ids.get(reason, []),
                    )
                )
        elif not seed_runs:
            remediations.append(
                _fallback_remediation(
                    blocker="fallback_target_history_missing",
                    remediation_code="seed_fallback_target_family",
                    unblock_action_type="manual_seed_run",
                    minimum_evidence=[
                        "One finalized system_mechanism run exists for ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py.",
                        "The seed run includes tests/test_auto_improve_iteration_runtime.py as evidence.",
                        "make auto-improve-readiness reports fallback.seed_run_count greater than 0.",
                    ],
                    retry_condition="Finalize one narrow fallback-family run, then rerun make auto-improve-readiness.",
                )
            )
        elif history_requirement and len(seed_runs) < history_requirement:
            remediations.append(
                _fallback_remediation(
                    blocker="fallback_target_history_depth",
                    remediation_code="add_comparable_fallback_history",
                    unblock_action_type="manual_comparable_run",
                    minimum_evidence=[
                        f"fallback.seed_run_count is at least fallback.history_requirement ({history_requirement}).",
                        "The comparable runs keep the same primary target family.",
                        "make auto-improve-readiness either emits a runnable proposal or reports the history requirement as met.",
                    ],
                    retry_condition="Add the missing comparable finalized run(s), then rerun make auto-improve-readiness.",
                )
            )
        else:
            remediations.append(
                _fallback_remediation(
                    blocker="proposal_queue_empty_after_history_seed",
                    remediation_code="review_queue_generation_thresholds",
                    unblock_action_type="queue_policy_review",
                    minimum_evidence=[
                        "mechanism review emits at least one candidate or documents the threshold preventing candidate emission.",
                        "mutation proposal generation emits at least one proposal or documents the remaining evidence gap.",
                    ],
                    retry_condition="Refresh generated reports after the queue policy or history evidence changes.",
                )
            )
    return remediations


def _readiness_fallback_payload(
    queue_state: ReadinessQueueState,
    fallback_status: str,
) -> dict[str, Any]:
    return {
        "status": fallback_status,
        "primary_targets": FALLBACK_PRIMARY_TARGETS,
        "supporting_targets": FALLBACK_SUPPORTING_TARGETS,
        "test_files": FALLBACK_TEST_FILES,
        "seed_run_count": len(queue_state.seed_runs),
        "seed_runs": queue_state.seed_runs,
        "history_requirement": queue_state.history_requirement,
        "additional_runs_needed": queue_state.additional_runs_needed,
        "queue_recheck_target": READINESS_TARGET,
        "auto_improve_command": AUTO_IMPROVE_GOAL_RUN_COMMAND,
    }


def readiness_queue_payloads(
    *,
    queue_state: ReadinessQueueState,
    reports_present: bool,
    mechanism_review_report: dict[str, Any],
) -> ReadinessQueuePayloads:
    checks = _checks(
        reports_present=reports_present,
        proposals_emitted=queue_state.proposals_emitted,
        runnable_proposal_count=len(queue_state.runnable_proposal_ids),
        blocked_proposal_count=queue_state.blocked_proposal_count,
        blocked_reason_counts=queue_state.blocked_reason_counts,
        session_reports_considered=int(
            queue_state.outcome_summary.get("session_reports_considered", 0) or 0
        ),
        seed_runs=queue_state.seed_runs,
        history_requirement=queue_state.history_requirement,
    )
    remediations = _readiness_remediations(
        reports_present=reports_present,
        proposals_emitted=queue_state.proposals_emitted,
        runnable_proposal_count=len(queue_state.runnable_proposal_ids),
        blocked_reason_counts=queue_state.blocked_reason_counts,
        blocked_proposal_ids=queue_state.blocked_proposal_ids,
        seed_runs=queue_state.seed_runs,
        history_requirement=queue_state.history_requirement,
    )
    queue = _readiness_queue(
        queue_ready=queue_state.queue_ready,
        proposals_emitted=queue_state.proposals_emitted,
        runnable_proposal_ids=queue_state.runnable_proposal_ids,
        blocked_proposal_count=queue_state.blocked_proposal_count,
        blocked_reason_counts=queue_state.blocked_reason_counts,
        proposal_summary=queue_state.proposal_summary,
        review_summary=queue_state.review_summary,
        outcome_summary=queue_state.outcome_summary,
        mechanism_review_report=mechanism_review_report,
        evidence_gaps=queue_state.queue_evidence_gaps,
    )
    fallback_status = _fallback_status(
        queue_state.queue_ready,
        queue_state.proposals_emitted,
        queue_state.blocked_proposal_count,
        queue_state.seed_runs,
    )
    return ReadinessQueuePayloads(
        queue=queue,
        fallback=_readiness_fallback_payload(queue_state, fallback_status),
        checks=checks,
        remediations=remediations,
    )


def _matching_fallback_seed_runs(vault: Path) -> list[str]:
    runs_dir = vault / "runs"
    if not runs_dir.exists():
        return []

    matched: list[str] = []
    for path in sorted(runs_dir.glob("*/run-telemetry.json")):
        payload = load_optional_json_object(path)
        if not payload or not bool(payload.get("finalized")):
            continue
        primary_targets = _string_list(payload.get("primary_targets"))
        if primary_targets == FALLBACK_PRIMARY_TARGETS:
            matched.append(path.parent.name)
    return matched


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


def _same_eval_proposal_run_ids(mutation_proposal_report: dict[str, Any]) -> list[str]:
    run_ids: list[str] = []
    proposals = mutation_proposal_report.get("proposals")
    if not isinstance(proposals, list):
        return run_ids
    for proposal in proposals:
        if (
            not isinstance(proposal, dict)
            or _string_list(proposal.get("blocked_by"))
            or str(proposal.get("failure_mode", "")).strip()
            not in SAME_EVAL_PROPOSAL_FAILURE_MODES
        ):
            continue
        for run_id in proposal.get("run_ids", []):
            value = str(run_id).strip()
            if value and value not in run_ids:
                run_ids.append(value)
    return run_ids


def _coverage_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _legacy_reconstruction_by_run(vault: Path) -> dict[str, dict[str, Any]]:
    report = load_optional_json_object(
        vault / LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH
    )
    rows = report.get("run_reconstructions")
    if not isinstance(rows, list):
        return {}
    by_run: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("run_id", "")).strip()
        status = str(row.get("reconstruction_status", "")).strip()
        if run_id and status in {"not_needed", "reconstructed"}:
            by_run[run_id] = row
    return by_run


def _legacy_secondary_axes_present(row: dict[str, Any]) -> bool:
    return bool(row.get("parsed_strict_secondary_improvement_present")) and bool(
        _string_list(row.get("parsed_secondary_axes"))
    )


def _legacy_behavior_delta_digest_present(row: dict[str, Any]) -> bool:
    digest = str(row.get("telemetry_behavior_delta_digest", "")).strip()
    artifact_sha = str(row.get("behavior_delta_artifact_sha256", "")).strip()
    return bool(digest or artifact_sha)


def _legacy_decision_reason_code_present(
    telemetry: dict[str, Any],
    row: dict[str, Any],
) -> bool:
    decision = telemetry.get("decision_record")
    if not isinstance(decision, dict):
        return False
    reason_code = str(decision.get("reason_code", "")).strip()
    source_rule = str(decision.get("source_rule", "")).strip()
    if reason_code != "equal_score_secondary_eligibility" and source_rule != (
        "equal_score_secondary_eligibility"
    ):
        return False
    return _legacy_secondary_axes_present(row)


def _same_eval_telemetry_summary(
    vault: Path, mutation_proposal_report: dict[str, Any]
) -> dict[str, Any]:
    run_ids = _same_eval_proposal_run_ids(mutation_proposal_report)
    legacy_rows = _legacy_reconstruction_by_run(vault)
    runs: list[dict[str, Any]] = []
    for run_id in run_ids:
        telemetry_path = _telemetry_path_for_run(vault, run_id)
        telemetry = load_optional_json_object(telemetry_path) if telemetry_path else {}
        legacy_row = legacy_rows.get(run_id, {})
        reason_code = str(telemetry.get("same_eval_reason_code", "")).strip()
        axes = _string_list(telemetry.get("secondary_improvement_axes"))
        legacy_axes_present = _legacy_secondary_axes_present(legacy_row)
        runs.append(
            {
                "run_id": run_id,
                "telemetry_path": report_path(vault, telemetry_path)
                if telemetry_path
                else "",
                "telemetry_present": bool(telemetry),
                "same_eval_reason_code_present": bool(
                    reason_code and reason_code != "unknown"
                )
                or _legacy_decision_reason_code_present(telemetry, legacy_row),
                "strict_secondary_improvement_present": bool(
                    telemetry.get("strict_secondary_improvement_present", False)
                )
                or legacy_axes_present,
                "secondary_improvement_axes_present": bool(axes) or legacy_axes_present,
                "behavior_delta_digest_present": bool(
                    str(telemetry.get("behavior_delta_digest", "")).strip()
                )
                or _legacy_behavior_delta_digest_present(legacy_row),
            }
        )
    run_count = len(runs)
    reason_code_count = sum(1 for item in runs if item["same_eval_reason_code_present"])
    strict_secondary_count = sum(
        1
        for item in runs
        if item["strict_secondary_improvement_present"]
        and item["secondary_improvement_axes_present"]
    )
    digest_count = sum(1 for item in runs if item["behavior_delta_digest_present"])
    complete_count = sum(
        1
        for item in runs
        if item["same_eval_reason_code_present"]
        and item["strict_secondary_improvement_present"]
        and item["secondary_improvement_axes_present"]
        and item["behavior_delta_digest_present"]
    )
    complete = run_count in (0, complete_count)
    return {
        "status": "not_applicable"
        if run_count == 0
        else ("pass" if complete else "blocked"),
        "proposal_family": "repeated_same_eval_or_discard",
        "proposal_failure_modes": sorted(SAME_EVAL_PROPOSAL_FAILURE_MODES),
        "run_count": run_count,
        "runs_with_complete_typed_evidence": complete_count,
        "same_eval_reason_code_coverage_ratio": _coverage_ratio(
            reason_code_count, run_count
        ),
        "strict_secondary_improvement_coverage_ratio": _coverage_ratio(
            strict_secondary_count, run_count
        ),
        "behavior_delta_digest_coverage_ratio": _coverage_ratio(
            digest_count, run_count
        ),
        "runs": runs,
    }


def _fallback_history_requirement(
    mechanism_review_report: dict[str, Any],
) -> tuple[int, int]:
    bootstrap = mechanism_review_report.get("diagnostics", {}).get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return 0, 0
    target_groups = bootstrap.get("target_groups_under_min_history", [])
    if not isinstance(target_groups, list):
        return 0, 0

    for item in target_groups:
        if not isinstance(item, dict):
            continue
        if _string_list(item.get("primary_targets")) != FALLBACK_PRIMARY_TARGETS:
            continue
        blocked = item.get("blocked_candidate_types", [])
        if not isinstance(blocked, list):
            return 0, 0
        required_runs = [
            int(entry["required_runs"])
            for entry in blocked
            if isinstance(entry, dict) and isinstance(entry.get("required_runs"), int)
        ]
        additional_runs_needed = [
            int(entry["additional_runs_needed"])
            for entry in blocked
            if isinstance(entry, dict)
            and isinstance(entry.get("additional_runs_needed"), int)
        ]
        return (
            max(required_runs, default=0),
            max(additional_runs_needed, default=0),
        )
    return 0, 0


def readiness_queue_state(
    vault: Path,
    reports: dict[str, dict[str, Any]],
) -> ReadinessQueueState:
    outcome_summary = dict_field(reports["outcome_metrics"], "summary")
    review_summary = dict_field(reports["mechanism_review"], "summary")
    proposal_summary = dict_field(reports["mutation_proposal"], "summary")
    proposal_diagnostics = dict_field(reports["mutation_proposal"], "diagnostics")
    loop_health_summary = _build_loop_health_summary(vault)
    same_eval_telemetry_summary = _same_eval_telemetry_summary(
        vault, reports["mutation_proposal"]
    )
    proposals_emitted = int(proposal_summary.get("proposals_emitted", 0) or 0)
    runnable_proposal_ids = _runnable_proposal_ids(reports["mutation_proposal"])
    blocked_proposal_count = _blocked_proposal_count(
        proposal_summary, proposal_diagnostics
    )
    blocked_reason_counts = _blocked_reason_counts(reports["mutation_proposal"])
    blocked_proposal_ids = _blocked_proposal_ids_by_reason(reports["mutation_proposal"])
    blocked_reasons = list(blocked_reason_counts)
    queue_ready = bool(runnable_proposal_ids)
    queue_evidence_gaps = _queue_evidence_gaps(
        review_report=reports["mechanism_review"],
        proposal_report=reports["mutation_proposal"],
        review_summary=review_summary,
        proposal_summary=proposal_summary,
        proposal_diagnostics=proposal_diagnostics,
        proposals_emitted=proposals_emitted,
        queue_ready=queue_ready,
        blocked_reasons=blocked_reasons,
    )
    seed_runs = _matching_fallback_seed_runs(vault)
    history_requirement, additional_runs_needed = _fallback_history_requirement(
        reports["mechanism_review"]
    )
    return ReadinessQueueState(
        outcome_summary=outcome_summary,
        review_summary=review_summary,
        proposal_summary=proposal_summary,
        proposal_diagnostics=proposal_diagnostics,
        loop_health_summary=loop_health_summary,
        same_eval_telemetry_summary=same_eval_telemetry_summary,
        queue_evidence_gaps=queue_evidence_gaps,
        proposals_emitted=proposals_emitted,
        runnable_proposal_ids=runnable_proposal_ids,
        blocked_proposal_count=blocked_proposal_count,
        blocked_reason_counts=blocked_reason_counts,
        blocked_proposal_ids=blocked_proposal_ids,
        blocked_reasons=blocked_reasons,
        queue_ready=queue_ready,
        seed_runs=seed_runs,
        history_requirement=history_requirement,
        additional_runs_needed=additional_runs_needed,
    )


def _checks(
    *,
    reports_present: bool,
    proposals_emitted: int,
    runnable_proposal_count: int,
    blocked_proposal_count: int,
    blocked_reason_counts: dict[str, int],
    session_reports_considered: int,
    seed_runs: list[str],
    history_requirement: int,
) -> list[dict[str, Any]]:
    blocked_detail = ""
    if blocked_proposal_count > 0:
        reason_text = ", ".join(
            f"{reason}={count}"
            for reason, count in sorted(blocked_reason_counts.items())
        )
        blocked_detail = (
            f"; retained blocked_proposal_count={blocked_proposal_count}"
            + (f" ({reason_text})" if reason_text else "")
        )
    return [
        {
            "id": "generated_reports_present",
            "pass": reports_present,
            "detail": (
                "refresh-generated-core outputs are present for outcome metrics, mechanism review, and mutation proposal."
                if reports_present
                else "expected refreshed outcome-metrics, mechanism-review-candidates, and mutation-proposals reports."
            ),
        },
        {
            "id": "proposal_queue_nonempty",
            "pass": runnable_proposal_count > 0,
            "detail": (
                f"runnable_proposal_count={runnable_proposal_count} "
                f"(proposals_emitted={proposals_emitted}){blocked_detail}"
                if runnable_proposal_count > 0
                else (
                    f"proposals_emitted={proposals_emitted} but runnable_proposal_count=0, "
                    f"so auto-improve should stay paused{blocked_detail}."
                    if proposals_emitted > 0
                    else "proposals_emitted=0 so auto-improve should stay paused."
                )
            ),
        },
        {
            "id": "outcome_metrics_session_rollup_present",
            "pass": session_reports_considered > 0,
            "detail": (
                f"session_reports_considered={session_reports_considered}"
                if session_reports_considered > 0
                else "session_reports_considered=0 so outcome metrics still lack session-rollup evidence."
            ),
        },
        {
            "id": "fallback_target_history_requirement_met",
            "pass": (
                proposals_emitted > 0
                or (
                    len(seed_runs) >= history_requirement
                    if history_requirement
                    else bool(seed_runs)
                )
            ),
            "detail": (
                "queue is already non-empty, so fallback history depth is not needed."
                if proposals_emitted > 0
                else (
                    f"fallback target family has {len(seed_runs)} finalized comparable run(s); "
                    f"required={history_requirement or 1}."
                )
            ),
        },
    ]


def _fallback_status(
    queue_ready: bool,
    proposals_emitted: int,
    blocked_proposal_count: int,
    seed_runs: list[str],
) -> str:
    if queue_ready:
        return "not_needed"
    if proposals_emitted > 0 or blocked_proposal_count > 0:
        return "blocked_queue"
    return "seed_recommended" if not seed_runs else "history_seeded"


def _readiness_next_action(
    *,
    queue_ready: bool,
    proposals_emitted: int,
    blocked_reasons: list[str],
    runnable_proposal_ids: list[str],
    seed_runs: list[str],
) -> str:
    if queue_ready:
        proposal_detail = (
            f" Run proposal `{runnable_proposal_ids[0]}` next."
            if runnable_proposal_ids
            else ""
        )
        return (
            "Queue is non-empty. After `make check-serial` and `make public-check-serial`, "
            f"start bounded goal-native auto-improve with `{AUTO_IMPROVE_GOAL_RUN_COMMAND}` "
            "so runner heartbeat, checkpoint, resume, and timeout evidence is captured."
            f"{proposal_detail}"
        )
    if proposals_emitted > 0:
        blocked_suffix = (
            f" Current blocker(s): {', '.join(blocked_reasons)}."
            if blocked_reasons
            else ""
        )
        return (
            "Generated proposals exist but none are runnable yet. Keep auto-improve paused, "
            "inspect `blocked_by` in `ops/reports/mutation-proposals.json`, let the current "
            "chronology move past the blocker or clear the blocking condition, then rerun "
            f"`{READINESS_TARGET}`.{blocked_suffix}"
        )
    if blocked_reasons:
        return (
            "No runnable proposal seed is available yet, but mutation proposal surfaced "
            f"blocked queue seed(s): {', '.join(blocked_reasons)}. Keep auto-improve paused, "
            "inspect `diagnostics.empty_queue_blockers` in `ops/reports/mutation-proposals.json`, "
            f"clear the listed blocker(s), then rerun `{READINESS_TARGET}`."
        )
    if not seed_runs:
        return (
            "Queue is empty and the fallback target family has no finalized comparable seed run yet. "
            "Finalize one narrow manual `system_mechanism` run for "
            "`ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py` plus "
            "`tests/test_auto_improve_iteration_runtime.py`, then rerun "
            f"`{READINESS_TARGET}`."
        )
    return (
        "Queue is still empty after the fallback family was seeded. Keep auto-improve paused and either "
        "add another comparable narrow run for `ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py` "
        "or review mechanism_review history thresholds, then rerun "
        f"`{READINESS_TARGET}`."
    )


def readiness_execution_fields(
    queue_state: ReadinessQueueState,
) -> ReadinessExecutionFields:
    reasons = [
        "runnable proposal queue is non-empty"
        if queue_state.queue_ready
        else "no runnable proposal is available"
    ]
    reasons.extend(
        gap
        for gap in queue_state.queue_evidence_gaps
        if gap.startswith(
            (
                "mechanism_review.status=attention",
                "mutation_proposal.status=attention",
            )
        )
    )
    if queue_state.proposals_emitted > 0 and not queue_state.queue_ready:
        if queue_state.blocked_reasons:
            reasons.append(
                f"proposal blockers active: {', '.join(queue_state.blocked_reasons)}"
            )
        else:
            reasons.append(
                "generated proposals exist, but every emitted proposal is currently blocked"
            )
    elif queue_state.proposals_emitted == 0 and not queue_state.queue_ready:
        reasons.append("mutation proposal generation emitted zero runnable proposals")

    return ReadinessExecutionFields(
        status="pass" if queue_state.queue_ready else "warn",
        gate_effect=(
            GATE_EFFECT_NONE
            if queue_state.queue_ready
            else GATE_EFFECT_BLOCKS_EXECUTION
        ),
        can_run=queue_state.queue_ready,
        reasons=reasons,
        runnable_proposal_count=len(queue_state.runnable_proposal_ids),
        blocked_proposal_count=queue_state.blocked_proposal_count,
        recommended_next_step=_readiness_next_action(
            queue_ready=queue_state.queue_ready,
            proposals_emitted=queue_state.proposals_emitted,
            blocked_reasons=queue_state.blocked_reasons,
            runnable_proposal_ids=queue_state.runnable_proposal_ids,
            seed_runs=queue_state.seed_runs,
        ),
    )


def _readiness_queue(
    *,
    queue_ready: bool,
    proposals_emitted: int,
    runnable_proposal_ids: list[str],
    blocked_proposal_count: int,
    blocked_reason_counts: dict[str, int],
    proposal_summary: dict[str, Any],
    review_summary: dict[str, Any],
    outcome_summary: dict[str, Any],
    mechanism_review_report: dict[str, Any],
    evidence_gaps: list[str],
) -> ReadinessQueue:
    return ReadinessQueue(
        ready=queue_ready,
        proposals_emitted=proposals_emitted,
        runnable_proposal_count=len(runnable_proposal_ids),
        runnable_proposal_ids=runnable_proposal_ids,
        blocked_proposal_count=blocked_proposal_count,
        blocked_reason_counts=_blocked_reason_count_items(blocked_reason_counts),
        source_candidates_read=int(
            proposal_summary.get("source_candidates_read", 0) or 0
        ),
        candidates_emitted=int(review_summary.get("candidates_emitted", 0) or 0),
        attempts_considered=int(outcome_summary.get("attempts_considered", 0) or 0),
        session_reports_considered=int(
            outcome_summary.get("session_reports_considered", 0) or 0
        ),
        queue_pressure_summary=str(proposal_summary.get("queue_pressure_summary", "")),
        review_bootstrap_summary=str(
            mechanism_review_report.get("diagnostics", {})
            .get("bootstrap", {})
            .get("summary", "")
        ),
        evidence_gaps=evidence_gaps,
    )
