from __future__ import annotations

from ops.scripts.auto_improve_maintenance_decision_runtime import (
    MAINTENANCE_ACTION_RESUME_TARGET,
    MAINTENANCE_ACTION_RUNNER_ACTION,
    _expected_maintenance_cycle_count,
    _maintenance_cycle_queue_metadata,
    _maintenance_queue_action,
)


def test_maintenance_queue_action_classifies_empty_recent_overlap_and_stable_queue() -> None:
    assert _maintenance_queue_action([]) == {
        "status": "none",
        "reason": "queue_empty",
        "proposal_ids": [],
        "runner_action": "none",
        "proposal_budget_increment": 0,
        "resume_target": "",
        "recommended_next_step": "Refresh auto-improve readiness and inspect queue remediations.",
    }

    recent = _maintenance_queue_action(["recent_log_overlap_queue_blocked__a"])
    assert recent["status"] == "action_required"
    assert recent["reason"] == "recent_log_overlap_queue_blocked"
    assert recent["runner_action"] == MAINTENANCE_ACTION_RUNNER_ACTION
    assert recent["resume_target"] == MAINTENANCE_ACTION_RESUME_TARGET

    stable = _maintenance_queue_action(["proposal-a"])
    assert stable["status"] == "action_required"
    assert stable["reason"] == "stable_runnable_queue"
    assert stable["proposal_budget_increment"] == 1


def test_maintenance_cycle_queue_metadata_tracks_stability_and_meaningful_changes() -> None:
    first = _maintenance_cycle_queue_metadata([], ["proposal-a"], 1)
    assert first["meaningful"] is True
    assert first["meaningful_reasons"] == ["post_promote_observation"]
    assert first["stable_queue_snapshot_count"] == 1

    second = _maintenance_cycle_queue_metadata(
        [{"queue_snapshot": ["proposal-a"], "runnable_proposal_count": 1}],
        ["proposal-a"],
        1,
    )
    assert second["meaningful"] is False
    assert second["stable_queue_snapshot_count"] == 2

    changed = _maintenance_cycle_queue_metadata(
        [{"queue_snapshot": ["proposal-a"], "runnable_proposal_count": 1}],
        ["proposal-b"],
        2,
    )
    assert changed["meaningful"] is True
    assert changed["meaningful_reasons"] == [
        "queue_snapshot_changed",
        "runnable_proposal_count_changed",
    ]


def test_expected_maintenance_cycle_count_includes_initial_observation_cycle() -> None:
    assert (
        _expected_maintenance_cycle_count(
            start_elapsed_seconds=0,
            target_elapsed_seconds=600,
            interval_seconds=300,
        )
        == 3
    )
    assert (
        _expected_maintenance_cycle_count(
            start_elapsed_seconds=600,
            target_elapsed_seconds=600,
            interval_seconds=300,
        )
        == 0
    )
