from __future__ import annotations

from ops.scripts.mechanism.auto_improve_next_run_decision_runtime import (
    NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
)
from ops.scripts.mechanism.mutation_proposal_candidate_runtime import (
    MutationProposal,
    fixed_priority_breakdown,
)
from ops.scripts.mechanism.mutation_proposal_queue_runtime import (
    queue_pressure_summary,
    queue_selection_diagnostics,
    select_report_proposals,
)


def _proposal(
    proposal_id: str,
    *,
    priority: int,
    blast_radius_score: int = 1,
    failure_mode: str = "ordinary_failure",
    blocked_by: list[str] | None = None,
    family: str = "runtime",
) -> MutationProposal:
    return MutationProposal(
        proposal_id=proposal_id,
        source_candidate_id=f"candidate-{proposal_id}",
        source_candidate_type="mechanism_test_candidate",
        family=family,
        tier="P1",
        priority=priority,
        primary_targets=[f"ops/scripts/{proposal_id}.py"],
        supporting_targets=[],
        metrics_triggered=[failure_mode],
        run_ids=[],
        failure_mode=failure_mode,
        single_mechanism_scope="single_file",
        change_hypothesis="helper extraction preserves report behavior",
        expected_binary_signal="focused tests pass",
        blast_radius_score=blast_radius_score,
        must_change_tests=["tests/test_mutation_proposal_queue_runtime.py"],
        must_change_budget_signal={
            "signal": "queue_selection_contract",
            "expected_change": "stable",
        },
        must_not_expand_apply_roots=True,
        must_not_increase_untyped_surface=True,
        required_artifacts=[],
        blocked_by=blocked_by or [],
        why_now="queue pressure should be ranked before report rendering",
        priority_breakdown=fixed_priority_breakdown(priority),
        recent_log_overlap_matches=[],
    )


def test_select_report_proposals_prioritizes_next_run_repairs_before_standard_queue() -> None:
    standard_high_priority = _proposal("standard-high", priority=90)
    repair_blocked = _proposal(
        "repair-blocked",
        priority=100,
        failure_mode=NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
        blocked_by=["structural_complexity_budget"],
    )
    repair_runnable = _proposal(
        "repair-runnable",
        priority=80,
        failure_mode=NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
    )

    selected = select_report_proposals(
        [standard_high_priority, repair_blocked, repair_runnable],
        max_proposals=2,
    )

    assert [proposal.proposal_id for proposal in selected] == [
        "repair-runnable",
        "repair-blocked",
    ]


def test_queue_selection_diagnostics_reports_suppressed_standard_items_and_blockers() -> None:
    proposals = [
        _proposal("standard-high", priority=90),
        _proposal(
            "repair-blocked",
            priority=100,
            failure_mode=NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
            blocked_by=["structural_complexity_budget", "source_action_required"],
        ),
        _proposal(
            "repair-runnable",
            priority=80,
            failure_mode=NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
        ),
    ]
    selected = select_report_proposals(proposals, max_proposals=2)

    diagnostics = queue_selection_diagnostics(
        [proposal.to_wire() for proposal in proposals],
        [proposal.to_wire() for proposal in selected],
    )

    assert diagnostics == {
        "available_proposal_count": 3,
        "selected_proposal_count": 2,
        "selection_mode": "carry_forward_repair_only",
        "repair_priority_suppressed_count": 1,
        "runnable_available_count": 2,
        "blocked_available_count": 1,
        "selected_runnable_count": 1,
        "selected_blocked_count": 1,
        "blocked_reason_counts": [
            {"reason": "source_action_required", "count": 1},
            {"reason": "structural_complexity_budget", "count": 1},
        ],
    }


def test_queue_pressure_summary_uses_evidence_gaps_when_no_family_signal() -> None:
    assert (
        queue_pressure_summary(
            {"status": "no_proposals", "by_family": []},
            evidence_gaps=["source_action_required", "artifact_stale"],
        )
        == "no proposals emitted | source_action_required | artifact_stale"
    )
