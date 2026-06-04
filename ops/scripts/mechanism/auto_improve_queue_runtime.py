from __future__ import annotations


def build_proposal_queue(
    proposals_report: dict,
    *,
    attempted: set[str],
    quarantined: set[str],
) -> list[dict]:
    runnable = [
        {
            **proposal,
            "proposal_id": proposal_id,
            "priority": int(priority_text) if priority_text.removeprefix("-").isdigit() else 0,
            "blocked_by": normalized_blockers,
        }
        for proposal in proposals_report["proposals"]
        for proposal_id in [str(proposal.get("proposal_id", "")).strip()]
        for proposal_family in [str(proposal.get("family", "")).strip()]
        for failure_mode in [str(proposal.get("failure_mode", "")).strip()]
        for priority_text in [str(proposal.get("priority", 0)).strip()]
        if proposal_id
        and not (
            normalized_blockers := [
                blocker_text
                for blocker in proposal.get("blocked_by", []) or []
                for blocker_text in [str(blocker).strip()]
                if blocker_text
                and not (
                    blocker_text == "recent_log_overlap"
                    and proposal_family == "queue_unblock"
                    and failure_mode == "recent_log_overlap_queue_blocked"
                    and proposal_id.startswith("recent_log_overlap_queue_blocked__")
                )
            ]
        )
        and proposal_id not in attempted
        and proposal_id not in quarantined
    ]
    runnable.sort(key=lambda item: (-item["priority"], item["proposal_id"]))
    return runnable


def select_next_proposal(
    proposals_report: dict,
    *,
    attempted: set[str],
    quarantined: set[str],
) -> tuple[dict | None, list[str]]:
    runnable = build_proposal_queue(
        proposals_report,
        attempted=attempted,
        quarantined=quarantined,
    )
    return (runnable[0] if runnable else None), [item["proposal_id"] for item in runnable]
