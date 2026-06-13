from __future__ import annotations

from pathlib import Path
from typing import Any

from .auto_improve_next_run_decision_runtime import NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
from .mutation_proposal_loader_runtime import load_next_run_decision_queue_inputs
from .mutation_proposal_recent_log_overlap_runtime import (
    RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
    RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
)
from .next_run_repair_queue_runtime import open_carry_forward_decisions

OPEN_NEXT_RUN_REPAIR_QUARANTINED_BLOCKER = "open_next_run_repair_quarantined_source"


def _current_source_proposal_ids(mutation_proposal_report: dict[str, Any]) -> set[str]:
    proposals = mutation_proposal_report.get("proposals")
    if not isinstance(proposals, list):
        return set()
    return {
        str(proposal.get("proposal_id", "")).strip()
        for proposal in proposals
        if isinstance(proposal, dict)
        and str(proposal.get("failure_mode", "")).strip()
        != NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
        and str(proposal.get("proposal_id", "")).strip()
    }


def open_repair_quarantined_source_proposal_ids(
    vault: Path,
    mutation_proposal_report: dict[str, Any],
) -> list[str]:
    queue_inputs = load_next_run_decision_queue_inputs(vault)
    open_decisions = open_carry_forward_decisions(
        queue_inputs.next_run_decisions,
        vault=vault,
        consumed_decision_ids=set(queue_inputs.consumed_next_run_decision_ids),
        current_proposal_ids=_current_source_proposal_ids(mutation_proposal_report),
        recent_log_overlap_unblock_failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        recent_log_overlap_unblock_family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
    )
    target_proposal_ids = {
        str(decision.get("target_proposal_id", "")).strip()
        for decision in open_decisions
        if str(decision.get("target_proposal_id", "")).strip()
    }
    source_proposal_ids: list[str] = []
    for decision in open_decisions:
        if not bool(decision.get("quarantined_source_proposal")):
            continue
        proposal_id = str(decision.get("proposal_id", "")).strip()
        if (
            proposal_id
            and proposal_id not in target_proposal_ids
            and proposal_id not in source_proposal_ids
        ):
            source_proposal_ids.append(proposal_id)
    return source_proposal_ids
