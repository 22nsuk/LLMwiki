from __future__ import annotations

from pathlib import Path

import pytest
from ops.scripts.auto_improve_maintenance_decision_runtime import (
    MAINTENANCE_ACTION_RESUME_TARGET,
    MAINTENANCE_ACTION_RUNNER_ACTION,
    _expected_maintenance_cycle_count,
    _initial_maintenance_payload,
    _maintenance_completion_stop_reason,
    _maintenance_cycle_queue_metadata,
    _maintenance_queue_action,
    _maintenance_run_eligibility,
    _maintenance_terminal_completion_condition,
    _resolve_maintenance_interval,
    _resolve_post_promote_maintenance_cycles,
    build_maintenance_action_resume_plan,
)

from ops.scripts import auto_improve_runtime
from ops.scripts.mechanism import auto_improve_maintenance_decision_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]

BUSINESS_PLAN_REQUIRED_FIELDS = {
    "artifact_kind",
    "producer",
    "session_id",
    "status",
    "current_max_proposals",
    "current_iteration_count",
    "next_max_proposals",
    "queue_action",
    "selected_proposal",
    "blockers",
    "recommended_next_action",
    "decisions",
}


def _assert_valid_plan(plan: dict) -> None:
    assert set(plan) >= BUSINESS_PLAN_REQUIRED_FIELDS
    assert plan["artifact_kind"] == "goal_runtime_maintenance_action_plan"
    assert plan["producer"] == "ops.scripts.auto_improve_runtime"
    assert isinstance(plan["queue_action"], dict)
    assert isinstance(plan["selected_proposal"], dict)
    assert isinstance(plan["blockers"], list)
    assert isinstance(plan["decisions"], dict)


def _loader_must_not_run() -> dict:
    raise AssertionError("mutation proposal report loader should not run")


def test_auto_improve_runtime_maintenance_exports_point_to_helper() -> None:
    assert (
        auto_improve_runtime.MAINTENANCE_ACTION_RUNNER_ACTION
        is auto_improve_maintenance_decision_runtime.MAINTENANCE_ACTION_RUNNER_ACTION
    )
    assert (
        auto_improve_runtime.MAINTENANCE_ACTION_RESUME_TARGET
        is auto_improve_maintenance_decision_runtime.MAINTENANCE_ACTION_RESUME_TARGET
    )
    assert (
        auto_improve_runtime.build_maintenance_action_resume_plan
        is auto_improve_maintenance_decision_runtime.build_maintenance_action_resume_plan
    )


def test_maintenance_runtime_option_coercion_rejects_invalid_values() -> None:
    assert _resolve_maintenance_interval(None) == 300
    assert _resolve_maintenance_interval(1) == 1
    assert _resolve_post_promote_maintenance_cycles(None) == 1
    assert _resolve_post_promote_maintenance_cycles(0) == 0

    for invalid_interval in (0, -1, True):
        with pytest.raises(auto_improve_runtime.AutoImproveUsageError):
            _resolve_maintenance_interval(invalid_interval)  # type: ignore[arg-type]

    for invalid_cycles in (-1, False):
        with pytest.raises(auto_improve_runtime.AutoImproveUsageError):
            _resolve_post_promote_maintenance_cycles(invalid_cycles)  # type: ignore[arg-type]


def test_maintenance_run_eligibility_preserves_skip_order_and_run_shape() -> None:
    skipped = _maintenance_run_eligibility(
        maintain_until_budget=False,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=0,
        new_iteration_count=0,
        stop_reason="proposal_budget_exhausted",
        last_iteration_outcome="promoted",
        elapsed_seconds=10,
        target_elapsed_seconds=60,
    )
    assert skipped.should_run is False
    assert skipped.reason == "default_post_promote_without_new_iteration"
    assert skipped.stop_reason is None

    exhausted = _maintenance_run_eligibility(
        maintain_until_budget=True,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=5,
        new_iteration_count=1,
        stop_reason="proposal_budget_exhausted",
        last_iteration_outcome="promoted",
        elapsed_seconds=60,
        target_elapsed_seconds=60,
    )
    assert exhausted.should_run is False
    assert exhausted.reason == "time_budget_already_exhausted"
    assert exhausted.stop_reason == "time_budget_exhausted"

    eligible = _maintenance_run_eligibility(
        maintain_until_budget=False,
        post_promote_maintenance_cycles=None,
        maintenance_interval_seconds=5,
        new_iteration_count=1,
        stop_reason="proposal_budget_exhausted",
        last_iteration_outcome="promoted",
        elapsed_seconds=10,
        target_elapsed_seconds=60,
    )
    assert eligible.should_run is True
    assert eligible.interval_seconds == 5
    assert eligible.max_cycles == 1


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


