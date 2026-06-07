from __future__ import annotations

from pathlib import Path

from ops.scripts.auto_improve_maintenance_decision_runtime import (
    MAINTENANCE_ACTION_RESUME_TARGET,
    MAINTENANCE_ACTION_RUNNER_ACTION,
    _expected_maintenance_cycle_count,
    _maintenance_cycle_queue_metadata,
    _maintenance_queue_action,
    build_maintenance_action_resume_plan,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_ACTION_SCHEMA = REPO_ROOT / "ops/schemas/goal-runtime-maintenance-action-plan.schema.json"


def _assert_valid_plan(plan: dict) -> None:
    assert validate_with_schema(plan, load_schema(MAINTENANCE_ACTION_SCHEMA)) == []


def _loader_must_not_run() -> dict:
    raise AssertionError("mutation proposal report loader should not run")


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
