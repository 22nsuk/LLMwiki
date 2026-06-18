from __future__ import annotations


def _proposal_id(proposal: dict) -> str:
    return str(proposal.get("proposal_id", "")).strip()


def _proposal_priority(proposal: dict) -> int:
    priority_text = str(proposal.get("priority", 0)).strip()
    return int(priority_text) if priority_text.removeprefix("-").isdigit() else 0


def _normalized_blockers(proposal: dict) -> list[str]:
    return [
        blocker_text
        for blocker in proposal.get("blocked_by", []) or []
        for blocker_text in [str(blocker).strip()]
        if blocker_text
    ]


def is_recent_log_overlap_queue_unblock(proposal: dict, proposal_id: str | None = None) -> bool:
    proposal_id = _proposal_id(proposal) if proposal_id is None else str(proposal_id).strip()
    return (
        str(proposal.get("family", "")).strip() == "queue_unblock"
        and str(proposal.get("failure_mode", "")).strip()
        == "recent_log_overlap_queue_blocked"
        and proposal_id.startswith("recent_log_overlap_queue_blocked__")
    )


def _standard_runnable_proposal_ids(
    proposals: list[dict],
    *,
    attempted: set[str],
    quarantined: set[str],
) -> set[str]:
    return {
        proposal_id
        for proposal in proposals
        for proposal_id in [_proposal_id(proposal)]
        if proposal_id
        and proposal_id not in attempted
        and proposal_id not in quarantined
        and not _normalized_blockers(proposal)
    }


def build_proposal_queue(
    proposals_report: dict,
    *,
    attempted: set[str],
    quarantined: set[str],
) -> list[dict]:
    proposals = proposals_report["proposals"]
    recent_log_overlap_unblock_enabled = not _standard_runnable_proposal_ids(
        proposals,
        attempted=attempted,
        quarantined=quarantined,
    )
    runnable = [
        {
            **proposal,
            "proposal_id": proposal_id,
            "priority": _proposal_priority(proposal),
            "blocked_by": normalized_blockers,
        }
        for proposal in proposals
        for proposal_id in [_proposal_id(proposal)]
        if proposal_id
        and not (
            normalized_blockers := [
                blocker_text
                for blocker_text in _normalized_blockers(proposal)
                if not (
                    recent_log_overlap_unblock_enabled
                    and blocker_text == "recent_log_overlap"
                    and is_recent_log_overlap_queue_unblock(proposal, proposal_id)
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