def test_initial_maintenance_payload_and_terminal_conditions_are_pure_decisions() -> None:
    payload = _initial_maintenance_payload(
        started_at="2026-04-15T00:00:00Z",
        target_elapsed_seconds=600,
        start_elapsed_seconds=0,
        interval_seconds=300,
        max_cycles=None,
    )
    assert payload["completion_condition"] == "time_budget"
    assert payload["expected_min_cycle_count"] == 3
    assert payload["queue_action"]["status"] == "none"

    stable_session = {
        "maintenance": {
            "stable_queue_snapshot": ["proposal-a"],
            "stable_queue_snapshot_count": 2,
            "cycle_count": 1,
        }
    }
    assert (
        _maintenance_terminal_completion_condition(
            stable_session,
            default_completion_condition="time_budget",
            max_cycles=None,
            elapsed_seconds=300,
            target_elapsed_seconds=600,
        )
        == "stable_queue_snapshot"
    )
    assert _maintenance_completion_stop_reason("stable_queue_snapshot") == "stable_queue_snapshot"
    assert (
        _maintenance_completion_stop_reason("post_promote_cycle_limit")
        == "post_promote_cycle_limit_reached"
    )
    assert _maintenance_completion_stop_reason("time_budget") == "time_budget_reached"


def test_maintenance_action_resume_plan_returns_pass_without_required_action() -> None:
    plan = build_maintenance_action_resume_plan(
        {
            "budget": {"max_proposals": 1},
            "iterations": [{"proposal_id": "proposal-a"}],
            "maintenance": {"queue_action": {"status": "none"}},
        },
        session_id="auto-session-no-action",
        mutation_proposals_report_loader=_loader_must_not_run,
    )

    assert plan["status"] == "pass"
    assert plan["next_max_proposals"] == 1
    assert plan["decisions"] == {
        "can_resume": False,
        "requires_budget_increment": False,
    }
    assert plan["recommended_next_action"] == "No maintenance queue action requires a resume."
    _assert_valid_plan(plan)


def test_maintenance_action_resume_plan_blocks_invalid_runner_before_loading_proposals() -> None:
    plan = build_maintenance_action_resume_plan(
        {
            "budget": {"max_proposals": 1},
            "iterations": [],
            "maintenance": {
                "queue_action": {
                    "status": "action_required",
                    "runner_action": "manual_only",
                    "proposal_budget_increment": 1,
                    "proposal_ids": ["proposal-a"],
                }
            },
        },
        session_id="auto-session-invalid-runner",
        mutation_proposals_report_loader=_loader_must_not_run,
    )

    assert plan["status"] == "attention"
    assert plan["blockers"] == ["maintenance queue action has no executable runner action"]
    assert plan["decisions"]["can_resume"] is False
    _assert_valid_plan(plan)


def test_maintenance_action_resume_plan_refreshes_stale_recent_overlap_queue_action() -> None:
    current_proposal_id = "recent_log_overlap_queue_blocked__maintenance-decision-runtime"
    plan = build_maintenance_action_resume_plan(
        {
            "budget": {"max_proposals": 1},
            "iterations": [{"proposal_id": "recent_log_overlap_queue_blocked__old-runtime"}],
            "attempted_proposal_ids": ["recent_log_overlap_queue_blocked__old-runtime"],
            "maintenance": {
                "queue_action": {
                    "status": "action_required",
                    "reason": "recent_log_overlap_queue_blocked",
                    "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
                    "proposal_budget_increment": 1,
                    "proposal_ids": ["recent_log_overlap_queue_blocked__old-runtime"],
                }
            },
        },
        session_id="auto-session-stale-recent-log-overlap",
        mutation_proposals_report_loader=lambda: {
            "proposals": [
                {
                    "proposal_id": current_proposal_id,
                    "family": "queue_unblock",
                    "failure_mode": "recent_log_overlap_queue_blocked",
                    "blocked_by": ["recent_log_overlap"],
                    "priority": 91,
                }
            ]
        },
    )

    assert plan["status"] == "pass"
    assert plan["selected_proposal"]["proposal_id"] == current_proposal_id
    assert plan["queue_action"]["reason"] == "recent_log_overlap_queue_blocked"
    assert plan["queue_action"]["proposal_ids"] == [current_proposal_id]
    assert plan["actionable_queue_snapshot"] == [current_proposal_id]
    assert plan["decisions"] == {
        "can_resume": True,
        "requires_budget_increment": True,
    }
    _assert_valid_plan(plan)


def test_maintenance_action_resume_plan_blocks_missing_mutation_proposal_report() -> None:
    plan = build_maintenance_action_resume_plan(
        {
            "budget": {"max_proposals": 1},
            "iterations": [],
            "maintenance": {
                "queue_action": {
                    "status": "action_required",
                    "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
                    "proposal_budget_increment": 1,
                    "proposal_ids": ["proposal-a"],
                }
            },
        },
        session_id="auto-session-missing-proposals",
        mutation_proposals_report_loader=dict,
    )

    assert plan["status"] == "attention"
    assert plan["blockers"] == ["mutation proposal report is missing or invalid"]
    assert plan["next_max_proposals"] == 1
    _assert_valid_plan(plan)
