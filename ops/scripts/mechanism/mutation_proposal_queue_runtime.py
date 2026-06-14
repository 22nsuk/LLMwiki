from __future__ import annotations

from dataclasses import dataclass

from .auto_improve_next_run_decision_runtime import NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
from .mutation_proposal_candidate_runtime import MutationProposal

QUEUE_PRESSURE_SUMMARY_TOP_N = 3


@dataclass(frozen=True)
class QueueSelectionDiagnostics:
    available_proposal_count: int
    selected_proposal_count: int
    selection_mode: str
    repair_priority_suppressed_count: int
    runnable_available_count: int
    blocked_available_count: int
    selected_runnable_count: int
    selected_blocked_count: int
    blocked_reason_counts: list[dict]

    def to_wire(self) -> dict:
        return {
            "available_proposal_count": self.available_proposal_count,
            "selected_proposal_count": self.selected_proposal_count,
            "selection_mode": self.selection_mode,
            "repair_priority_suppressed_count": self.repair_priority_suppressed_count,
            "runnable_available_count": self.runnable_available_count,
            "blocked_available_count": self.blocked_available_count,
            "selected_runnable_count": self.selected_runnable_count,
            "selected_blocked_count": self.selected_blocked_count,
            "blocked_reason_counts": self.blocked_reason_counts,
        }


def _report_selection_sort_key(proposal: MutationProposal) -> tuple[bool, int, int, str]:
    return (
        bool(proposal.blocked_by),
        -proposal.priority,
        proposal.blast_radius_score,
        proposal.proposal_id,
    )


def select_report_proposals(
    proposals: list[MutationProposal],
    *,
    max_proposals: int,
) -> list[MutationProposal]:
    if max_proposals <= 0:
        return []
    repair_proposals = [
        proposal
        for proposal in proposals
        if proposal.failure_mode == NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
    ]
    selectable = repair_proposals or proposals
    return sorted(selectable, key=_report_selection_sort_key)[:max_proposals]


def _blocked_reason_counts(proposals: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        for reason in proposal.get("blocked_by", []):
            reason_text = str(reason).strip()
            if not reason_text:
                continue
            counts[reason_text] = counts.get(reason_text, 0) + 1
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def queue_selection_diagnostics(
    available_proposals: list[dict],
    selected_proposals: list[dict],
) -> dict:
    repair_available = [
        proposal
        for proposal in available_proposals
        if proposal.get("failure_mode") == NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
    ]
    repair_priority_suppressed_count = (
        sum(
            1
            for proposal in available_proposals
            if proposal.get("failure_mode") != NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
        )
        if repair_available
        else 0
    )
    return QueueSelectionDiagnostics(
        available_proposal_count=len(available_proposals),
        selected_proposal_count=len(selected_proposals),
        selection_mode="carry_forward_repair_only" if repair_available else "standard",
        repair_priority_suppressed_count=repair_priority_suppressed_count,
        runnable_available_count=sum(
            1 for proposal in available_proposals if not proposal.get("blocked_by")
        ),
        blocked_available_count=sum(
            1 for proposal in available_proposals if proposal.get("blocked_by")
        ),
        selected_runnable_count=sum(
            1 for proposal in selected_proposals if not proposal.get("blocked_by")
        ),
        selected_blocked_count=sum(
            1 for proposal in selected_proposals if proposal.get("blocked_by")
        ),
        blocked_reason_counts=_blocked_reason_counts(available_proposals),
    ).to_wire()


def queue_pressure_summary(
    family_session_calibration: dict,
    *,
    evidence_gaps: list[str] | None = None,
    top_n: int = QUEUE_PRESSURE_SUMMARY_TOP_N,
) -> str:
    status = str(family_session_calibration.get("status", "")).strip()
    by_family = list(family_session_calibration.get("by_family", []))
    evidence_summary = " | ".join((evidence_gaps or [])[:3])
    if status == "no_proposals" or not by_family:
        if evidence_summary:
            return f"no proposals emitted | {evidence_summary}"
        return "no proposals emitted"

    sorted_families = sorted(
        (item for item in by_family if isinstance(item, dict)),
        key=lambda item: (
            -int(item.get("proposal_count", 0)),
            -abs(int(item.get("session_priority_delta", 0))),
            -int(item.get("blocked_proposal_count", 0)),
            str(item.get("family", "")),
        ),
    )

    signal_labels = (
        ("validation_blocked_sessions", "validation"),
        ("review_blocked_sessions", "review"),
        ("mutation_failed_sessions", "mutation"),
        ("validator_dispatch_sessions", "validator"),
        ("reviewer_dispatch_sessions", "reviewer"),
        ("high_risk_routing_sessions", "risk"),
    )
    segments: list[str] = []
    for item in sorted_families[:top_n]:
        proposal_count = int(item.get("proposal_count", 0))
        blocked_count = int(item.get("blocked_proposal_count", 0))
        priority_delta = int(item.get("session_priority_delta", 0))
        family = str(item.get("family", "")).strip() or "<unknown>"
        parts = [
            f"{family} {proposal_count} proposal" + ("" if proposal_count == 1 else "s")
        ]
        if blocked_count > 0:
            parts.append(f"{blocked_count} blocked")
        if priority_delta != 0:
            parts.append(f"delta {priority_delta:+d}")
        active_signals = sorted(
            (
                (label, int(item.get(field, 0)), idx)
                for idx, (field, label) in enumerate(signal_labels)
                if int(item.get(field, 0)) > 0
            ),
            key=lambda entry: (-entry[1], entry[2], entry[0]),
        )
        for label, count, _ in active_signals[:2]:
            parts.append(f"{label} {count}")
        segments.append(", ".join(parts))

    if len(sorted_families) > top_n:
        segments.append(f"+{len(sorted_families) - top_n} more")

    summary = "; ".join(segments)
    if status == "disabled":
        return f"session calibration disabled | {summary}"
    if status == "no_session_context":
        return f"session unavailable | {summary}"
    return summary
