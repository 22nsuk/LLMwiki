from __future__ import annotations

MAX_PROPOSALS_SELECTED_ZERO_DETAIL = "available proposals exist but report selection emitted none"
MAX_PROPOSALS_SELECTED_ZERO_REASON = "max_proposals_selected_zero"
RECENT_LOG_OVERLAP_BLOCKER = "recent_log_overlap"
RECENT_LOG_OVERLAP_QUEUE_BLOCKED_DETAIL = (
    "available proposals are blocked only by recent_log_overlap; emit a non-overlapping "
    "queue_unblock rotation before reporting an empty queue"
)
RECENT_LOG_OVERLAP_QUEUE_BLOCKED_REASON = "recent_log_overlap_queue_blocked"


def source_evidence_gaps(mechanism_review_report: dict, proposals: list[dict]) -> list[str]:
    evidence_gaps: list[str] = []
    summary = mechanism_review_report.get("summary", {})
    if isinstance(summary, dict) and int(summary.get("candidates_emitted", 0)) <= 0:
        evidence_gaps.append("mechanism review emitted zero candidates")

    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return evidence_gaps

    session_calibration = diagnostics.get("session_calibration", {})
    if isinstance(session_calibration, dict):
        session_status = str(session_calibration.get("status", "")).strip()
        if session_status == "no_session_context":
            evidence_gaps.append("session_calibration.status=no_session_context")

    outcome_metrics = diagnostics.get("outcome_metrics_calibration", {})
    if isinstance(outcome_metrics, dict):
        outcome_status = str(outcome_metrics.get("status", "")).strip()
        if outcome_status and outcome_status != "active":
            evidence_gaps.append(f"outcome_metrics_calibration.status={outcome_status}")
        for gap in outcome_metrics.get("evidence_gaps", []):
            text = str(gap).strip()
            if text:
                evidence_gaps.append(f"outcome_metrics: {text}")

    if not proposals and not evidence_gaps:
        evidence_gaps.append("proposal queue is empty after applying current mutation_proposal filters")

    deduped: list[str] = []
    seen: set[str] = set()
    for gap in evidence_gaps:
        if gap in seen:
            continue
        seen.add(gap)
        deduped.append(gap)
    return deduped


def _empty_queue_blocker(
    *,
    blocker_type: str,
    reason: str,
    detail: str,
    source: str,
    candidate_id: str | None = None,
    candidate_type: str | None = None,
    primary_targets: list[str] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "blocker_type": blocker_type,
        "reason": reason,
        "detail": detail,
        "source": source,
    }
    if candidate_id:
        item["candidate_id"] = candidate_id
    if candidate_type:
        item["candidate_type"] = candidate_type
    if primary_targets:
        item["primary_targets"] = primary_targets
    return item


def _queue_selection_blocker(available_proposals: list[dict]) -> dict[str, object]:
    recent_only = all(
        proposal.get("blocked_by") == [RECENT_LOG_OVERLAP_BLOCKER]
        for proposal in available_proposals
    )
    selection_reason = (
        RECENT_LOG_OVERLAP_QUEUE_BLOCKED_REASON
        if recent_only
        else MAX_PROPOSALS_SELECTED_ZERO_REASON
    )
    selection_detail = (
        RECENT_LOG_OVERLAP_QUEUE_BLOCKED_DETAIL
        if recent_only
        else MAX_PROPOSALS_SELECTED_ZERO_DETAIL
    )
    return _empty_queue_blocker(
        blocker_type="selection",
        reason=selection_reason,
        detail=selection_detail,
        source="queue_selection",
    )


def empty_queue_blockers(
    *,
    mutation_enabled: bool,
    mechanism_review_report: dict,
    available_proposals: list[dict],
    proposals: list[dict],
    skipped_candidates: list[dict],
    evidence_gaps: list[str],
) -> list[dict]:
    if proposals:
        return []

    blockers: list[dict] = []
    if not mutation_enabled:
        blockers.append(
            _empty_queue_blocker(
                blocker_type="policy",
                reason="mutation_proposal_disabled",
                detail="mutation_proposal.enabled=false",
                source="mutation_proposal_policy",
            )
        )

    diagnostics = mechanism_review_report.get("diagnostics", {})
    source_blockers = diagnostics.get("candidate_blockers", []) if isinstance(diagnostics, dict) else []
    if isinstance(source_blockers, list):
        for blocker in source_blockers:
            if not isinstance(blocker, dict):
                continue
            blocker_type = str(blocker.get("blocker_type", "")).strip() or "source"
            reason = str(blocker.get("reason", "")).strip() or "candidate_blocked"
            detail = str(blocker.get("detail", "")).strip() or reason
            primary_targets = [
                str(target)
                for target in blocker.get("primary_targets", [])
                if str(target).strip()
            ]
            blockers.append(
                _empty_queue_blocker(
                    blocker_type=blocker_type,
                    reason=reason,
                    detail=detail,
                    source="mechanism_review.candidate_blockers",
                    candidate_type=str(blocker.get("candidate_type", "")).strip() or None,
                    primary_targets=primary_targets,
                )
            )

    for skipped in skipped_candidates:
        reason = str(skipped.get("reason", "")).strip()
        if reason == "candidate_mapping_error":
            blocker_type = "schema"
        elif reason == "failure_mode_not_allowed":
            blocker_type = "policy"
        else:
            blocker_type = "source"
        blockers.append(
            _empty_queue_blocker(
                blocker_type=blocker_type,
                reason=reason or "candidate_skipped",
                detail=str(skipped.get("detail", "")).strip() or reason or "candidate skipped",
                source="skipped_candidates",
                candidate_id=str(skipped.get("candidate_id", "")).strip() or None,
            )
        )

    if available_proposals and not proposals:
        blockers.append(_queue_selection_blocker(available_proposals))

    if not blockers:
        for gap in evidence_gaps:
            gap_text = str(gap).strip()
            if not gap_text:
                continue
            if gap_text.startswith("session_calibration."):
                blocker_type = "session"
            elif gap_text.startswith("outcome_metrics"):
                blocker_type = "outcome"
            elif "zero candidates" in gap_text:
                blocker_type = "history"
            else:
                blocker_type = "source"
            blockers.append(
                _empty_queue_blocker(
                    blocker_type=blocker_type,
                    reason="evidence_gap",
                    detail=gap_text,
                    source="evidence_gaps",
                )
            )

    if not blockers:
        blockers.append(
            _empty_queue_blocker(
                blocker_type="source",
                reason="proposal_queue_empty_without_specific_blocker",
                detail="proposals_emitted=0 and blocked_proposals=0 after proposal generation",
                source="mutation_proposal",
            )
        )

    return blockers


def reported_blocked_proposal_count(
    proposals: list[dict],
    empty_queue_blockers: list[dict],
) -> int:
    if not proposals:
        return len(empty_queue_blockers)
    return sum(1 for proposal in proposals if not isinstance(proposal.get("blocked_by"), list) or proposal["blocked_by"])


def report_status(*, enabled: bool, proposals: list[dict]) -> str:
    if enabled and any(
        isinstance(proposal.get("blocked_by"), list) and not proposal["blocked_by"]
        for proposal in proposals
    ):
        return "pass"
    return "attention"
