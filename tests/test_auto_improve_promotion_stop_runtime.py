from __future__ import annotations

from ops.scripts.mechanism import (
    auto_improve_promotion_stop_runtime,
    auto_improve_runtime,
)
from ops.scripts.mechanism.auto_improve_promotion_stop_runtime import (
    promotion_maintenance_stop_decision,
)


def _session_with_last_outcome(outcome: str) -> dict:
    return {
        "iterations": [
            {
                "run_id": "auto-session-run-01",
                "outcome": outcome,
                "decision": "PROMOTE" if outcome == "promoted" else "DISCARD",
            }
        ]
    }


def test_auto_improve_runtime_promotion_stop_exports_point_to_helper() -> None:
    assert (
        auto_improve_runtime._promotion_maintenance_stop_decision
        is auto_improve_promotion_stop_runtime.promotion_maintenance_stop_decision
    )


def test_promotion_maintenance_stop_decision_skips_when_stop_reason_is_not_budget() -> None:
    decision = promotion_maintenance_stop_decision(
        _session_with_last_outcome("promoted"),
        maintain_until_budget=False,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=5,
        new_iteration_count=1,
        stop_reason="queue_exhausted",
        elapsed_seconds=10,
        target_elapsed_seconds=60,
    )

    assert decision.should_run_maintenance is False
    assert decision.reason == "stop_reason_not_proposal_budget_exhausted"
    assert decision.stop_reason is None


def test_promotion_maintenance_stop_decision_rewrites_exhausted_budget_stop_reason() -> None:
    decision = promotion_maintenance_stop_decision(
        _session_with_last_outcome("promoted"),
        maintain_until_budget=True,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=5,
        new_iteration_count=1,
        stop_reason="proposal_budget_exhausted",
        elapsed_seconds=60,
        target_elapsed_seconds=60,
    )

    assert decision.should_run_maintenance is False
    assert decision.reason == "time_budget_already_exhausted"
    assert decision.stop_reason == "time_budget_exhausted"


def test_promotion_maintenance_stop_decision_runs_after_new_promotion() -> None:
    decision = promotion_maintenance_stop_decision(
        _session_with_last_outcome("promoted"),
        maintain_until_budget=False,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=5,
        new_iteration_count=1,
        stop_reason="proposal_budget_exhausted",
        elapsed_seconds=10,
        target_elapsed_seconds=60,
    )

    assert decision.should_run_maintenance is True
    assert decision.reason == "eligible"
    assert decision.interval_seconds == 5
    assert decision.max_cycles == 1
