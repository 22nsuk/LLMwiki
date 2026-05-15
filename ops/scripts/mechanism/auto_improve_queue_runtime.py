from __future__ import annotations


def build_proposal_queue(
    proposals_report: dict,
    *,
    attempted: set[str],
    quarantined: set[str],
) -> list[dict]:
    runnable = [
        proposal
        for proposal in proposals_report["proposals"]
        if not proposal["blocked_by"]
        and proposal["proposal_id"] not in attempted
        and proposal["proposal_id"] not in quarantined
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
