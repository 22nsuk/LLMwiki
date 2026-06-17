from __future__ import annotations

from pathlib import Path

from .mutation_proposal_candidate_runtime import (
    MutationProposal,
    fixed_priority_breakdown,
    generated_must_change_tests,
    must_change_test_paths,
    must_not_expand_apply_roots,
    proposal_blast_radius_score,
    required_artifacts,
    resolve_must_change_tests,
    with_generated_supporting_targets,
)
from .mutation_proposal_recent_log_overlap_runtime import (
    RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
    RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
)
from .next_run_repair_queue_runtime import (
    NextRunRepairProposalDependencies,
    next_run_repair_proposal_models,
)


def _next_run_repair_dependencies() -> NextRunRepairProposalDependencies:
    return NextRunRepairProposalDependencies(
        with_generated_supporting_targets=with_generated_supporting_targets,
        must_change_test_paths=must_change_test_paths,
        generated_must_change_tests=generated_must_change_tests,
        resolve_must_change_tests=resolve_must_change_tests,
        proposal_blast_radius_score=proposal_blast_radius_score,
        must_not_expand_apply_roots=must_not_expand_apply_roots,
        required_artifacts=required_artifacts,
        proposal_factory=MutationProposal,
        priority_breakdown_factory=lambda: fixed_priority_breakdown(100),
    )


def next_run_repair_models_for_current_queue(
    vault: Path,
    effective_policy: dict,
    current_proposal_models: list[MutationProposal],
    *,
    next_run_decisions: list[dict],
    consumed_next_run_decision_ids: list[str],
) -> list[MutationProposal]:
    current_runnable_proposal_ids = {
        proposal.proposal_id
        for proposal in current_proposal_models
        if proposal.proposal_id and not proposal.blocked_by
    }
    return next_run_repair_proposal_models(
        vault,
        effective_policy,
        next_run_decisions,
        consumed_decision_ids=set(consumed_next_run_decision_ids),
        current_proposal_ids=current_runnable_proposal_ids,
        dependencies=_next_run_repair_dependencies(),
        recent_log_overlap_unblock_failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        recent_log_overlap_unblock_family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
    )
