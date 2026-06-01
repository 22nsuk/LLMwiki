from __future__ import annotations

from ops.scripts.mechanism.auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    OPEN_DECISION_STATUS,
)
from ops.scripts.mechanism.next_run_repair_queue_runtime import (
    open_carry_forward_decisions,
)


def _carry_forward_decision(**overrides: object) -> dict[str, object]:
    decision: dict[str, object] = {
        "decision": CARRY_FORWARD_DECISION,
        "status": OPEN_DECISION_STATUS,
        "decision_id": "next-run-decision:run-1",
        "observed_at": "2026-01-01T00:00:00Z",
        "target_proposal_id": "next_run_failure_repair__target",
        "primary_targets": ["ops/scripts/mechanism/mutation_proposal_runtime.py"],
        "failure_taxonomy": "review_blocked",
    }
    decision.update(overrides)
    return decision


def test_open_carry_forward_decisions_keeps_latest_decision_per_target() -> None:
    decisions = [
        _carry_forward_decision(
            decision_id="next-run-decision:old",
            observed_at="2026-01-01T00:00:00Z",
            reason="old repair",
        ),
        _carry_forward_decision(
            decision_id="next-run-decision:new",
            observed_at="2026-01-02T00:00:00Z",
            reason="new repair",
        ),
    ]

    open_decisions = open_carry_forward_decisions(
        decisions,
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert [decision["decision_id"] for decision in open_decisions] == [
        "next-run-decision:new"
    ]


def test_open_carry_forward_decisions_suppresses_consumed_ids_only() -> None:
    decisions = [
        _carry_forward_decision(decision_id="next-run-decision:consumed"),
        _carry_forward_decision(
            decision_id="next-run-decision:open",
            target_proposal_id="next_run_failure_repair__other",
            primary_targets=["ops/scripts/mechanism/run_mechanism_experiment_runtime.py"],
        ),
    ]

    open_decisions = open_carry_forward_decisions(
        decisions,
        consumed_decision_ids={"next-run-decision:consumed"},
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert [decision["decision_id"] for decision in open_decisions] == [
        "next-run-decision:open"
    ]


def test_open_carry_forward_decisions_suppresses_superseded_queue_rotation() -> None:
    open_decisions = open_carry_forward_decisions(
        [
            _carry_forward_decision(
                failure_taxonomy="mutation_failed",
                proposal_family="queue_unblock",
                proposal_id="recent_log_overlap_queue_blocked__old",
            )
        ],
        current_proposal_ids={"recent_log_overlap_queue_blocked__current"},
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert open_decisions == []
